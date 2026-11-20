"""Evaluate figure extraction against DocLayNet v1.2 ground truth (scientific_articles only). Dev-only tool.

DocLayNet v1.2 (Hugging Face parquet) embeds a one-page PDF per annotated page, so the real detector
(`figure_detector`, the same code that ships in extract_assets.exe) runs on the original vector/text content
and its figure boxes are compared with the human-annotated `Picture` boxes.

Splits used here:
  tune     DocLayNet train, documents NOT in the hold-out  -> look at errors, tune rules here
  holdout  ~20% of train documents, chosen by a fixed hash -> measure only; never inspect pages (no overlays)
  val/test DocLayNet val/test                              -> the detector was historically tuned on these

Examples (system Python with pyarrow + PyMuPDF; the dataset never enters the repository):
  python dev\\eval_doclaynet.py --data D:\\PdfSamples --subset tune
  python dev\\eval_doclaynet.py --data D:\\PdfSamples --subset tune --limit 500 --overlays 20
  python dev\\eval_doclaynet.py --data D:\\PdfSamples --subset val --subset test
  python dev\\eval_doclaynet.py --data D:\\PdfSamples --subset tune --disable-rule _reject_too_small

Per-page results are cached per detector fingerprint (hash of tools\\src\\figure_detector\\*.py, image_ops.py and
the disabled rules), so a re-run after a code change recomputes everything and a re-run without changes is instant.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import os
import random
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "tools" / "src"

SPLIT_DIRS = {"train": "DocLayNet-train", "val": "DocLayNet-val", "test": "DocLayNet-test"}
SUBSETS = ("tune", "holdout", "val", "test")
CLASS_NAMES = {
    1: "Caption", 2: "Footnote", 3: "Formula", 4: "List-item", 5: "Page-footer", 6: "Page-header",
    7: "Picture", 8: "Section-header", 9: "Table", 10: "Text", 11: "Title",
}
PICTURE = 7
SCIENTIFIC = "scientific_articles"

HOLDOUT_SALT = "luka-loop/doclaynet-holdout/v1"
HOLDOUT_PERCENT = 20

# Matching thresholds. Our boxes are deliberately larger than the annotation (4 pt render padding is NOT
# included here, but axis-label/tick expansion is), hence the lenient criterion next to plain IoU >= 0.5.
STRICT_IOU = 0.5
LENIENT_GT_COVER = 0.9       # prediction covers >= 90% of the ground-truth box ...
LENIENT_MAX_GROWTH = 2.0     # ... and is at most 2x its area
PART_COVER = 0.5             # "mostly inside" for merge/split/fragment attribution

Box = tuple[float, float, float, float]


# ==============================================================================
# Pure helpers (no pyarrow / PyMuPDF; unit-tested in tests\test_eval_doclaynet.py)
# ==============================================================================


def is_holdout(doc_name: str) -> bool:
    """Deterministic document-level hold-out membership (~HOLDOUT_PERCENT % of documents)."""
    digest = hashlib.sha256(f"{HOLDOUT_SALT}:{doc_name}".encode("utf-8")).hexdigest()
    return int(digest, 16) % 100 < HOLDOUT_PERCENT


def subset_of(split: str, doc_name: str) -> str:
    if split != "train":
        return split
    return "holdout" if is_holdout(doc_name) else "tune"


def coco_to_pdf(bbox: list[float], coco_w: float, coco_h: float, page_w: float, page_h: float) -> Box:
    """DocLayNet `[x, y, w, h]` in the stretched coco_w x coco_h image -> PDF points (scaled per axis)."""
    x, y, w, h = bbox
    sx, sy = page_w / coco_w, page_h / coco_h
    return (x * sx, y * sy, (x + w) * sx, (y + h) * sy)


def area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def intersection(a: Box, b: Box) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def iou(a: Box, b: Box) -> float:
    inter = intersection(a, b)
    union = area(a) + area(b) - inter
    return inter / union if union > 0 else 0.0


def coverage(inner: Box, outer: Box) -> float:
    """Fraction of `inner`'s area that lies inside `outer`."""
    a = area(inner)
    return intersection(inner, outer) / a if a > 0 else 0.0


