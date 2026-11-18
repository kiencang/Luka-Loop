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
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
import pymupdf


_LEAD_TRIM_RE = re.compile(r"^[\s•·▪▫▶►▸●○■□.\-–—*:]+")
_OPT_SUPP_PREFIX = r"(?:(?i:supplementary|extended\s+data|appendix)\s+)?"
_CAPTION_ID_BODY = (
    r"(?:(?:\s+|(?<=\.)\s*)(?:\d+(?:[.\-]\d+)*(?:[a-zA-Z])?|[IVXLCDM]+|[SA-Z]\.?\d+(?:[.\-]\d+)*(?:[a-zA-Z])?)"
    r"|\d+(?:[.\-]\d+)*(?:[a-zA-Z])?)"
)
_CAPTION_BOUNDARY = r"(?=$|[\s.:;\-–—|)\],])"
_FIG_CAPTION_RE = re.compile(
    rf"^{_OPT_SUPP_PREFIX}"
    r"(?i:figures?|figs?\.?|hình(?:\s+(?:ảnh|minh\s+họa))?|sơ\s*đồ|biểu\s*đồ|scheme|chart|plate|diagram)"
    rf"{_CAPTION_ID_BODY}{_CAPTION_BOUNDARY}"
)
_TAB_CAPTION_RE = re.compile(
    rf"^{_OPT_SUPP_PREFIX}"
    r"(?i:tables?|tabs?\.?|bảng)"
    rf"{_CAPTION_ID_BODY}{_CAPTION_BOUNDARY}"
)
_PROSE_AFTER_NUM_RE = re.compile(
    r"^\s+(?:shows?|illustrates?|presents?|depicts?|demonstrates?|summarizes?|compares?|displays?|indicates?|lists?|provides?|gives?|reports?|reveals?|confirms?|suggests?|highlights?|is|was|are|were|has|have|can|may|will|cho\s+thấy|minh\s+họa|mô\s+tả|trình\s+bày|tóm\s+tắt|so\s+sánh|chỉ\s+ra|thể\s+hiện)\b",
    re.IGNORECASE,
)
_SUBPANEL_LABEL_RE = re.compile(r"^(?:\([a-zA-Z0-9]{1,2}\)|[a-zA-Z]\)\s)")


@dataclass
class TextBlock:
    rect: pymupdf.Rect
    text: str
    kind: str  # "fig_caption", "tab_caption", "text"


@dataclass
class CandidateBox:
    rect: pymupdf.Rect
    caption_idx: int | None = None
    source: str = "vector"
    drawings: int = 0


def _clean_text(text: str) -> str:
    """Collapse internal newlines/whitespace and normalize common PDF ligatures."""
    return (
        " ".join(text.strip().split())
        .replace("ﬁ", "fi")
        .replace("ﬂ", "fl")
        .replace("ﬀ", "ff")
        .replace("ﬃ", "ffi")
        .replace("ﬄ", "ffl")
    )


