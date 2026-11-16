#!/usr/bin/env python3
# ==============================================================================
# [BUILD SOURCE / REFERENCE ONLY — DO NOT EXECUTE WITH SYSTEM PYTHON]
#
# Mục đích tệp này: Đây CHỈ là mã nguồn Python gốc dùng khi cần chỉnh sửa logic
# và đóng gói (PyInstaller) ra tệp chạy độc lập `tools\extract_assets\extract_assets.exe`.
#
# LƯU Ý CHO AI AGENT:
#   - KHÔNG chạy tệp `.py` này bằng `python` / `python3` / `py` / `pip`.
#   - Máy người dùng chạy qua bộ công cụ portable không cần Python hệ thống.
#   - Khi tách ảnh PDF, hãy gọi `tools\extract_pdf_assets.ps1` (tự động gọi
#     `tools\extract_assets\extract_assets.exe`) theo hướng dẫn trong SKILL.md.
# ==============================================================================
"""
Layout-Aware PDF Image Extractor (PyMuPDF) — Build source for extract_assets.exe.
Extracts all figure images (both bitmap images and vector diagrams, merging
multi-panel figures while keeping separate table-row images distinct) using
PDFFigures-inspired caption, text-row, and separator-rule heuristics.

Build target:
  tools/extract_assets/extract_assets.exe (invoked via tools/extract_pdf_assets.ps1)
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
import pymupdf


_LEAD_TRIM_RE = re.compile(r"^[\s•·▪▫▶►▸●○■□.\-–—*:]+")
_FIG_CAPTION_RE = re.compile(
    r"^(figures?|figs?\.?|hình|sơđồ|biểudồ|scheme|chart|plate|diagram)\s*[\dIVX]+",
    re.IGNORECASE,
)
_TAB_CAPTION_RE = re.compile(
    r"^(tables?|tabs?\.?|bảng)\s*[\dIVX]+",
    re.IGNORECASE,
)


@dataclass
class TextBlock:
    rect: pymupdf.Rect
    text: str
    kind: str  # "fig_caption", "tab_caption", "text"


@dataclass
class CandidateBox:
    rect: pymupdf.Rect
    caption_idx: int | None = None


def _clean_text(text: str) -> str:
    """Collapse internal newlines/whitespace and normalize common PDF ligatures."""
    return " ".join(text.strip().split()).replace("ﬁ", "fi").replace("ﬂ", "fl")


def _classify_text_block(text: str) -> str:
    """Classify a text block as figure caption, table caption, or regular text."""
    collapsed = _clean_text(text)
    if not collapsed:
        return "text"
    cleaned = _LEAD_TRIM_RE.sub("", collapsed)
    compact = re.sub(r"\s+", "", cleaned[:36])
    if _FIG_CAPTION_RE.match(compact):
        return "fig_caption"
    if _TAB_CAPTION_RE.match(compact):
        return "tab_caption"
    return "text"


def _collect_text_blocks(page: pymupdf.Page) -> list[TextBlock]:
    """Extract non-empty text blocks classified by role."""
    blocks: list[TextBlock] = []
    for b in page.get_text("blocks"):
        if b[6] != 0:
            continue
        txt = b[4].strip()
        if not txt:
            continue
        blocks.append(TextBlock(pymupdf.Rect(b[:4]), txt, _classify_text_block(txt)))
    return blocks


def _is_page_background(r: pymupdf.Rect, pw: float, ph: float) -> bool:
    """Return True if rectangle covers almost the entire page/slide canvas."""
    area_ratio = (r.width * r.height) / max(1.0, pw * ph)
    return area_ratio >= 0.78 or (r.width >= 0.90 * pw and r.height >= 0.85 * ph)


def _horiz_overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))


def _vert_overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def _rect_gap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    """Euclidean gap between two rectangles (0 if overlapping)."""
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return (dx * dx + dy * dy) ** 0.5


def _is_edge_ornament(
    r: pymupdf.Rect, pw: float, ph: float, fig_captions: list[TextBlock]
) -> bool:
    """Filter out small running header/footer logos, page badges, and margin bars."""
    if r.height >= 62.0:
        return False
    in_margin = r.y1 < 54.0 or r.y0 > ph - 45.0 or (r.y0 < 42.0 and r.height < 50.0)
    if not in_margin:
        return False
    for cap in fig_captions:
        if _horiz_overlap(r, cap.rect) >= 20.0 and abs(cap.rect.y0 - r.y1) < 40.0:
            return False
    return True


def _merge_touching(rects: list[pymupdf.Rect], pad: float = 2.0) -> list[pymupdf.Rect]:
    """Merge overlapping or tightly touching rectangles within `pad` points."""
    merged: list[pymupdf.Rect] = []
    for r in sorted(rects, key=lambda x: (round(x.y0, 1), round(x.x0, 1))):
        cur = pymupdf.Rect(r)
        changed = True
        while changed:
            changed = False
            rest: list[pymupdf.Rect] = []
            for m in merged:
                expanded = pymupdf.Rect(m.x0 - pad, m.y0 - pad, m.x1 + pad, m.y1 + pad)
                if cur.intersects(expanded):
                    cur = cur | m
                    changed = True
                else:
                    rest.append(m)
            merged = rest
        merged.append(cur)
    return sorted(merged, key=lambda x: (round(x.y0, 1), round(x.x0, 1)))


def _collect_raster_boxes(
    page: pymupdf.Page, fig_captions: list[TextBlock]
) -> tuple[list[pymupdf.Rect], bool]:
    """Collect foreground raster regions and report whether a full-page image exists."""
    pw, ph = page.rect.width, page.rect.height
    raw_rects: list[pymupdf.Rect] = []
    has_full_page_img = False

    for info in page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.is_empty or r.width < 1.0 or r.height < 1.0:
            continue
        if _is_page_background(r, pw, ph):
            has_full_page_img = True
            continue
        raw_rects.append(r)

    merged = _merge_touching(raw_rects, pad=2.0)
    kept: list[pymupdf.Rect] = []
    for r in merged:
        if r.width < 36.0 or r.height < 36.0 or (r.width * r.height) < 1600.0:
            continue
        if _is_edge_ornament(r, pw, ph, fig_captions):
            continue
        kept.append(r)
    return kept, has_full_page_img


def _collect_separator_rules(
    drawings: list[dict], pw: float, ph: float
) -> list[pymupdf.Rect]:
    """Identify long thin horizontal/vertical rules used as table/section dividers."""
    rules: list[pymupdf.Rect] = []
    for dr in drawings:
        r = dr["rect"]
        if r.height <= 4.0 and r.width >= 0.25 * pw:
            rules.append(r)
        elif r.width <= 4.0 and r.height >= 0.30 * ph:
            rules.append(r)
    return rules


def _filter_drawings_for_clustering(
    drawings: list[dict], pw: float, ph: float, words: list[tuple]
) -> list[dict]:
    """Remove page frames, divider rules, text highlights, and shaded table row fills."""
    word_rects = [pymupdf.Rect(w[:4]) for w in words]
    filtered: list[dict] = []

    for dr in drawings:
        r = dr["rect"]
        if r.is_empty:
            continue
        if _is_page_background(r, pw, ph):
            continue
        if r.height <= 4.0 and r.width >= 0.30 * pw:
            continue
        if r.width <= 4.0 and r.height >= 0.30 * ph:
            continue
        if (r.y1 < 48.0 or r.y0 > ph - 40.0) and r.height < 28.0:
            continue

        if dr.get("color") is None and dr.get("fill") is not None:
            is_highlight = 4.0 <= r.height <= 24.0 and any(
                r.intersects(wr) and _vert_overlap(r, wr) >= 0.5 * min(r.height, wr.height)
                for wr in word_rects
            )
            if is_highlight or r.width >= 0.30 * pw:
                continue

        filtered.append(dr)

    return filtered


def _is_valid_vector_cluster(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    filtered_rects: list[pymupdf.Rect],
    raster_rects: list[pymupdf.Rect],
    text_blocks: list[TextBlock],
    fig_captions: list[TextBlock],
) -> bool:
    """Reject tiny artifacts, edge badges, prose blocks, data tables, and outlined text."""
    pw, ph = page.rect.width, page.rect.height
    if rect.width < 42.0 or rect.height < 42.0 or _is_page_background(rect, pw, ph):
        return False
    if _is_edge_ornament(rect, pw, ph, fig_captions):
        return False

    txt = page.get_text("text", clip=rect).strip()
    word_count = len(txt.split())
    if word_count > 80:
        return False

    if word_count >= 20:
        tabs = page.find_tables(clip=rect)
        if any(
            pymupdf.Rect(t.bbox).get_area() > 0.45 * rect.get_area()
            and t.row_count >= 2
            and t.col_count >= 2
            for t in tabs.tables
        ):
            return False
        prose_inside = [
            tb for tb in text_blocks
            if tb.kind == "text"
            and len(tb.text.split()) >= 12
            and (tb.rect & rect).get_area() > 0.5 * tb.rect.get_area()
        ]
        if len(prose_inside) >= 2:
            return False

    has_raster = any(rect.intersects(rr) for rr in raster_rects)
    if not has_raster:
        inside = [r for r in filtered_rects if rect.contains(r)]
        if len(inside) >= 200:
            tiny_glyphs = sum(
                1 for x in inside if 1.0 <= x.width <= 12.0 and 1.0 <= x.height <= 12.0
            )
            if (tiny_glyphs / len(inside)) >= 0.72:
                return False

    return True


def _match_caption(
    rect: pymupdf.Rect, fig_captions: list[TextBlock], text_blocks: list[TextBlock]
) -> int | None:
    """Find the most likely figure caption belonging to `rect`, if any."""
    best_idx: int | None = None
    best_dist = float("inf")

    for idx, cap in enumerate(fig_captions):
        cr = cap.rect
        h_ov = _horiz_overlap(rect, cr)
        min_ov = min(28.0, 0.30 * min(rect.width, cr.width))

        if h_ov >= min_ov:
            if -14.0 <= cr.y0 - rect.y1 <= 50.0:
                dist = abs(cr.y0 - rect.y1)
            elif -14.0 <= rect.y0 - cr.y1 <= 42.0:
                dist = abs(rect.y0 - cr.y1) + 5.0
            else:
                dist = float("inf")
        elif _vert_overlap(rect, cr) >= 10.0 and abs(cr.y0 - rect.y0) <= 35.0:
            gap_x = max(0.0, max(rect.x0, cr.x0) - min(rect.x1, cr.x1))
            dist = gap_x + 10.0 if gap_x <= 35.0 else float("inf")
        else:
            continue

        if dist < best_dist:
            span = rect | cr
            blocked = False
            for tb in text_blocks:
                if tb.rect == cr or tb.kind == "fig_caption":
                    continue
                if len(tb.text.split()) < 4:
                    continue
                if (
                    _horiz_overlap(tb.rect, span) >= 20.0
                    and ((rect.y1 <= tb.rect.y0 + 2 and tb.rect.y1 <= cr.y0 + 2)
                         or (cr.y1 <= tb.rect.y0 + 2 and tb.rect.y1 <= rect.y0 + 2))
                ):
                    blocked = True
                    break
            if not blocked:
                best_dist = dist
                best_idx = idx

    return best_idx


def _propagate_captions(
    candidates: list[CandidateBox],
    fig_captions: list[TextBlock],
    text_blocks: list[TextBlock],
    rules: list[pymupdf.Rect],
) -> None:
    """Propagate caption ownership to immediately stacked sibling panels."""
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(candidates):
            if a.caption_idx is not None:
                continue
            for j, b in enumerate(candidates):
                if i == j or b.caption_idx is None:
                    continue
                cap = fig_captions[b.caption_idx].rect
                if _horiz_overlap(a.rect, cap) < 0.45 * a.rect.width:
                    continue
                if _rect_gap(a.rect, b.rect) > 18.0:
                    continue
                if _has_obstacle_between(a.rect, b.rect, text_blocks, rules):
                    continue
                if _is_table_row_pair(a.rect, b.rect, text_blocks):
                    continue
                a.caption_idx = b.caption_idx
                changed = True
                break


def _has_obstacle_between(
    a: pymupdf.Rect,
    b: pymupdf.Rect,
    text_blocks: list[TextBlock],
    rules: list[pymupdf.Rect],
) -> bool:
    """Return True if a prose/caption block or divider rule lies strictly between `a` and `b`."""
    if a.y1 <= b.y0 or b.y1 <= a.y0:
        top, bot = (a, b) if a.y1 <= b.y0 else (b, a)
        x_lo, x_hi = min(a.x0, b.x0), max(a.x1, b.x1)
        for tb in text_blocks:
            tr = tb.rect
            if tr.y0 >= top.y1 - 4.0 and tr.y1 <= bot.y0 + 4.0:
                if max(0.0, min(x_hi, tr.x1) - max(x_lo, tr.x0)) >= 15.0:
                    return True
        for rr in rules:
            if top.y1 - 2.0 <= rr.y0 <= bot.y0 + 2.0 and rr.height <= 4.0:
                if max(0.0, min(x_hi, rr.x1) - max(x_lo, rr.x0)) >= 0.4 * (x_hi - x_lo):
                    return True

    if a.x1 <= b.x0 or b.x1 <= a.x0:
        left, right = (a, b) if a.x1 <= b.x0 else (b, a)
        y_lo, y_hi = min(a.y0, b.y0), max(a.y1, b.y1)
        for tb in text_blocks:
            tr = tb.rect
            if tr.x0 >= left.x1 - 4.0 and tr.x1 <= right.x0 + 4.0:
                if max(0.0, min(y_hi, tr.y1) - max(y_lo, tr.y0)) >= 12.0:
                    return True
        for rr in rules:
            if left.x1 - 2.0 <= rr.x0 <= right.x0 + 2.0 and rr.width <= 4.0:
                if max(0.0, min(y_hi, rr.y1) - max(y_lo, rr.y0)) >= 0.4 * (y_hi - y_lo):
                    return True

    return False


def _aligned_row_text_id(r: pymupdf.Rect, text_blocks: list[TextBlock]) -> int | None:
    """Return index of a distinct text block horizontally aligned beside `r` in the same row."""
    for idx, tb in enumerate(text_blocks):
        if tb.kind != "text":
            continue
        tr = tb.rect
        if _horiz_overlap(r, tr) > 5.0:
            continue
        gap_x = max(0.0, max(r.x0, tr.x0) - min(r.x1, tr.x1))
        if gap_x > 80.0:
            continue
        if abs(tr.y0 - r.y0) <= 10.0 and _vert_overlap(r, tr) >= 8.0 and tr.height <= r.height + 25.0:
            return idx
    return None


def _is_table_row_pair(
    a: pymupdf.Rect, b: pymupdf.Rect, text_blocks: list[TextBlock]
) -> bool:
    """Return True if vertically stacked `a` and `b` align with separate adjacent table-row texts."""
    if not (a.y1 <= b.y0 + 2.0 or b.y1 <= a.y0 + 2.0):
        return False
    if _horiz_overlap(a, b) < 0.5 * min(a.width, b.width):
        return False
    ta = _aligned_row_text_id(a, text_blocks)
    tb = _aligned_row_text_id(b, text_blocks)
    return ta is not None and tb is not None and ta != tb


def _should_merge_candidates(
    a: CandidateBox,
    b: CandidateBox,
    text_blocks: list[TextBlock],
    rules: list[pymupdf.Rect],
) -> bool:
    """Decide whether two figure candidates belong to the same logical figure."""
    if a.caption_idx is not None and b.caption_idx is not None and a.caption_idx != b.caption_idx:
        return False
    if _has_obstacle_between(a.rect, b.rect, text_blocks, rules):
        return False
    if _is_table_row_pair(a.rect, b.rect, text_blocks):
        return False

    gap = _rect_gap(a.rect, b.rect)
    if a.caption_idx is not None and a.caption_idx == b.caption_idx:
        return gap <= 48.0
    return gap <= 4.0


def _sort_reading_order(candidates: list[CandidateBox]) -> list[CandidateBox]:
    """Sort candidates top-to-bottom, ordering items within the same ~14pt band left-to-right."""
    ordered = sorted(candidates, key=lambda c: (c.rect.y0, c.rect.x0))
    rows: list[list[CandidateBox]] = []
    for c in ordered:
        if rows and abs(c.rect.y0 - rows[-1][0].rect.y0) <= 14.0:
            rows[-1].append(c)
        else:
            rows.append([c])
    result: list[CandidateBox] = []
    for row in rows:
        row.sort(key=lambda c: c.rect.x0)
        result.extend(row)
    return result


def _group_figures(
    raster_rects: list[pymupdf.Rect],
    vector_rects: list[pymupdf.Rect],
    text_blocks: list[TextBlock],
    rules: list[pymupdf.Rect],
) -> list[CandidateBox]:
    """Fuse overlapping raster/vector parts and merge multi-panel figures cleanly."""
    fig_captions = [tb for tb in text_blocks if tb.kind == "fig_caption"]

    base_rects = _merge_touching(raster_rects + vector_rects, pad=2.0)
    candidates = [
        CandidateBox(r, _match_caption(r, fig_captions, text_blocks)) for r in base_rects
    ]

    _propagate_captions(candidates, fig_captions, text_blocks, rules)

    changed = True
    while changed:
        changed = False
        merged: list[CandidateBox] = []
        for c in candidates:
            did_merge = False
            for m in merged:
                if _should_merge_candidates(m, c, text_blocks, rules):
                    m.rect = m.rect | c.rect
                    if m.caption_idx is None:
                        m.caption_idx = c.caption_idx
                    did_merge = True
                    changed = True
                    break
            if not did_merge:
                merged.append(c)
        candidates = merged

    return _sort_reading_order(candidates)


def _extract_context_snippet(
    rect: pymupdf.Rect, text_blocks: list[TextBlock]
) -> str | None:
    """Find concise nearby row or paragraph text when a figure has no explicit caption."""
    row_texts = [
        tb for tb in text_blocks
        if tb.kind == "text"
        and abs(tb.rect.y0 - rect.y0) <= 12.0
        and _vert_overlap(rect, tb.rect) >= 8.0
        and _horiz_overlap(rect, tb.rect) <= 5.0
    ]
    if row_texts:
        row_texts.sort(key=lambda tb: tb.rect.x0)
        joined = " | ".join(_clean_text(tb.text) for tb in row_texts)
        return joined[:220]

    best_tb: TextBlock | None = None
    best_gap = float("inf")
    for tb in text_blocks:
        gap = _rect_gap(rect, tb.rect)
        if gap < best_gap and gap <= 65.0 and len(tb.text.split()) >= 2:
            best_gap = gap
            best_tb = tb
    if best_tb is not None:
        return _clean_text(best_tb.text)[:220]
    return None


def _collect_page_candidates(
    page: pymupdf.Page,
) -> tuple[list[CandidateBox], list[TextBlock], list[TextBlock], bool]:
    """Collect figure candidates, text blocks, figure captions, and scan flag for `page`."""
    pw, ph = page.rect.width, page.rect.height
    text_blocks = _collect_text_blocks(page)
    fig_captions = [tb for tb in text_blocks if tb.kind == "fig_caption"]

    raster_rects, has_full_page_img = _collect_raster_boxes(page, fig_captions)

    drawings = page.get_drawings()
    vector_rects: list[pymupdf.Rect] = []
    rules: list[pymupdf.Rect] = []
    if drawings:
        rules = _collect_separator_rules(drawings, pw, ph)
        words = page.get_text("words")
        filtered = _filter_drawings_for_clustering(drawings, pw, ph, words)
        if filtered:
            filtered_rects = [dr["rect"] for dr in filtered]
            for c in page.cluster_drawings(drawings=filtered, x_tolerance=5, y_tolerance=5):
                if _is_valid_vector_cluster(
                    page, c, filtered_rects, raster_rects, text_blocks, fig_captions
                ):
                    vector_rects.append(c)

    candidates = _group_figures(raster_rects, vector_rects, text_blocks, rules)
    is_scanned = has_full_page_img and not candidates
    return candidates, text_blocks, fig_captions, is_scanned


def collect_page_figures(page: pymupdf.Page) -> tuple[list[pymupdf.Rect], bool]:
    """Collect logical figure bounding boxes on `page` and flag scanned pages."""
    candidates, _, _, is_scanned = _collect_page_candidates(page)
    return [c.rect for c in candidates], is_scanned


def extract_images(
    pdf_path: Path, out_dir: Path, dpi: int = 180, write_meta: bool = False
) -> list[Path]:
    """Render every detected bitmap or vector figure region in `pdf_path` to PNG."""
    doc = pymupdf.open(pdf_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    scanned_pages: list[int] = []
    manifest_items: list[dict] = []

    for pno, page in enumerate(doc, 1):
        ph, pw = page.rect.height, page.rect.width
        candidates, text_blocks, fig_captions, is_scanned = _collect_page_candidates(page)
        if is_scanned:
            scanned_pages.append(pno)
        for idx, cand in enumerate(candidates, 1):
            bb = cand.rect
            clip = pymupdf.Rect(
                max(0.0, bb.x0 - 4.0),
                max(0.0, bb.y0 - 4.0),
                min(pw, bb.x1 + 4.0),
                min(ph, bb.y1 + 4.0),
            )
            out_name = f"fig_p{pno}_{idx}.png"
            out_path = out_dir / out_name
            pix = page.get_pixmap(clip=clip, dpi=dpi)
            pix.save(out_path)
            saved.append(out_path)

            if write_meta:
                cap_text = (
                    _clean_text(fig_captions[cand.caption_idx].text)
                    if cand.caption_idx is not None
                    else None
                )
                ctx_text = (
                    None
                    if cap_text is not None
                    else _extract_context_snippet(bb, text_blocks)
                )
                manifest_items.append(
                    {
                        "file": out_name,
                        "page": pno,
                        "bbox": [
                            round(bb.x0, 1),
                            round(bb.y0, 1),
                            round(bb.x1, 1),
                            round(bb.y1, 1),
                        ],
                        "width_px": pix.width,
                        "height_px": pix.height,
                        "caption": cap_text,
                        "context": ctx_text,
                    }
                )

    print(f"Extracted {len(saved)} figures -> {out_dir}")
    if scanned_pages:
        print(
            f"[Note] Detected {len(scanned_pages)} scanned/full-page image page(s): {scanned_pages}"
        )
    if write_meta:
        meta_path = out_dir / "manifest.json"
        meta = {
            "pdf": pdf_path.name,
            "total_pages": len(doc),
            "scanned_pages": scanned_pages,
            "figures": manifest_items,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote manifest -> {meta_path}")
    return saved


def main() -> None:
    ap = argparse.ArgumentParser(description="Layout-aware figure image extractor from PDF")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=180)
    ap.add_argument(
        "--meta",
        action="store_true",
        help="Write manifest.json mapping extracted images to captions and context",
    )
    args = ap.parse_args()
    extract_images(args.pdf, args.out_dir, args.dpi, write_meta=args.meta)


if __name__ == "__main__":
    main()
