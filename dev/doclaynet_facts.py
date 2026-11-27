"""Extract per-page facts from DocLayNet v1.2 (scientific_articles) for the detector statistics. Dev-only tool.

Each page is read once with the detector's own building blocks (`analyze_page`, `_image_ink_rect`, the clip-cut
drawings, `_label_lines`, `main_text_score`), so the facts show what the tool sees. Every text block and text line is
then tagged with the human-annotated DocLayNet box it falls in (Picture, Caption, Text, ...). DocLayNet boxes never
overlap, so a line inside a Picture is part of that figure and a line outside every Picture is not.

`dev/doclaynet_stats.py` reads these facts and writes the report; changing a statistic never re-reads the dataset.

The hold-out subset is never read (it is kept for unbiased measurement only). Rotated pages are skipped: the tool
detects on the unrotated page while DocLayNet annotates the displayed one.

Example (system Python with pyarrow + PyMuPDF; the dataset never enters the repository):
  python -X utf8 dev\\doclaynet_facts.py --data D:\\PdfSamples --subset tune --subset val --subset test

Output: <cache-dir>/facts/v<FACTS_VERSION>/<split>_<parquet>_rg<k>.jsonl.gz, one JSON object per page. A row group
that already has its file is skipped, so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import concurrent.futures as cf
import gzip
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

DEV_DIR = Path(__file__).resolve().parent
if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))
import eval_doclaynet as ev  # noqa: E402

FACTS_VERSION = 1
SUBSETS = ("tune", "val", "test")  # never "holdout"
NEAR_PICTURE = 60.0       # pt around a Picture within which drawings are kept
MAX_DRAWINGS = 5000       # drawings kept per page (the rest are counted, not stored)
_LETTER_WORD_RE = re.compile(r"^[^\w]*[A-Za-z][A-Za-z'\u2019-]+[^\w]*$")
_WORD_RE = re.compile(r"[A-Za-z]{2,}")


# ==============================================================================
# Pure helpers (no PyMuPDF objects; unit-tested in tests\test_doclaynet_stats.py)
# ==============================================================================


def r2(rect) -> list[float]:
    return [round(float(v), 2) for v in rect[:4]]


def centre(b) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def inside(p: tuple[float, float], b, pad: float = 0.0) -> bool:
    return b[0] - pad <= p[0] <= b[2] + pad and b[1] - pad <= p[1] <= b[3] + pad


def overlap(a, b) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def assign_gt(rect, gt: list[dict]) -> tuple[str, int, float]:
    """(class, index, share of `rect` inside that box) of the DocLayNet box holding `rect`.

    The box holding the centre wins (largest overlap if several); otherwise the box with the largest overlap;
    ("none", -1, 0.0) when `rect` touches no box.
    """
    c = centre(rect)
    a = max(1e-6, area(rect))
    best = ("none", -1, 0.0)
    for k, g in enumerate(gt):
        if inside(c, g["r"]):
            share = overlap(rect, g["r"]) / a
            if best[1] < 0 or not inside(c, gt[best[1]]["r"]) or share > best[2]:
                best = (g["c"], k, share)
    if best[1] >= 0:
        return best[0], best[1], round(best[2], 3)
    for k, g in enumerate(gt):
        share = overlap(rect, g["r"]) / a
        if share > best[2]:
            best = (g["c"], k, share)
    return best[0], best[1], round(best[2], 3)


def widest_word_gap(words: list[tuple], drawings: list[tuple]) -> float:
    """Widest empty gap (pt) between two neighbouring full-height words of letters on one visual row.

    `words` are (x0, y0, x1, y1, text); `drawings` (x0, y0, x1, y1). A gap counts only if no word of any size and no
    vector drawing lies in it, so maths with sub/superscripts, fractions or outlined glyphs makes no fake gap.
    """
    rows: list[dict] = []
    for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        cy, h = (w[1] + w[3]) / 2, max(1.0, w[3] - w[1])
        for r in rows:
            if abs(r["cy"] - cy) < 0.5 * min(h, r["h"]):
                r["w"].append(w)
                break
        else:
            rows.append({"cy": cy, "h": h, "w": [w]})
    heights = sorted(w[3] - w[1] for w in words)
    full = 0.75 * heights[len(heights) // 2] if heights else 0.0
    best = 0.0
    for r in rows:
        ws = sorted(r["w"], key=lambda w: w[0])
        top, bot = min(w[1] for w in ws), max(w[3] for w in ws)
        fw = [w for w in ws if w[3] - w[1] >= full]
        for a, b in zip(fw, fw[1:]):
            if b[0] - a[2] <= best or not (_LETTER_WORD_RE.match(a[4]) and _LETTER_WORD_RE.match(b[4])):
                continue
            x0, x1 = a[2] + 0.5, b[0] - 0.5
            if any(w[0] < x1 and w[2] > x0 and min(w[3], bot) - max(w[1], top) > 0.5 * (w[3] - w[1]) for w in words):
                continue
            if any(d[0] < x1 and d[2] > x0 and d[1] < bot - 1 and d[3] > top + 1 for d in drawings):
                continue
            best = b[0] - a[2]
    return best


def block_features(text: str, rect, words: int, line_sizes: list[tuple], page_size: float, page_font: str,
                   pw: float) -> dict:
    """The eight main-text features of `main_text.main_text_score`, kept one by one.

    `line_sizes` are (bbox, {size: chars}, {font: chars}) of the PDF lines whose centre lies in the block.
    """
    sizes: collections.Counter = collections.Counter()
    fonts: collections.Counter = collections.Counter()
    for _, s, f in line_sizes:
        sizes.update(s)
        fonts.update(f)
    size = sizes.most_common(1)[0][0] if sizes else 0.0
    font = fonts.most_common(1)[0][0] if fonts else ""
    rows: list[list[float]] = []
    for bbox, _, _ in sorted(line_sizes, key=lambda ln: ln[0][1]):
        if rows and abs(rows[-1][3] - bbox[3]) < 0.5 * max(1.0, bbox[3] - bbox[1]):
            continue
        rows.append(list(bbox))
    text = text.strip()
    toks = text.split()
    return {
        "size": size,
        "width_rel": round((rect[2] - rect[0]) / pw, 4) if pw else 0.0,
        "chars_per_line": round(len(text) / max(1, len(rows)), 2),
        "lower_frac": round(sum(1 for w in toks if w[:1].islower()) / max(1, len(toks)), 4),
        "alpha_frac": round(sum(1 for w in toks if _WORD_RE.search(w)) / max(1, len(toks)), 4),
        "digit_frac": round(sum(ch.isdigit() for ch in text) / max(1, len(text)), 4),
        "same_font": 1 if font == page_font else 0,
        "size_rel": round(size / page_size, 4) if page_size else 0.0,
    }


# ==============================================================================
# Page facts (worker process)
# ==============================================================================


def _worker_init() -> None:
    if str(ev.SRC_DIR) not in sys.path:
        sys.path.insert(0, str(ev.SRC_DIR))
    os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")


def _gt_boxes(rec: dict) -> list[dict]:
    m = rec["metadata"]
    cw, ch, pw, ph = m["coco_width"], m["coco_height"], m["original_width"], m["original_height"]
    out = []
    cells_per_box = rec["pdf_cells"] or [[] for _ in rec["bboxes"]]
    for b, c, cells in zip(rec["bboxes"], rec["category_id"], cells_per_box):
        cls = ev.CLASS_NAMES.get(c, str(c))
        g = {"c": cls, "r": r2(ev.coco_to_pdf(b, cw, ch, pw, ph)), "n": len(cells or [])}
        if cls in ("Picture", "Caption"):
            g["cells"] = [
                [cell["text"], r2(ev.coco_to_pdf(cell["bbox"], cw, ch, pw, ph)), round(cell["font"]["size"] or 0.0, 2)]
                for cell in cells or []
            ]
        out.append(g)
    return out


def page_facts(rec: dict, entry: dict, page=None, running_heads=None) -> dict:
    """All facts of one DocLayNet page.

    By default the page is DocLayNet's one-page PDF, read without document context. `page` (the same page in the full
    original PDF) and `running_heads` (its repeated heads, `running_heads.find_running_heads`) give the context the
    tool has when it translates a whole document.
    """
    import pymupdf
    from figure_detector.main_text import _page_lines, main_text_score
    from figure_detector.model import _SECTION_HEADING_RE, DEFAULT_CONFIG as cfg
    from figure_detector.pipeline import _is_label_row, _label_lines
    from figure_detector.raster import _image_ink_rect
    from figure_detector.text import _clean_text, _is_short_axis_label, analyze_page

    m = rec["metadata"]
    out = {k: entry[k] for k in ("split", "subset", "doc", "page_no", "page_hash")}
    out["collection"] = m["collection"]
    gt = _gt_boxes(rec)
    out["gt"] = gt
    own = page is None
    with (pymupdf.open(stream=rec["pdf"], filetype="pdf") if own else contextlib.nullcontext()) as doc:
        if own:
            page = doc[0]
        out["w"], out["h"] = round(page.rect.width, 2), round(page.rect.height, 2)
        out["gt_w"], out["gt_h"] = m["original_width"], m["original_height"]
        if page.rotation % 360:
            out["skipped"] = "rotated"
            return out
        ctx = analyze_page(page, cfg=cfg)
        ctx.running_heads = list(running_heads or [])
        pdf_lines, page_size, page_font = _page_lines(page)
        out["page_size"], out["page_font"] = page_size, page_font
        drawings = [d["rect"] for d in ctx.drawings]

        # --- text blocks --------------------------------------------------------------------------------------
        blocks = []
        for tb in ctx.text_blocks:
            box = tb.rect + (-0.5, -0.5, 0.5, 0.5)
            mine = [ln for ln in pdf_lines if box.contains(pymupdf.Point(*centre(ln[0])))]
            feats = block_features(tb.text, tb.rect, tb.word_count, mine, page_size, page_font, ctx.pw)
            ws = [w[:5] for w in ctx.words if box.contains(pymupdf.Point(*centre(w)))]
            near = [tuple(d) for d in drawings if d.intersects(tb.rect)]
            gap = widest_word_gap(ws, near) if feats["size"] > 0 else 0.0
            cls, gi, share = assign_gt(tb.rect, gt)
            cleaned = _clean_text(tb.text)
            blocks.append({
                "r": r2(tb.rect), "kind": tb.kind, "wc": tb.word_count, "rows": tb.rows, "text": cleaned[:160],
                "f": feats,
                "score": main_text_score(tb.text, tb.rect, tb.word_count, mine, page_size, page_font, ctx.pw),
                "gap": round(gap, 2), "gap_em": round(gap / feats["size"], 3) if feats["size"] > 0 else 0.0,
                "short_axis": _is_short_axis_label(tb, vertical_ok=True), "label_row": _is_label_row(tb, cfg),
                "heading_re": bool(_SECTION_HEADING_RE.match(cleaned)), "period": cleaned.endswith("."),
                "gt": cls, "gi": gi, "share": share,
            })
        out["blocks"] = blocks

        # --- text lines, as the label steps see them (words grouped by PyMuPDF block/line) ---------------------
        groups: dict[tuple[int, int], list] = {}
        for w in ctx.words:
            groups.setdefault((w[5], w[6]), []).append(w)
        label_like = {tuple(round(v, 1) for v in r) for r, _ in _label_lines(ctx)}
        lines = []
        for ws in groups.values():
            r = pymupdf.Rect(ws[0][:4])
            for w in ws[1:]:
                r |= pymupdf.Rect(w[:4])
            c = pymupdf.Point(*centre(r))
            owner = next((i for i, tb in enumerate(ctx.text_blocks) if (tb.rect + (-0.5, -0.5, 0.5, 0.5)).contains(c)), -1)
            sizes: collections.Counter = collections.Counter()
            for bbox, s, _ in pdf_lines:
                if inside(centre(bbox), r, 0.5) or inside(centre(r), bbox, 0.5):
                    sizes.update(s)
            cls, gi, share = assign_gt(r, gt)
            lines.append({
                "r": r2(r), "nw": len(ws), "text": " ".join(w[4] for w in ws)[:100],
                "size": sizes.most_common(1)[0][0] if sizes else 0.0, "owner": owner,
                "label_like": tuple(round(v, 1) for v in r) in label_like,
                "gt": cls, "gi": gi, "share": share,
            })
        out["lines"] = lines

        # --- images: placement box and the white-margin trim the tool would compute ----------------------------
        has_xobjects = bool(page.get_images(full=False))
        infos = page.get_image_info(xrefs=has_xobjects)
        images = []
        for info in infos:
            pr = pymupdf.Rect(info["bbox"]) & page.rect
            if pr.is_empty:
                continue
            ink = None
            if has_xobjects and len(infos) <= cfg.raster_trim_max_images and pr.get_area() >= cfg.min_raster_area:
                ink_rect = _image_ink_rect(ctx, info, cfg)
                if ink_rect is not None:
                    ink = r2(ink_rect & pr) if not (ink_rect & pr).is_empty else []
            cls, gi, share = assign_gt(pr, gt)
            images.append({"r": r2(pr), "ink": ink, "px": [info.get("width"), info.get("height")],
                           "gt": cls, "gi": gi, "share": share})
        out["images"] = images

        # --- drawings near Pictures: clip-cut rect, drawn rect (when the clip cut it), type, stroke width ------------
        pics = [g["r"] for g in gt if g["c"] == "Picture"]
        pic_idx = [k for k, g in enumerate(gt) if g["c"] == "Picture"]
        kept, dropped = [], 0
        overflow: dict[int, list] = {}  # Picture index -> [union rect of the drawings past the cap, count]
        if pics:
            zones = [(p[0] - NEAR_PICTURE, p[1] - NEAR_PICTURE, p[2] + NEAR_PICTURE, p[3] + NEAR_PICTURE) for p in pics]
            for d in ctx.drawings:
                r = d["rect"]
                if not any(r.x1 >= z[0] and r.x0 <= z[2] and r.y1 >= z[1] and r.y0 <= z[3] for z in zones):
                    continue
                if len(kept) >= MAX_DRAWINGS:
                    dropped += 1
                    c = centre(r)
                    for k, p in zip(pic_idx, pics):
                        if inside(c, p):
                            o = overflow.setdefault(k, [[r.x0, r.y0, r.x1, r.y1], 0])
                            o[0] = [min(o[0][0], r.x0), min(o[0][1], r.y0), max(o[0][2], r.x1), max(o[0][3], r.y1)]
                            o[1] += 1
                            break
                    continue
                u = d.get("unclipped_rect")
                u = r2(u) if u is not None and r2(u) != r2(r) else None  # only when the clip cut the path
                kept.append([r2(r), u, d.get("type"),
                             round(d.get("width") or 0.0, 2), len(d.get("items") or ())])
        out["drawings"] = kept
        out["drawings_dropped"] = dropped
        out["drawings_overflow"] = [[r2(o[0]), k, o[1]] for k, o in overflow.items()]
        out["n_drawings_page"] = len(ctx.drawings)
    return out


def _run_group(file: str, rg: int, entries: list[dict], out_path: str) -> tuple[str, int, int]:
    import pyarrow.parquet as pq

    rows = pq.ParquetFile(file).read_row_group(rg, columns=["metadata", "bboxes", "category_id", "pdf_cells", "pdf"]).to_pylist()
    tmp = out_path + ".tmp"
    errors = 0
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for e in entries:
            t0 = time.perf_counter()
            try:
                facts = page_facts(rows[e["row"]], e)
            except Exception as exc:  # noqa: BLE001 - one broken page must not stop a 14k-page run
                facts = {k: e[k] for k in ("split", "subset", "doc", "page_no", "page_hash")}
                facts["error"] = f"{type(exc).__name__}: {exc}"
                facts["traceback"] = traceback.format_exc(limit=4)
                errors += 1
            facts["seconds"] = round(time.perf_counter() - t0, 3)
            fh.write(json.dumps(facts, ensure_ascii=False) + "\n")
    os.replace(tmp, out_path)
    return out_path, len(entries), errors


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ev.REPO_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "?"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True, help="Folder holding DocLayNet-train/-val/-test")
    ap.add_argument("--subset", action="append", choices=SUBSETS, help="Repeatable; default: tune")
    ap.add_argument("--limit", type=int, default=0, help="Random sample of N pages (0 = all); written to a separate folder")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "luka_doclaynet_eval")
    args = ap.parse_args(argv)

    subsets = args.subset or ["tune"]
    index = ev.build_index(args.data, args.cache_dir)
    entries = [e for e in index if e["subset"] in subsets]
    if args.limit and args.limit < len(entries):
        entries = sorted(random.Random(args.seed).sample(entries, args.limit), key=lambda e: (e["file"], e["rg"], e["row"]))
    folder = args.cache_dir / "facts" / (f"v{FACTS_VERSION}" + (f"-n{args.limit}s{args.seed}" if args.limit else ""))
    folder.mkdir(parents=True, exist_ok=True)
    groups: dict[tuple[str, int], list[dict]] = collections.defaultdict(list)
    for e in entries:
        groups[(e["file"], e["rg"])].append(e)
    todo = {}
    for (f, g), es in groups.items():
        path = folder / f"{es[0]['split']}_{Path(f).stem}_rg{g}.jsonl.gz"
        if not path.is_file():
            todo[(f, g)] = (es, str(path))
    meta = {"facts_version": FACTS_VERSION, "git_head": _git_head(), "detector_fingerprint": ev.detector_fingerprint([]),
            "subsets": subsets, "limit": args.limit, "seed": args.seed}
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    n_todo = sum(len(es) for es, _ in todo.values())
    print(f"{len(entries)} pages in {len(groups)} row groups; {len(groups) - len(todo)} groups done, "
          f"{n_todo} pages to read with {args.workers} worker(s) -> {folder}", flush=True)
    t0, done, errors = time.time(), 0, 0
    with cf.ProcessPoolExecutor(max_workers=args.workers, initializer=_worker_init) as pool:
        futures = [pool.submit(_run_group, f, g, es, path) for (f, g), (es, path) in todo.items()]
        for fut in cf.as_completed(futures):
            _, n, err = fut.result()
            done += n
            errors += err
            print(f"  {done}/{n_todo} pages ({done / max(1e-6, time.time() - t0):.1f} pages/s, {errors} errors)", flush=True)
    print(f"Done in {time.time() - t0:.0f} s, {errors} page errors")


if __name__ == "__main__":
    main()