def _classify_text_block(text: str) -> str:
    """Classify a text block as figure caption, table caption, or regular text."""
    collapsed = _clean_text(text)
    if not collapsed:
        return "text"
    cleaned = _LEAD_TRIM_RE.sub("", collapsed)
    fig_m = _FIG_CAPTION_RE.match(cleaned)
    if fig_m and not _PROSE_AFTER_NUM_RE.match(cleaned[fig_m.end():]):
        return "fig_caption"
    tab_m = _TAB_CAPTION_RE.match(cleaned)
    if tab_m and not _PROSE_AFTER_NUM_RE.match(cleaned[tab_m.end():]):
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
    r: pymupdf.Rect, page_rect: pymupdf.Rect, fig_captions: list[TextBlock]
) -> bool:
    """Filter out small running header/footer logos, page badges, and margin bars."""
    if r.height >= 62.0:
        return False
    top_y, bot_y = page_rect.y0, page_rect.y1
    in_margin = (
        r.y1 < (top_y + 54.0)
        or r.y0 > (bot_y - 45.0)
        or (r.y0 < (top_y + 42.0) and r.height < 50.0)
    )
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
        if _is_edge_ornament(r, page.rect, fig_captions):
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
    drawings: list[dict], page_rect: pymupdf.Rect, words: list[tuple]
) -> list[dict]:
    """Remove page frames, divider rules, text highlights, and shaded table row fills."""
    pw, ph = page_rect.width, page_rect.height
    top_y, bot_y = page_rect.y0, page_rect.y1
    word_rects = [pymupdf.Rect(w[:4]) for w in words]
    filtered: list[dict] = []

    for dr in drawings:
        r = dr["rect"]
        # PyMuPDF marks axis-aligned straight lines (width == 0 or height == 0) as is_empty;
        # keep them so flowchart connectors and plot axes survive clustering.
        if r.is_infinite or r.x1 < r.x0 or r.y1 < r.y0 or (r.width <= 0.0 and r.height <= 0.0):
            continue
        if _is_page_background(r, pw, ph):
            continue
        if r.height <= 4.0 and r.width >= 0.62 * pw:
            continue
        if r.width <= 4.0 and r.height >= 0.45 * ph:
            continue
        if (r.y1 < (top_y + 48.0) or r.y0 > (bot_y - 40.0)) and r.height < 28.0:
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
    if _is_edge_ornament(rect, page.rect, fig_captions):
        return False

    txt = page.get_text("text", clip=rect).strip()
    word_count = len(txt.split())
    if word_count > 200:
        return False

    has_fig_cap = _match_caption(rect, fig_captions, text_blocks) is not None
    if word_count > 80 and not has_fig_cap:
        return False

    if word_count >= 20:
        tab_captions = [tb for tb in text_blocks if tb.kind == "tab_caption"]
        has_tab_cap = _match_caption(rect, tab_captions, text_blocks) is not None
        if not (has_fig_cap and not has_tab_cap):
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
            and (tb.rect & rect).get_area() > 0.5 * tb.rect.get_area()
        ]
        long_blocks = [tb for tb in prose_inside if len(tb.text.split()) >= 12]
        if len(long_blocks) >= 2 or any(len(tb.text.split()) >= 40 for tb in long_blocks):
            return False

    has_raster = any(rect.intersects(rr) for rr in raster_rects)
    if not has_raster:
        inside = [r for r in filtered_rects if rect.contains(r)]
        if not has_fig_cap and word_count >= 5 and len(inside) <= 2:
            return False
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
            if -14.0 <= cr.y0 - rect.y1 <= 64.0:
                dist = abs(cr.y0 - rect.y1)
            elif -14.0 <= rect.y0 - cr.y1 <= 42.0:
                dist = abs(rect.y0 - cr.y1) + 18.0
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
                tb_words = tb.text.split()
                if len(tb_words) < 4:
                    continue
                if len(tb_words) <= 16 and _SUBPANEL_LABEL_RE.match(_clean_text(tb.text)):
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


def _row_aligned_text_indices(
    rect: pymupdf.Rect, text_blocks: list[TextBlock], max_gap_x: float = 80.0
) -> list[int]:
    """Return sorted indices of regular text blocks sharing the horizontal table row with `rect`."""
    indices: list[int] = []
    for idx, tb in enumerate(text_blocks):
        if tb.kind != "text":
            continue
        tr = tb.rect
        if _horiz_overlap(rect, tr) > 5.0:
            continue
        gap_x = max(0.0, max(rect.x0, tr.x0) - min(rect.x1, tr.x1))
        if gap_x > max_gap_x:
            continue
        vert_nested = (
            tr.y0 >= rect.y0 - 8.0
            and tr.y1 <= rect.y1 + 12.0
            and _vert_overlap(rect, tr) >= min(6.0, tr.height * 0.6)
        )
        top_aligned = (
            abs(tr.y0 - rect.y0) <= 12.0
            and _vert_overlap(rect, tr) >= 8.0
            and tr.height <= rect.height + 28.0
        )
        if vert_nested or top_aligned:
            indices.append(idx)
    indices.sort(key=lambda i: text_blocks[i].rect.x0)
    return indices


def _aligned_row_text_id(r: pymupdf.Rect, text_blocks: list[TextBlock]) -> int | None:
    """Return index of the first distinct text block horizontally aligned beside `r` in the same row."""
    matches = _row_aligned_text_indices(r, text_blocks, max_gap_x=80.0)
    return matches[0] if matches else None


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
    row_indices = _row_aligned_text_indices(rect, text_blocks, max_gap_x=120.0)
    if row_indices:
        joined = " | ".join(_clean_text(text_blocks[i].text) for i in row_indices)
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