def is_strict_match(pred: Box, gt: Box) -> bool:
    return iou(pred, gt) >= STRICT_IOU


def is_lenient_match(pred: Box, gt: Box) -> bool:
    return is_strict_match(pred, gt) or (
        coverage(gt, pred) >= LENIENT_GT_COVER and area(pred) <= LENIENT_MAX_GROWTH * area(gt)
    )


def greedy_match(preds: list[Box], gts: list[Box], accept) -> list[tuple[int, int]]:
    """One-to-one matching, highest IoU first, among pairs accepted by `accept(pred, gt)`."""
    pairs = sorted(
        ((iou(p, g), i, j) for i, p in enumerate(preds) for j, g in enumerate(gts) if accept(p, g)),
        reverse=True,
    )
    used_p, used_g, out = set(), set(), []
    for _, i, j in pairs:
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
            out.append((i, j))
    return out


def evaluate_page(preds: list[Box], gts: list[Box], others: list[tuple[str, Box]]) -> dict:
    """Score one page. `others` are the non-Picture ground-truth boxes as (class name, box).

    Returns strict/lenient TP counts plus one outcome per unmatched box:
      GT:   'merged' (one prediction swallowed it together with another picture), 'split' (>= 2 predictions
            inside it), 'partial' (one prediction too small/off), 'missed' (nothing overlaps)
      pred: 'merge' (covers >= 2 pictures), 'fragment' (lies inside a picture), 'fp_<class>' (mostly inside
            a Table/Formula/Text/... box), 'fp_unlabeled' (on nothing annotated)
    """
    strict = greedy_match(preds, gts, is_strict_match)
    lenient = greedy_match(preds, gts, is_lenient_match)
    matched_p = {i for i, _ in lenient}
    matched_g = {j for _, j in lenient}

    pred_outcomes: dict[int, str] = {}
    gt_outcomes: dict[int, str] = {}
    for i, p in enumerate(preds):
        if i in matched_p:
            continue
        swallowed = [j for j, g in enumerate(gts) if coverage(g, p) >= PART_COVER]
        if len(swallowed) >= 2:
            pred_outcomes[i] = "merge"
            for j in swallowed:
                if j not in matched_g:
                    gt_outcomes[j] = "merged"
            continue
        if any(coverage(p, g) >= PART_COVER for g in gts):
            pred_outcomes[i] = "fragment"
            continue
        best_cls, best_cov = "unlabeled", 0.0
        for cls, b in others:
            c = coverage(p, b)
            if c > best_cov:
                best_cls, best_cov = cls, c
        pred_outcomes[i] = f"fp_{best_cls if best_cov >= PART_COVER else 'unlabeled'}"

    for j, g in enumerate(gts):
        if j in matched_g or j in gt_outcomes:
            continue
        inside = [i for i, p in enumerate(preds) if coverage(p, g) >= PART_COVER]
        if len(inside) >= 2:
            gt_outcomes[j] = "split"
        elif inside or any(intersection(p, g) > 0 for p in preds):
            gt_outcomes[j] = "partial"
        else:
            gt_outcomes[j] = "missed"

    return {
        "n_pred": len(preds),
        "n_gt": len(gts),
        "tp_strict": len(strict),
        "tp_lenient": len(lenient),
        "matched": sorted(lenient),
        "gt_outcomes": {str(k): v for k, v in sorted(gt_outcomes.items())},
        "pred_outcomes": {str(k): v for k, v in sorted(pred_outcomes.items())},
    }


