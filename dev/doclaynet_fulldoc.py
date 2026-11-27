"""DocLayNet pages read inside their full original arXiv paper (no-upload-dev/arxiv-b1, no-upload-dev/arxiv-b2). Dev-only tool.

DocLayNet gives every page as a one-page PDF, so the tool never has the document context it has when it translates
a whole paper: repeated running heads cannot be found, and the label steps fall back to fixed page bands. For the
papers whose original PDF is kept locally, this script

  1. finds the running heads of the whole paper with the tool's own `find_running_heads` and compares them, page by
     page, with the Page-header / Page-footer boxes DocLayNet annotated;
  2. writes the same facts as `dev/doclaynet_facts.py`, but read from the full paper's page with its running heads,
     so `dev/doclaynet_stats.py --facts fulldoc-v<N>` shows what changes with document context.

A DocLayNet page is matched to the full paper's page `page_no` (0-based) only when their words agree (Jaccard >= 0.8);
pages of a different arXiv version are skipped and counted. Only tune documents are used (never holdout).

Example:
  python -X utf8 dev\\doclaynet_fulldoc.py --data D:\\PdfSamples
  python -X utf8 dev\\doclaynet_stats.py --facts fulldoc-v1
  python -X utf8 dev\\doclaynet_stats.py --docs work-dev\\doclaynet_stats\\fulldoc_docs.txt
Output: <cache>\\facts\\fulldoc-v1\\*.jsonl.gz, work-dev\\doclaynet_stats\\fulldoc_heads.md (+ .json), fulldoc_docs.txt
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import gzip
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

DEV_DIR = Path(__file__).resolve().parent
if str(DEV_DIR) not in sys.path:
    sys.path.insert(0, str(DEV_DIR))
import doclaynet_facts as F  # noqa: E402
import eval_doclaynet as ev  # noqa: E402

REPO_ROOT = DEV_DIR.parent
PAPER_DIRS = (REPO_ROOT / "no-upload-dev" / "arxiv-b1", REPO_ROOT / "no-upload-dev" / "arxiv-b2")
MIN_JACCARD = 0.8
HEAD_CLASSES = ("Page-header", "Page-footer")


def _words(page) -> set[str]:
    return set(page.get_text("text").split())


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


def _head_matches(head, box, pad: float = 3.0) -> bool:
    """A detected head rect and an annotated box are the same thing: either centre lies in the other."""
    return F.inside(F.centre(head), box, pad) or F.inside(F.centre(box), head, pad)


def _paper_worker(paper: str, entries: list[dict], out_path: str) -> dict:
    """Facts + running-head comparison for the DocLayNet pages of one paper."""
    F._worker_init()
    import pyarrow.parquet as pq
    import pymupdf
    from figure_detector.pipeline import unrotated_page
    from figure_detector.running_heads import find_running_heads, page_edge_lines

    res = {"paper": os.path.basename(paper), "pages": 0, "mismatch": 0, "errors": 0, "heads": []}
    rows: dict[tuple[str, int], list] = {}
    with pymupdf.open(paper) as doc:
        edge = []
        for page in doc:
            with unrotated_page(page):
                edge.append(page_edge_lines(page))
        heads = find_running_heads(edge)
        tmp = out_path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            for e in entries:
                try:
                    key = (e["file"], e["rg"])
                    if key not in rows:
                        rows[key] = pq.ParquetFile(e["file"]).read_row_group(
                            e["rg"], columns=["bboxes", "category_id", "pdf_cells", "metadata", "pdf"]).to_pylist()
                    rec = rows[key][e["row"]]
                    k = e["page_no"]
                    if k >= len(doc):
                        res["mismatch"] += 1
                        continue
                    with pymupdf.open(stream=rec["pdf"], filetype="pdf") as one:
                        same = _jaccard(_words(one[0]), _words(doc[k])) >= MIN_JACCARD
                    if not same or doc[k].rotation % 360:
                        res["mismatch"] += 1
                        continue
                    page = doc[k]
                    facts = F.page_facts(rec, e, page=page, running_heads=heads[k])
                    facts["context"] = "fulldoc"
                    fh.write(json.dumps(facts, ensure_ascii=False) + "\n")
                    res["pages"] += 1
                    gt = facts["gt"]
                    res["heads"].append({
                        "doc": e["doc"], "page_no": k, "h": facts["h"],
                        "gt": [[g["c"], g["r"]] for g in gt if g["c"] in HEAD_CLASSES],
                        "found": [[F.r2(h)] + list(F.assign_gt(F.r2(h), gt)[:1]) for h in heads[k]],
                    })
                except Exception:  # noqa: BLE001
                    res["errors"] += 1
                    traceback.print_exc()
        os.replace(tmp, out_path)
    return res


def head_report(results: list[dict]) -> tuple[dict, list[str]]:
    gt_n = collections.Counter()
    gt_found = collections.Counter()
    gt_in_band = collections.Counter()
    found_cls = collections.Counter()
    pages_with_gt = pages_with_found = 0
    for r in results:
        for pg in r["heads"]:
            h = pg["h"]
            pages_with_gt += bool(pg["gt"])
            pages_with_found += bool(pg["found"])
            for cls, box in pg["gt"]:
                gt_n[cls] += 1
                gt_found[cls] += any(_head_matches(f[0], box) for f in pg["found"])
                top_band, bottom_band = 0.10 * h, 0.94 * h
                gt_in_band[cls] += box[3] <= top_band or box[1] >= bottom_band
            for f in pg["found"]:
                found_cls[f[1]] += 1
    n_found = sum(found_cls.values())
    ok = found_cls.get("Page-header", 0) + found_cls.get("Page-footer", 0)
    summary = {"gt": dict(gt_n), "gt_found": dict(gt_found), "gt_in_fixed_band": dict(gt_in_band),
               "found_by_class": dict(found_cls), "pages_with_gt": pages_with_gt, "pages_with_found": pages_with_found}
    L = ["# Đầu trang / chân trang trên bài gốc: công cụ so với nhãn DocLayNet", "",
         f"{sum(r['pages'] for r in results)} trang của {len(results)} bài (bỏ {sum(r['mismatch'] for r in results)} trang "
         f"khác phiên bản, {sum(r['errors'] for r in results)} lỗi). Đầu trang lặp lại tìm bằng `find_running_heads` trên "
         "cả bài, đúng như khi dịch.", "",
         "| khung DocLayNet | số khung | công cụ tìm thấy | tỷ lệ | nằm trong dải cố định 10% đầu / 6% cuối |",
         "| :--- | ---: | ---: | ---: | ---: |"]
    for cls in HEAD_CLASSES:
        n = gt_n.get(cls, 0)
        L.append(f"| {cls} | {n} | {gt_found.get(cls, 0)} | {round(100 * gt_found.get(cls, 0) / max(1, n), 1)}% | "
                 f"{gt_in_band.get(cls, 0)} ({round(100 * gt_in_band.get(cls, 0) / max(1, n), 1)}%) |")
    L += ["", f"Dòng công cụ coi là đầu/chân trang: {n_found}; trùng khung Page-header/Page-footer: {ok} "
          f"({round(100 * ok / max(1, n_found), 1)}%). Theo loại khung DocLayNet chứa chúng: {dict(found_cls)}.", "",
          f"Trang có khung đầu/chân trang: {pages_with_gt}; trang công cụ tìm thấy đầu/chân trang: {pages_with_found}.", ""]
    return summary, L


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True, help="Folder holding DocLayNet-{train,val,test}")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "luka_doclaynet_eval")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "work-dev" / "doclaynet_stats")
    args = ap.parse_args(argv)

    papers = {p.name: str(p) for d in PAPER_DIRS if d.is_dir() for p in d.glob("*.pdf")}
    index = ev.build_index(args.data, args.cache_dir)
    by_doc: dict[str, list[dict]] = collections.defaultdict(list)
    for e in index:
        if e["doc"] in papers and e["subset"] == "tune":
            by_doc[e["doc"]].append(e)
    skipped = sorted(d for d in papers if d not in by_doc)
    out_dir = args.cache_dir / "facts" / f"fulldoc-v{F.FACTS_VERSION}"
    out_dir.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(by_doc)} papers, {sum(len(v) for v in by_doc.values())} DocLayNet pages "
          f"({len(skipped)} papers not in tune: {skipped[:5]})")
    t0 = time.time()
    results = []
    with cf.ProcessPoolExecutor(max_workers=args.workers, initializer=F._worker_init) as pool:
        futs = [pool.submit(_paper_worker, papers[d], sorted(v, key=lambda e: e["page_no"]),
                            str(out_dir / (Path(d).stem + ".jsonl.gz"))) for d, v in by_doc.items()]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            results.append(fut.result())
            if i % 10 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)} papers ({time.time() - t0:.0f} s)", flush=True)
    summary, lines = head_report(results)
    (args.out / "fulldoc_heads.md").write_text("\n".join(lines), encoding="utf-8")
    (args.out / "fulldoc_heads.json").write_text(json.dumps({"summary": summary, "papers": results},
                                                            ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "fulldoc_docs.txt").write_text("\n".join(sorted(by_doc)) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