def _is_frame_for(inner: pymupdf.Rect, outer: pymupdf.Rect) -> bool:
    """Return True if `inner` is just an enclosing border/cell box around `outer`."""
    outer_area = max(1.0, outer.get_area())
    return (
        (inner & outer).get_area() >= 0.85 * outer_area
        and inner.get_area() >= 0.85 * outer_area
    )


def _rect_center_inside(inner: pymupdf.Rect, outer: pymupdf.Rect) -> bool:
    """Return True if `inner`'s midpoint lies inside `outer` (or overlaps substantially)."""
    cx = 0.5 * (inner.x0 + inner.x1)
    cy = 0.5 * (inner.y0 + inner.y1)
    if outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1:
        return True
    return (inner & outer).get_area() >= 0.5 * max(1.0, inner.get_area())


def _annotate_candidate_origins(
    candidates: list[CandidateBox],
    raster_rects: list[pymupdf.Rect],
    vector_rects: list[pymupdf.Rect],
    filtered_rects: list[pymupdf.Rect],
) -> None:
    """Populate `source` ('raster'|'vector'|'hybrid') and `drawings` count on each candidate."""
    for cand in candidates:
        bb = cand.rect
        overlapping_rasters = [rr for rr in raster_rects if bb.intersects(rr)]
        intersecting_vecs = [
            r for r in filtered_rects if bb.intersects(r) and _rect_center_inside(r, bb)
        ]
        if not overlapping_rasters:
            cand.source = "vector"
            cand.drawings = len(intersecting_vecs)
            continue

        non_frame_vecs = [r for r in intersecting_vecs if not _is_frame_for(r, bb)]
        if len(non_frame_vecs) >= 2 or (len(overlapping_rasters) >= 2 and len(non_frame_vecs) >= 1):
            cand.source = "hybrid"
            cand.drawings = len(intersecting_vecs)
        else:
            cand.source = "raster"
            cand.drawings = 0


def _detect_table_placement(
    candidates: list[CandidateBox],
    idx: int,
    text_blocks: list[TextBlock],
    table_bboxes: list[pymupdf.Rect],
) -> str:
    """Classify uncaptioned candidate as 'table_cell' or standalone 'figure'."""
    cand = candidates[idx]
    if cand.caption_idx is not None:
        return "figure"

    bb = cand.rect
    bb_area = max(1.0, bb.get_area())
    if any((bb & tb_rect).get_area() >= 0.65 * bb_area for tb_rect in table_bboxes):
        return "table_cell"

    row_indices = _row_aligned_text_indices(bb, text_blocks, max_gap_x=120.0)
    if len(row_indices) >= 2:
        return "table_cell"
    if len(row_indices) == 1 and len(text_blocks[row_indices[0]].text.split()) <= 25:
        if any(i != idx and _is_table_row_pair(bb, other.rect, text_blocks) for i, other in enumerate(candidates)):
            return "table_cell"
        row_span = bb | text_blocks[row_indices[0]].rect
        for tb in text_blocks:
            if tb.kind == "tab_caption" and 0.0 <= bb.y0 - tb.rect.y1 <= 55.0 and _horiz_overlap(tb.rect, row_span) >= 40.0:
                return "table_cell"

    return "figure"


def _normalize_box(bb: pymupdf.Rect, page_rect: pymupdf.Rect) -> list[float]:
    """Normalize `bb` onto [0.0, 1.0] relative to `page_rect` (handles CropBox offsets)."""
    pw = max(1.0, float(page_rect.width))
    ph = max(1.0, float(page_rect.height))

    def _norm(val: float, origin: float, span: float) -> float:
        return round(max(0.0, min(1.0, (val - origin) / span)), 3)

    return [
        _norm(bb.x0, page_rect.x0, pw),
        _norm(bb.y0, page_rect.y0, ph),
        _norm(bb.x1, page_rect.x0, pw),
        _norm(bb.y1, page_rect.y0, ph),
    ]


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
    filtered_rects: list[pymupdf.Rect] = []
    rules: list[pymupdf.Rect] = []
    if drawings:
        rules = _collect_separator_rules(drawings, pw, ph)
        words = page.get_text("words")
        filtered = _filter_drawings_for_clustering(drawings, page.rect, words)
        if filtered:
            filtered_rects = [dr["rect"] for dr in filtered]
            for c in page.cluster_drawings(drawings=filtered, x_tolerance=5, y_tolerance=5):
                if _is_valid_vector_cluster(
                    page, c, filtered_rects, raster_rects, text_blocks, fig_captions
                ):
                    vector_rects.append(c)

    candidates = _group_figures(raster_rects, vector_rects, text_blocks, rules)
    _annotate_candidate_origins(candidates, raster_rects, vector_rects, filtered_rects)
    is_scanned = has_full_page_img and not candidates
    return candidates, text_blocks, fig_captions, is_scanned