def prf(tp: int, n_pred: int, n_gt: int) -> dict:
    precision = tp / n_pred if n_pred else 1.0
    recall = tp / n_gt if n_gt else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if "error" not in r]
    tot = collections.Counter()
    gt_out, pred_out = collections.Counter(), collections.Counter()
    by_source = collections.defaultdict(collections.Counter)
    matched_ious: list[float] = []
    for r in ok:
        ev = r["eval"]
        tot.update({k: ev[k] for k in ("n_pred", "n_gt", "tp_strict", "tp_lenient")})
        matched_ious += [iou(tuple(r["preds"][i]), tuple(r["gts"][j])) for i, j in ev["matched"]]
        gt_out.update(ev["gt_outcomes"].values())
        pred_out.update(ev["pred_outcomes"].values())
        matched_p = {i for i, _ in ev["matched"]}
        for i, meta in enumerate(r["pred_meta"]):
            key = meta["source"] + ("+caption" if meta["captioned"] else "")
            by_source[key]["pred"] += 1
            by_source[key]["tp"] += i in matched_p
    pages_with_gt = sum(1 for r in ok if r["eval"]["n_gt"])
    return {
        "pages": len(results),
        "page_errors": len(results) - len(ok),
        "pages_with_pictures": pages_with_gt,
        "pages_without_pictures_but_predictions": sum(1 for r in ok if not r["eval"]["n_gt"] and r["eval"]["n_pred"]),
        "gt_pictures": tot["n_gt"],
        "predictions": tot["n_pred"],
        "strict_iou50": prf(tot["tp_strict"], tot["n_pred"], tot["n_gt"]),
        "lenient": prf(tot["tp_lenient"], tot["n_pred"], tot["n_gt"]),
        "matched_iou_mean": round(sum(matched_ious) / len(matched_ious), 4) if matched_ious else None,
        "matched_iou_below_0_8": sum(1 for v in matched_ious if v < 0.8),
        "unmatched_gt": dict(gt_out.most_common()),
        "unmatched_pred": dict(pred_out.most_common()),
        "precision_by_source": {
            k: {"pred": v["pred"], "tp": v["tp"], "precision": round(v["tp"] / v["pred"], 4)}
            for k, v in sorted(by_source.items())
        },
        "seconds_per_page": round(sum(r.get("seconds", 0.0) for r in results) / max(1, len(results)), 3),
    }


# ==============================================================================
# Dataset access (pyarrow) and detector runs (PyMuPDF), imported lazily
# ==============================================================================


def detector_fingerprint(disabled_rules: list[str]) -> str:
    h = hashlib.sha256()
    for p in sorted((SRC_DIR / "figure_detector").glob("*.py")) + [SRC_DIR / "image_ops.py"]:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    h.update(json.dumps(sorted(disabled_rules)).encode())
    return h.hexdigest()[:16]


def build_index(data_root: Path, cache_dir: Path) -> list[dict]:
    """Scientific pages of all splits as (split, subset, file, row group, row, doc, page_no, page_hash)."""
    cache = cache_dir / "scientific_index.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    import pyarrow.parquet as pq

    index = []
    for split, folder in SPLIT_DIRS.items():
        files = sorted((data_root / folder / "_parquet" / "data").glob("*.parquet"))
        if not files:
            raise SystemExit(f"No parquet files for split '{split}' under {data_root / folder}")
        for f in files:
            pf = pq.ParquetFile(f)
            for g in range(pf.num_row_groups):
                for row, rec in enumerate(pf.read_row_group(g, columns=["metadata", "category_id"]).to_pylist()):
                    m = rec["metadata"]
                    if m["doc_category"] != SCIENTIFIC:
                        continue
                    index.append({
                        "split": split, "subset": subset_of(split, m["original_filename"]),
                        "file": str(f), "rg": g, "row": row, "doc": m["original_filename"],
                        "page_no": m["page_no"], "page_hash": m["page_hash"],
                        "n_picture": (rec["category_id"] or []).count(PICTURE),
                    })
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(index), encoding="utf-8")
    return index


def _worker_init(disabled_rules: list[str]) -> None:
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")
    if disabled_rules:
        import figure_detector.vector as vec

        vec._VECTOR_CLUSTER_RULES = tuple(r for r in vec._VECTOR_CLUSTER_RULES if r.__name__ not in disabled_rules)