def collect_page_figures(page: pymupdf.Page) -> tuple[list[pymupdf.Rect], bool]:
    """Collect logical figure bounding boxes on `page` and flag scanned pages."""
    candidates, _, _, is_scanned = _collect_page_candidates(page)
    return [c.rect for c in candidates], is_scanned


def _configure_utf8_stdio() -> None:
    """Ensure stdout/stderr emit UTF-8 on Windows even when piped under cp1252."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_PAGE_TOKEN_SPLIT_RE = re.compile(r"[,;\s]+")
_PAGE_RANGE_RE = re.compile(r"^(\d+)-(\d+)$")
_INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


def _validate_dpi(value: str) -> int:
    dpi = int(value)
    if dpi < 36 or dpi > 1200:
        raise argparse.ArgumentTypeError(f"--dpi must be between 36 and 1200 (got {dpi})")
    return dpi


def _validate_scale(value: str) -> float:
    scale = float(value)
    if not math.isfinite(scale) or scale < 0.5 or scale > 10.0:
        raise argparse.ArgumentTypeError(f"--scale must be between 0.5 and 10.0 (got {value})")
    return scale


def _validate_quality(value: str) -> int:
    quality = int(value)
    if quality < 1 or quality > 100:
        raise argparse.ArgumentTypeError(f"--quality must be between 1 and 100 (got {quality})")
    return quality


def _validate_max_width(value: str) -> int:
    max_width = int(value)
    if max_width < 0 or max_width > 10000:
        raise argparse.ArgumentTypeError(
            f"--max-width must be between 0 and 10000 (got {max_width})"
        )
    return max_width


def _read_json_utf8(path: Path) -> object:
    """Load a UTF-8 JSON file (accepting optional BOM)."""
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ensure_rgb_or_gray(pix: pymupdf.Pixmap) -> pymupdf.Pixmap:
    """Convert non-gray/non-RGB pixmaps (e.g., CMYK or None colorspace) into RGB."""
    if pix.colorspace is None or (pix.n - pix.alpha) not in (1, 3):
        return pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix


def _crop_pixmap(pix: pymupdf.Pixmap, x0: int, y0: int, x1: int, y1: int) -> pymupdf.Pixmap:
    """Copy rectangular region [x0, y0, x1, y1) from `pix` into a zero-origin Pixmap."""
    rect = pymupdf.IRect(x0, y0, x1, y1)
    out = pymupdf.Pixmap(pix.colorspace, rect, bool(pix.alpha))
    out.copy(pix, rect)
    out.set_origin(0, 0)
    return out


def _decode_pixel_rgb_alpha(
    mv: memoryview, idx: int, color_n: int, has_alpha_chan: bool
) -> tuple[int, int, int, int]:
    """Read pixel at byte offset `idx`, un-premultiplying alpha into straight (r, g, b, a)."""
    a = mv[idx + color_n] if has_alpha_chan else 255
    if color_n == 1:
        r = g = b = mv[idx]
    else:
        r, g, b = mv[idx], mv[idx + 1], mv[idx + 2]
    if has_alpha_chan and 0 < a < 255:
        half = a >> 1
        r = min(255, (r * 255 + half) // a)
        g = min(255, (g * 255 + half) // a)
        b = min(255, (b * 255 + half) // a)
    return r, g, b, a


def _parse_page_list(raw_pages: str, total_pages: int) -> list[int]:
    """Parse optional page filter (e.g. '2', '2,5', '[1, 3]', '2-4') into sorted 1-based pages."""
    if total_pages < 1:
        return []
    cleaned = (raw_pages or "").strip().strip("[]").strip()
    if not cleaned:
        return list(range(1, total_pages + 1))

    tokens = [tok for tok in _PAGE_TOKEN_SPLIT_RE.split(cleaned) if tok]
    if not tokens:
        return list(range(1, total_pages + 1))

    seen: set[int] = set()
    for tok in tokens:
        m = _PAGE_RANGE_RE.match(tok)
        if m:
            start_p = int(m.group(1))
            end_p = int(m.group(2))
            if start_p < 1 or end_p < start_p or end_p > total_pages:
                raise ValueError(f"Page range '{tok}' out of valid range (1..{total_pages}).")
            seen.update(range(start_p, end_p + 1))
        elif tok.isdigit():
            p = int(tok)
            if p < 1 or p > total_pages:
                raise ValueError(f"Page number {p} out of valid range (1..{total_pages}).")
            seen.add(p)
        else:
            raise ValueError(
                f"Invalid -Pages token '{tok}'. Expected positive integers or ranges like '2,5' or '2-4'."
            )
    return sorted(seen)


def render_pages(
    pdf_path: Path, out_dir: Path, scale: float = 2.5, pages: str = ""
) -> list[Path]:
    """Render selected PDF pages to opaque white-background PNGs (`page_1.png`, ...)."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not math.isfinite(scale) or scale < 0.5 or scale > 10.0:
        raise ValueError(f"RenderScale out of safe range (0.5..10.0): {scale}")

    saved: list[Path] = []
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise RuntimeError(f"PDF is password-protected/encrypted and cannot be rendered: {pdf_path}")
        total_pages = len(doc)
        target_pages = _parse_page_list(pages, total_pages)
        out_dir.mkdir(parents=True, exist_ok=True)

        for pno in target_pages:
            page = doc[pno - 1]
            target_w = max(800, int(round(page.rect.width * scale)))
            zoom = target_w / max(1e-6, page.rect.width)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            out_png = out_dir / f"page_{pno}.png"
            out_png.write_bytes(pix.tobytes("png"))
            saved.append(out_png)
            print(f"Rendered page {pno}/{total_pages} -> {out_png} ({pix.width}px wide)")
    return saved


def _scan_ink_range(
    mv: memoryview,
    start_idx: int,
    stop_idx: int,
    idx_step: int,
    color_n: int,
    has_alpha: bool,
    threshold: int,
) -> bool:
    """Return True if any sampled pixel offset in range has visible non-white ink."""
    for idx in range(start_idx, stop_idx, idx_step):
        if has_alpha:
            a = mv[idx + color_n]
            if a <= 10:
                continue
            if a < 255:
                half = a >> 1
                if color_n == 1:
                    if min(255, (mv[idx] * 255 + half) // a) < threshold:
                        return True
                elif (
                    min(255, (mv[idx] * 255 + half) // a) < threshold
                    or min(255, (mv[idx + 1] * 255 + half) // a) < threshold
                    or min(255, (mv[idx + 2] * 255 + half) // a) < threshold
                ):
                    return True
                continue
        if color_n == 1:
            if mv[idx] < threshold:
                return True
        elif mv[idx] < threshold or mv[idx + 1] < threshold or mv[idx + 2] < threshold:
            return True
    return False


def _find_ink_bounds(
    pix: pymupdf.Pixmap, threshold: int = 247, step: int = 2
) -> tuple[int, int, int, int] | None:
    """Return inclusive grid bounds (min_x, min_y, max_x, max_y) of non-white visible ink."""
    w, h = pix.width, pix.height
    if w <= 0 or h <= 0:
        return None
    inc = max(1, step)
    color_n = pix.n - pix.alpha
    has_alpha = bool(pix.alpha)
    n = pix.n
    stride = w * n
    mv = pix.samples_mv

    ys = list(range(0, h, inc))
    xs = list(range(0, w, inc))

    min_y: int | None = None
    for y in ys:
        row_off = y * stride
        if _scan_ink_range(mv, row_off, row_off + stride, inc * n, color_n, has_alpha, threshold):
            min_y = y
            break
    if min_y is None:
        return None

    max_y = min_y
    for y in reversed(ys):
        if y <= min_y:
            break
        row_off = y * stride
        if _scan_ink_range(mv, row_off, row_off + stride, inc * n, color_n, has_alpha, threshold):
            max_y = y
            break

    col_step = inc * stride
    min_x = xs[0]
    for x in xs:
        col_off = x * n
        if _scan_ink_range(
            mv, min_y * stride + col_off, max_y * stride + col_off + 1, col_step, color_n, has_alpha, threshold
        ):
            min_x = x
            break

    max_x = min_x
    for x in reversed(xs):
        if x <= min_x:
            break
        col_off = x * n
        if _scan_ink_range(
            mv, min_y * stride + col_off, max_y * stride + col_off + 1, col_step, color_n, has_alpha, threshold
        ):
            max_x = x
            break

    return min_x, min_y, max_x, max_y


def _trim_white_margins(
    pix: pymupdf.Pixmap, threshold: int = 247, pad: int = 6
) -> pymupdf.Pixmap:
    """Crop excess white/transparent borders around visible ink with padding."""
    bounds = _find_ink_bounds(pix, threshold=threshold, step=2)
    if bounds is None:
        return pix
    min_x, min_y, max_x, max_y = bounds
    x0 = max(0, min_x - pad)
    y0 = max(0, min_y - pad)
    x1 = min(pix.width - 1, max_x + pad)
    y1 = min(pix.height - 1, max_y + pad)
    if x0 == 0 and y0 == 0 and x1 == pix.width - 1 and y1 == pix.height - 1:
        return pix
    return _crop_pixmap(pix, x0, y0, x1 + 1, y1 + 1)


def _validate_bare_filename(name: str, label: str = "out_name") -> str:
    """Ensure `name` is a single safe filename with no directory separators or traversal."""
    trimmed = (name or "").strip()
    if (
        not trimmed
        or trimmed in (".", "..")
        or Path(trimmed).name != trimmed
        or any(ord(ch) < 32 or ch in _INVALID_FILENAME_CHARS for ch in trimmed)
    ):
        raise ValueError(
            f"Path traversal blocked: invalid {label} '{name}' (must be a plain filename inside OutDir)"
        )
    return trimmed


def _validate_crop_box(box: object, out_name: str) -> tuple[float, float, float, float]:
    """Validate normalized [x0, y0, x1, y1] box coordinates in [0.0, 1.0] with x1 > x0, y1 > y0."""
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError(f"Invalid crop box for '{out_name}': expected 4 numeric elements [x0, y0, x1, y1].")
    vals: list[float] = []
    for idx, raw in enumerate(box):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"Invalid crop box coordinate at index {idx} for '{out_name}'.")
        val = float(raw)
        if not math.isfinite(val) or val < 0.0 or val > 1.0:
            raise ValueError(
                f"Crop box coordinate {raw} at index {idx} out of normalized range [0.0, 1.0] for '{out_name}'."
            )
        vals.append(val)
    if vals[2] <= vals[0] or vals[3] <= vals[1]:
        raise ValueError(f"Invalid crop box {vals} for '{out_name}': require x1 > x0 and y1 > y0.")
    return vals[0], vals[1], vals[2], vals[3]


def crop_from_json(spec_path: Path, out_dir: Path) -> list[Path]:
    """Crop normalized [x0, y0, x1, y1] regions defined in JSON spec with optional white-border auto-trim."""
    raw = _read_json_utf8(spec_path)
    if isinstance(raw, dict) and "items" in raw:
        items = raw["items"]
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = [raw]
    else:
        raise ValueError(f"Crop spec JSON must be an array or object with 'items': {spec_path}")
    if not isinstance(items, list):
        raise ValueError(f"Invalid crop spec items list in {spec_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each crop spec item must be a JSON object.")
        out_name = _validate_bare_filename(str(item.get("out_name", "")))
        src_raw = str(item.get("src_path") or item.get("page_png") or "").strip()
        if not src_raw:
            raise ValueError(f"Missing page_png/src_path in crop spec for '{out_name}'.")
        src_path = Path(src_raw)
        if not src_path.is_file():
            raise FileNotFoundError(f"Source crop image not found: {src_path}")

        bx0, by0, bx1, by1 = _validate_crop_box(item.get("box"), out_name)
        pix = _ensure_rgb_or_gray(pymupdf.Pixmap(str(src_path)))
        bw, bh = pix.width, pix.height
        x0 = max(0, int(round(bx0 * bw)))
        y0 = max(0, int(round(by0 * bh)))
        x1 = min(bw, int(round(bx1 * bw)))
        y1 = min(bh, int(round(by1 * bh)))
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"Invalid crop box [{bx0},{by0},{bx1},{by1}] for {out_name}")

        cropped = _crop_pixmap(pix, x0, y0, x1, y1)
        if item.get("auto_trim", True) is not False:
            cropped = _trim_white_margins(cropped)

        out_file = out_dir / out_name
        out_file.write_bytes(cropped.tobytes("png"))
        saved.append(out_file)
        print(f"Cropped {out_name} -> {out_file} ({cropped.width}x{cropped.height})")
    return saved


def _analyze_sample_grid(pix: pymupdf.Pixmap) -> tuple[int, bool]:
    """Sample a ~60x60 pixel grid to count distinct 15-bit quantized colors and alpha presence."""
    w, h = pix.width, pix.height
    if w <= 0 or h <= 0:
        return 0, False
    step_x = max(1, int(round(w / 60.0)))
    step_y = max(1, int(round(h / 60.0)))
    color_n = pix.n - pix.alpha
    has_alpha_chan = bool(pix.alpha)
    n = pix.n
    mv = pix.samples_mv

    colors: set[int] = set()
    has_alpha = False
    for y in range(0, h, step_y):
        row_off = y * w
        for x in range(0, w, step_x):
            idx = (row_off + x) * n
            r, g, b, a = _decode_pixel_rgb_alpha(mv, idx, color_n, has_alpha_chan)
            if a < 250:
                has_alpha = True
            q = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)
            colors.add(q)
    return len(colors), has_alpha


def _optimize_single_image(
    img_path: Path, out_dir: Path, index: int, quality: int, max_width: int
) -> dict:
    """Analyze, resize if wider than `max_width`, and selectively JPEG/PNG compress one image."""
    if not img_path.is_file():
        raise FileNotFoundError(f"Image file not found: {img_path}")

    orig_bytes = img_path.read_bytes()
    orig_len = len(orig_bytes)
    orig_mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

    pix = _ensure_rgb_or_gray(pymupdf.Pixmap(str(img_path)))
    distinct_colors, has_alpha = _analyze_sample_grid(pix)
    is_rich_photo = distinct_colors >= 200

    work_pix = pix
    was_resized = False
    if max_width > 0 and pix.width > max_width:
        new_w = max_width
        new_h = max(1, int(round(pix.height * (max_width / float(pix.width)))))
        work_pix = pymupdf.Pixmap(pix, new_w, new_h, None)
        was_resized = True

    if is_rich_photo and not has_alpha:
        jpg_pix = pymupdf.Pixmap(work_pix, 0) if work_pix.alpha else work_pix
        jpg_bytes = jpg_pix.tobytes("jpeg", jpg_quality=quality)
        if len(jpg_bytes) < orig_len and (was_resized or len(jpg_bytes) <= int(orig_len * 0.85)):
            out_file = out_dir / f"opt_{index}.jpg"
            out_file.write_bytes(jpg_bytes)
            return {
                "path": str(img_path),
                "out_file": str(out_file),
                "mime": "image/jpeg",
                "orig_len": orig_len,
                "final_len": len(jpg_bytes),
            }

    if was_resized and orig_mime == "image/png":
        png_bytes = work_pix.tobytes("png")
        if len(png_bytes) < orig_len:
            out_file = out_dir / f"opt_{index}.png"
            out_file.write_bytes(png_bytes)
            return {
                "path": str(img_path),
                "out_file": str(out_file),
                "mime": "image/png",
                "orig_len": orig_len,
                "final_len": len(png_bytes),
            }

    return {
        "path": str(img_path),
        "out_file": None,
        "mime": orig_mime,
        "orig_len": orig_len,
        "final_len": orig_len,
    }


def optimize_images_batch(
    spec_path: Path,
    out_dir: Path,
    out_json_path: Path,
    quality: int = 90,
    max_width: int = 1400,
) -> dict:
    """Optimize a batch of local PNG/JPEG files referenced by `spec_path` and write metadata to `out_json_path`."""
    if quality < 1 or quality > 100:
        raise ValueError(f"JpegQuality out of valid range (1..100): {quality}")
    if max_width < 0 or max_width > 10000:
        raise ValueError(f"MaxImageWidth out of valid range (0..10000): {max_width}")

    raw = _read_json_utf8(spec_path)
    items = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
    if not isinstance(items, list):
        raise ValueError(f"Optimize spec JSON must be an array or object with 'items': {spec_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for idx, entry in enumerate(items):
        raw_path = entry["path"] if isinstance(entry, dict) else entry
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"Missing image path at spec index {idx}")
        results.append(
            _optimize_single_image(Path(raw_path), out_dir, idx, quality, max_width)
        )

    payload = {"results": results}
    out_json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def extract_images(
    pdf_path: Path, out_dir: Path, dpi: int = 180, write_meta: bool = False
) -> list[Path]:
    """Render every detected bitmap or vector figure region in `pdf_path` to PNG."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if dpi < 36 or dpi > 1200:
        raise ValueError(f"dpi must be between 36 and 1200 (got {dpi})")

    saved: list[Path] = []
    scanned_pages: list[int] = []
    manifest_items: list[dict] = []

    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise RuntimeError(f"PDF is password-protected/encrypted and cannot be extracted: {pdf_path}")

        out_dir.mkdir(parents=True, exist_ok=True)
        total_pages = len(doc)

        for pno, page in enumerate(doc, 1):
            candidates, text_blocks, fig_captions, is_scanned = _collect_page_candidates(page)
            if is_scanned:
                scanned_pages.append(pno)
            table_bboxes: list[pymupdf.Rect] = []
            if write_meta and any(c.caption_idx is None for c in candidates):
                table_bboxes = [pymupdf.Rect(t.bbox) for t in page.find_tables().tables]

            for idx0, cand in enumerate(candidates):
                idx = idx0 + 1
                bb = cand.rect
                clip = pymupdf.Rect(bb.x0 - 4.0, bb.y0 - 4.0, bb.x1 + 4.0, bb.y1 + 4.0) & page.rect
                if clip.is_empty:
                    continue
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
                    placement = _detect_table_placement(candidates, idx0, text_blocks, table_bboxes)
                    manifest_items.append(
                        {
                            "file": out_name,
                            "page": pno,
                            "source": cand.source,
                            "drawings": cand.drawings,
                            "placement": placement,
                            "box": _normalize_box(bb, page.rect),
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
            "dpi": dpi,
            "total_pages": total_pages,
            "scanned_pages": scanned_pages,
            "figures": manifest_items,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote manifest -> {meta_path}")
    return saved


def main(argv: list[str] | None = None) -> None:
    _configure_utf8_stdio()
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument(
        "--mode",
        choices=("extract", "render-pages", "crop-json", "optimize-images"),
        default=None,
    )
    known, rest = pre.parse_known_args(raw_argv)
    mode = known.mode or "extract"

    if mode == "extract":
        ap = argparse.ArgumentParser(
            description="Layout-aware figure image extractor & PDF/image utility (PyMuPDF)"
        )
        ap.add_argument(
            "--mode",
            choices=("extract", "render-pages", "crop-json", "optimize-images"),
            default="extract",
            help="Operation mode (default: extract)",
        )
        ap.add_argument("pdf", type=Path)
        ap.add_argument("--out-dir", type=Path, required=True)
        ap.add_argument("--dpi", type=_validate_dpi, default=180)
        ap.add_argument(
            "--meta",
            action="store_true",
            help="Write manifest.json mapping extracted images to captions and context",
        )
        args = ap.parse_args(rest)
        extract_images(args.pdf, args.out_dir, args.dpi, write_meta=args.meta)
    elif mode == "render-pages":
        ap = argparse.ArgumentParser(description="Render PDF pages to PNG images")
        ap.add_argument("pdf", type=Path)
        ap.add_argument("--out-dir", type=Path, required=True)
        ap.add_argument("--scale", type=_validate_scale, default=2.5)
        ap.add_argument("--pages", type=str, default="")
        args = ap.parse_args(rest)
        render_pages(args.pdf, args.out_dir, scale=args.scale, pages=args.pages)
    elif mode == "crop-json":
        ap = argparse.ArgumentParser(description="Crop PNG regions from JSON spec with optional auto-trim")
        ap.add_argument("--spec", type=Path, required=True)
        ap.add_argument("--out-dir", type=Path, required=True)
        args = ap.parse_args(rest)
        crop_from_json(args.spec, args.out_dir)
    else:
        ap = argparse.ArgumentParser(description="Batch-analyze, resize, and optimize PNG/JPEG images")
        ap.add_argument("--spec", type=Path, required=True)
        ap.add_argument("--out-dir", type=Path, required=True)
        ap.add_argument("--out-json", type=Path, required=True)
        ap.add_argument("--quality", type=_validate_quality, default=90)
        ap.add_argument("--max-width", type=_validate_max_width, default=1400)
        args = ap.parse_args(rest)
        optimize_images_batch(
            args.spec,
            args.out_dir,
            args.out_json,
            quality=args.quality,
            max_width=args.max_width,
        )


if __name__ == "__main__":
    main()