def _run_group(file: str, rg: int, entries: list[dict]) -> list[dict]:
    """Evaluate the requested rows of one parquet row group (runs in a worker process)."""
    import pyarrow.parquet as pq
    import pymupdf
    from figure_detector.extract import _detect_table_placement
    from figure_detector.pipeline import _run_page_pipeline

    table = pq.ParquetFile(file).read_row_group(rg, columns=["metadata", "bboxes", "category_id", "pdf"])
    rows = table.to_pylist()
    out = []
    for e in entries:
        rec = rows[e["row"]]
        res = {k: e[k] for k in ("split", "subset", "file", "rg", "row", "doc", "page_no", "page_hash")}
        t0 = time.perf_counter()
        try:
            m = rec["metadata"]
            with pymupdf.open(stream=rec["pdf"], filetype="pdf") as doc:
                page = doc[0]
                pr = page.rect
                conv = [coco_to_pdf(b, m["coco_width"], m["coco_height"], pr.width, pr.height) for b in rec["bboxes"]]
                conv = [(b[0] + pr.x0, b[1] + pr.y0, b[2] + pr.x0, b[3] + pr.y0) for b in conv]
                gts = [b for b, c in zip(conv, rec["category_id"]) if c == PICTURE]
                others = [(CLASS_NAMES.get(c, str(c)), b) for b, c in zip(conv, rec["category_id"]) if c != PICTURE]
                ctx, candidates, is_scanned = _run_page_pipeline(page)
                tables = [t.rect for t in ctx.get_page_tables()] if any(c.caption_idx is None for c in candidates) else []
                preds = [tuple(c.rect) for c in candidates]
                res["pred_meta"] = [
                    {
                        "source": c.source,
                        "captioned": c.caption_idx is not None,
                        "placement": _detect_table_placement(candidates, k, ctx, tables),
                    }
                    for k, c in enumerate(candidates)
                ]
                res["preds"] = [[round(v, 2) for v in p] for p in preds]
                res["gts"] = [[round(v, 2) for v in g] for g in gts]
                res["is_scanned"] = is_scanned
                res["eval"] = evaluate_page(preds, gts, others)
        except Exception as exc:  # noqa: BLE001 - one broken page must not stop a 12k-page run
            res["error"] = f"{type(exc).__name__}: {exc}"
            res["traceback"] = traceback.format_exc(limit=3)
        res["seconds"] = round(time.perf_counter() - t0, 3)
        out.append(res)
    return out


def run_pages(entries: list[dict], disabled: list[str], workers: int, cache_file: Path) -> list[dict]:
    cached: dict[str, dict] = {}
    if cache_file.is_file():
        for line in cache_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                cached[r["page_hash"]] = r
    todo = [e for e in entries if e["page_hash"] not in cached]
    groups: dict[tuple[str, int], list[dict]] = collections.defaultdict(list)
    for e in todo:
        groups[(e["file"], e["rg"])].append(e)
    print(f"{len(entries)} pages selected, {len(entries) - len(todo)} cached, {len(todo)} to run "
          f"in {len(groups)} row groups with {workers} worker(s)", flush=True)
    if groups:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        t0, done = time.time(), 0
        with cache_file.open("a", encoding="utf-8") as fh, cf.ProcessPoolExecutor(
            max_workers=workers, initializer=_worker_init, initargs=(disabled,)
        ) as pool:
            futures = [pool.submit(_run_group, f, g, es) for (f, g), es in groups.items()]
            for fut in cf.as_completed(futures):
                for r in fut.result():
                    cached[r["page_hash"]] = r
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    done += 1
                fh.flush()
                rate = done / max(1e-6, time.time() - t0)
                print(f"  {done}/{len(todo)} pages ({rate:.1f} pages/s)", flush=True)
    return [cached[e["page_hash"]] for e in entries]


def _error_weight(r: dict) -> int:
    if "error" in r:
        return 1000
    ev = r["eval"]
    return len(ev["gt_outcomes"]) + len(ev["pred_outcomes"])


def write_overlays(results: list[dict], out_dir: Path, limit: int) -> list[Path]:
    """Render the `limit` worst pages with GT pictures (green) and predictions (red) for visual review."""
    import pyarrow.parquet as pq
    import pymupdf

    worst = sorted((r for r in results if _error_weight(r) and "error" not in r), key=_error_weight, reverse=True)[:limit]
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for rank, r in enumerate(worst, 1):
        rec = pq.ParquetFile(r["file"]).read_row_group(r["rg"], columns=["pdf"]).to_pylist()[r["row"]]
        with pymupdf.open(stream=rec["pdf"], filetype="pdf") as doc:
            page = doc[0]
            for j, g in enumerate(r["gts"]):
                outcome = r["eval"]["gt_outcomes"].get(str(j), "tp")
                page.draw_rect(pymupdf.Rect(g), color=(0, 0.6, 0), width=2.2)
                page.insert_text((g[0] + 2, g[1] + 9), f"GT {outcome}", fontsize=7, color=(0, 0.5, 0))
            for i, p in enumerate(r["preds"]):
                outcome = r["eval"]["pred_outcomes"].get(str(i), "tp")
                meta = r["pred_meta"][i]
                page.draw_rect(pymupdf.Rect(p), color=(0.85, 0, 0), width=1.2, dashes="[3] 0")
                page.insert_text((p[0] + 2, p[3] - 3), f"P{i} {outcome} {meta['source']}", fontsize=7, color=(0.8, 0, 0))
            path = out_dir / f"{rank:03d}_{Path(r['doc']).stem}_p{r['page_no']}.png"
            page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(path)
            written.append(path)
    return written


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True, help="Folder holding DocLayNet-train/-val/-test")
    ap.add_argument("--subset", action="append", choices=SUBSETS, help="Repeatable; default: tune")
    ap.add_argument("--limit", type=int, default=0, help="Random sample of N pages (0 = all)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--disable-rule", action="append", default=[], help="Ablation: drop a _VECTOR_CLUSTER_RULES entry")
    ap.add_argument("--overlays", type=int, default=0, help="Render the N worst pages (not allowed on holdout)")
    ap.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "luka_doclaynet_eval")
    ap.add_argument("--out", type=Path, default=None, help="Run folder (default: <cache-dir>/runs/<name>)")
    args = ap.parse_args(argv)

    subsets = args.subset or ["tune"]
    if args.overlays and "holdout" in subsets:
        ap.error("--overlays is not allowed on the holdout subset: inspecting it would turn it into tuning data")
    if args.disable_rule:
        sys.path.insert(0, str(SRC_DIR))
        import figure_detector.vector as vec

        known = {r.__name__ for r in vec._VECTOR_CLUSTER_RULES}
        unknown = sorted(set(args.disable_rule) - known)
        if unknown:
            ap.error(f"unknown rule(s) {unknown}; known: {sorted(known)}")

    index = build_index(args.data, args.cache_dir)
    entries = [e for e in index if e["subset"] in subsets]
    if args.limit and args.limit < len(entries):
        entries = sorted(random.Random(args.seed).sample(entries, args.limit), key=lambda e: (e["file"], e["rg"], e["row"]))

    fp = detector_fingerprint(args.disable_rule)
    results = run_pages(entries, args.disable_rule, args.workers, args.cache_dir / "pages" / f"{fp}.jsonl")

    name = "+".join(subsets) + (f"-n{args.limit}s{args.seed}" if args.limit else "") + f"-{fp}"
    out = args.out or args.cache_dir / "runs" / name
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "subsets": subsets, "limit": args.limit, "seed": args.seed, "detector_fingerprint": fp,
        "disabled_rules": args.disable_rule, **summarize(results),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    worst = sorted(results, key=_error_weight, reverse=True)[:50]
    (out / "worst_pages.json").write_text(json.dumps([
        {k: r.get(k) for k in ("subset", "doc", "page_no", "page_hash", "error")}
        | ({"gt": r["eval"]["gt_outcomes"], "pred": r["eval"]["pred_outcomes"]} if "eval" in r else {})
        for r in worst
    ], indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    if args.overlays:
        paths = write_overlays(results, out / "overlays", args.overlays)
        print(f"Wrote {len(paths)} overlay(s) -> {out / 'overlays'}")
    print(f"Run folder -> {out}")


if __name__ == "__main__":
    main()
