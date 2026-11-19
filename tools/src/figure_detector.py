"""Layout-aware PDF figure, caption, and table-cell detection & extraction (PyMuPDF)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from html_packager_core import emit_compacted_manifest_stdout
from image_ops import ensure_pymupdf
from path_guards import assert_local_no_unc_path, resolve_safe_out_directory

if TYPE_CHECKING:
    import pymupdf as _pymupdf_type  # noqa: F401

pymupdf = None


def _ensure_pymupdf():
    """Populate module-level `pymupdf` lazily via shared loader in `image_ops`."""
    global pymupdf
    if pymupdf is None:
        pymupdf = ensure_pymupdf()
    return pymupdf


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
    r"^\s+(?:shows|illustrates|presents|depicts|demonstrates|summarizes|compares|displays|indicates|lists|provides|gives|reports|reveals|confirms|suggests|highlights|is|was|are|were|has|have|can|may|will|cho\s+thấy|minh\s+họa|mô\s+tả|trình\s+bày|tóm\s+tắt|so\s+sánh|chỉ\s+ra|thể\s+hiện)\b",
)
_PLURAL_CAPTION_NOUN_RE = re.compile(
    rf"^{_OPT_SUPP_PREFIX}(?i:figures|figs\.?|tables|tabs\.?)\b"
)
_PLURAL_PROSE_AFTER_NUM_RE = re.compile(
    r"^\s+(?:show|illustrate|present|depict|demonstrate|summarize|compare|display|indicate|list|provide|give|report|reveal|confirm|suggest|highlight)\b",
)
_COMMA_PROSE_AFTER_NUM_RE = re.compile(r"^\s*,\s+[a-z]")
_INLINE_REF_AFTER_NUM_RE = re.compile(
    r"^(?:\s*[\)\]]|\s+(?:and|or)\s+(?i:fig(?:ure)?s?|tables?|tabs?)\b|\s+(?:for|as|to|in|on|at|with|by|from)\s+(?:a|an|the|this|more|further|details?|comparison|illustration|explanation)\b)"
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


def _is_prose_after_label(cleaned: str, label_end: int) -> bool:
    """Return True when lowercase running prose (never capitalized caption titles) follows a label."""
    tail = cleaned[label_end:]
    if tail == "." or _INLINE_REF_AFTER_NUM_RE.match(tail):
        return True
    if _PROSE_AFTER_NUM_RE.match(tail) or _COMMA_PROSE_AFTER_NUM_RE.match(tail):
        return True
    return bool(
        _PLURAL_CAPTION_NOUN_RE.match(cleaned) and _PLURAL_PROSE_AFTER_NUM_RE.match(tail)
    )


def _classify_text_block(text: str) -> str:
    """Classify a text block as figure caption, table caption, or regular text."""
    collapsed = _clean_text(text)
    if not collapsed:
        return "text"
    cleaned = _LEAD_TRIM_RE.sub("", collapsed)
    fig_m = _FIG_CAPTION_RE.match(cleaned)
    if fig_m and not _is_prose_after_label(cleaned, fig_m.end()):
        return "fig_caption"
    tab_m = _TAB_CAPTION_RE.match(cleaned)
    if tab_m and not _is_prose_after_label(cleaned, tab_m.end()):
        return "tab_caption"
    return "text"


def _split_dict_block(blk: dict) -> list[TextBlock]:
    """Split a PyMuPDF dict block across horizontal column jumps or mid-block captions."""
    _ensure_pymupdf()
    raw_lines: list[tuple[pymupdf.Rect, str]] = []
    for ln in blk.get("lines", ()):
        txt = "".join(s.get("text", "") for s in ln.get("spans", ())).strip()
        if not txt:
            continue
        r = pymupdf.Rect(ln["bbox"])
        if not r.is_empty:
            raw_lines.append((r, txt))

    if not raw_lines:
        return []

    groups: list[list[tuple[pymupdf.Rect, str]]] = []
    cur: list[tuple[pymupdf.Rect, str]] = []
    cur_rect: pymupdf.Rect | None = None

    for lr, ltxt in raw_lines:
        if not cur or cur_rect is None:
            cur = [(lr, ltxt)]
            cur_rect = pymupdf.Rect(lr)
            continue

        gap_x = max(cur_rect.x0, lr.x0) - min(cur_rect.x1, lr.x1)
        prev_r, prev_txt = cur[-1]
        cur_kind = _classify_text_block("\n".join(t for _, t in cur))
        line_kind = _classify_text_block(ltxt)
        caption_split = line_kind in ("fig_caption", "tab_caption") and (
            cur_kind == "text"
            or prev_txt.rstrip().endswith((".", "!", "?"))
            or (lr.y0 - prev_r.y1) >= 4.0
        )
        if gap_x >= 12.0 or caption_split:
            groups.append(cur)
            cur = [(lr, ltxt)]
            cur_rect = pymupdf.Rect(lr)
        else:
            cur.append((lr, ltxt))
            cur_rect = cur_rect | lr

    if cur:
        groups.append(cur)

    result: list[TextBlock] = []
    for grp in groups:
        grp_rect = pymupdf.Rect(grp[0][0])
        for r, _ in grp[1:]:
            grp_rect = grp_rect | r
        joined = "\n".join(t for _, t in grp)
        result.append(TextBlock(grp_rect, joined, _classify_text_block(joined)))
    return result


def _collect_text_blocks(page: pymupdf.Page) -> list[TextBlock]:
    """Extract non-empty text blocks classified by role."""
    blocks: list[TextBlock] = []
    for b in page.get_text("dict").get("blocks", ()):
        if b.get("type") != 0:
            continue
        blocks.extend(_split_dict_block(b))
    return blocks


def _is_page_background(r: pymupdf.Rect, pw: float, ph: float) -> bool:
    """Return True if rectangle covers almost the entire page/slide canvas."""
    area_ratio = (r.width * r.height) / max(1.0, pw * ph)
    return area_ratio >= 0.78 or (r.width >= 0.90 * pw and r.height >= 0.85 * ph)


def _is_vertical_bleed_strip(r: pymupdf.Rect, page_rect: pymupdf.Rect) -> bool:
    """Return True for narrow full-page-height decorative bleed strips along left/right edges."""
    pw, ph = page_rect.width, page_rect.height
    return (
        r.height >= 0.92 * ph
        and r.width <= 0.18 * pw
        and (r.x0 <= page_rect.x0 + 12.0 or r.x1 >= page_rect.x1 - 12.0)
    )


def _is_horizontal_bleed_strip(r: pymupdf.Rect, page_rect: pymupdf.Rect) -> bool:
    """Return True for full-page-width decorative bleed bands along top/bottom edges."""
    pw, ph = page_rect.width, page_rect.height
    return (
        r.width >= 0.92 * pw
        and r.height <= 0.16 * ph
        and (r.y0 <= page_rect.y0 + 12.0 or r.y1 >= page_rect.y1 - 12.0)
    )


def _is_full_bleed_edge_strip(r: pymupdf.Rect, page_rect: pymupdf.Rect) -> bool:
    """Return True for page-edge full-bleed decorative strips (horizontal or vertical)."""
    return _is_vertical_bleed_strip(r, page_rect) or _is_horizontal_bleed_strip(r, page_rect)


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
        or (
            r.width >= 0.60 * page_rect.width
            and (r.y0 < (top_y + 36.0) or r.y1 > (bot_y - 36.0))
        )
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
    page: pymupdf.Page,
    fig_captions: list[TextBlock],
    words: list[tuple] | None = None,
    text_blocks: list[TextBlock] | None = None,
) -> tuple[list[pymupdf.Rect], bool]:
    """Collect foreground raster regions and report whether a full-page image exists."""
    pw, ph = page.rect.width, page.rect.height
    raw_rects: list[pymupdf.Rect] = []
    has_full_page_img = False

    cap_blocks = fig_captions if text_blocks is None else text_blocks
    for info in page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.is_empty or r.width < 1.0 or r.height < 1.0:
            continue
        if _is_page_background(r, pw, ph):
            has_full_page_img = True
            continue
        # Drop narrow full-height bleed sidebars before merging so they cannot swallow corner logos.
        if _is_vertical_bleed_strip(r, page.rect) and _match_caption(r, fig_captions, cap_blocks) is None:
            continue
        raw_rects.append(r)

    merged = _merge_touching(raw_rects, pad=2.0)
    word_rects: list[pymupdf.Rect] | None = (
        [pymupdf.Rect(w[:4]) for w in words] if words is not None else None
    )
    kept: list[pymupdf.Rect] = []
    for r in merged:
        if _is_page_background(r, pw, ph):
            has_full_page_img = True
            continue
        is_normal_box = r.width >= 36.0 and r.height >= 36.0 and (r.width * r.height) >= 1600.0
        is_banner_strip = (
            min(r.width, r.height) >= 16.0
            and max(r.width, r.height) >= 100.0
            and (r.width * r.height) >= 1800.0
        )
        if not (is_normal_box or is_banner_strip):
            continue
        has_cap = _match_caption(r, fig_captions, cap_blocks) is not None
        if not has_cap and _is_full_bleed_edge_strip(r, page.rect):
            continue
        if _is_edge_ornament(r, page.rect, fig_captions):
            continue
        if not has_cap:
            if not is_normal_box:
                if r.width < 36.0 and r.height >= 0.45 * ph:
                    continue
                if word_rects is None:
                    word_rects = [pymupdf.Rect(w[:4]) for w in page.get_text("words")]
                if any(
                    r.intersects(wr) and _vert_overlap(r, wr) >= 0.45 * min(r.height, wr.height)
                    for wr in word_rects
                ):
                    continue
            elif text_blocks is not None:
                prose_blocks = [
                    tb for tb in cap_blocks
                    if tb.kind == "text"
                    and len(tb.text.split()) >= 10
                    and (tb.rect & r).get_area() > 0.5 * tb.rect.get_area()
                ]
                if len(prose_blocks) >= 3 and sum(len(tb.text.split()) for tb in prose_blocks) >= 85:
                    continue
        kept.append(r)
    return kept, has_full_page_img


def _is_light_gray_watermark_glyph(dr: dict) -> bool:
    """Return True if `dr` looks like an outlined light-gray diagonal watermark glyph."""
    if dr.get("color") is not None:
        return False
    fill = dr.get("fill")
    if fill is None or len(dr.get("items") or ()) < 10:
        return False
    r = dr["rect"]
    if max(r.width, r.height) > 95.0:
        return False
    if isinstance(fill, (int, float)):
        return float(fill) >= 0.68
    if isinstance(fill, (tuple, list)):
        if len(fill) == 1:
            return float(fill[0]) >= 0.68
        if len(fill) >= 3:
            rgb = [float(v) for v in fill[:3]]
            return min(rgb) >= 0.68 and (max(rgb) - min(rgb)) <= 0.06
    return False


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
    drawings: list[dict],
    page_rect: pymupdf.Rect,
    words: list[tuple],
    raster_rects: list[pymupdf.Rect] | None = None,
) -> list[dict]:
    """Remove page frames, divider rules, text highlights, and multi-figure sidebar backdrops."""
    pw, ph = page_rect.width, page_rect.height
    top_y, bot_y = page_rect.y0, page_rect.y1
    word_rects = [pymupdf.Rect(w[:4]) for w in words]
    rasters = raster_rects or []
    wm_indices = {i for i, dr in enumerate(drawings) if _is_light_gray_watermark_glyph(dr)}
    drop_wm = len(wm_indices) >= 4 and any(
        drawings[i]["rect"].intersects(wr) for i in wm_indices for wr in word_rects
    )
    filtered: list[dict] = []

    def _words_inside_count(box: pymupdf.Rect) -> int:
        return sum(
            1
            for wr in word_rects
            if box.contains(wr) or (box & wr).get_area() >= 0.5 * max(1e-6, wr.get_area())
        )

    for idx, dr in enumerate(drawings):
        if drop_wm and idx in wm_indices:
            continue
        r = dr["rect"]
        # PyMuPDF marks axis-aligned straight lines (width == 0 or height == 0) as is_empty;
        # keep them so flowchart connectors and plot axes survive clustering.
        if r.is_infinite or r.x1 < r.x0 or r.y1 < r.y0 or (r.width <= 0.0 and r.height <= 0.0):
            continue
        if _is_page_background(r, pw, ph) or _is_full_bleed_edge_strip(r, page_rect):
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
            is_tall_backdrop = (
                r.height >= 0.45 * ph
                and r.width >= 0.12 * pw
                and _words_inside_count(r) >= 10
            )
            if is_highlight or r.width >= 0.30 * pw or is_tall_backdrop:
                continue
        elif dr.get("fill") is None and r.height >= 0.40 * ph and r.width >= 0.12 * pw and rasters:
            inside_rasters = sorted(
                (rr for rr in rasters if _rect_center_inside(rr, r)),
                key=lambda x: x.y0,
            )
            if len(inside_rasters) >= 2:
                max_gap = max(
                    inside_rasters[k + 1].y0 - inside_rasters[k].y1
                    for k in range(len(inside_rasters) - 1)
                )
                if max_gap >= 40.0 and _words_inside_count(r) >= 10:
                    continue

        filtered.append(dr)

    return filtered


def _has_non_grid_detail(
    drawings: list[dict] | None, rect: pymupdf.Rect, min_count: int = 12
) -> bool:
    """Return True if `drawings` inside `rect` contain >= `min_count` curves or slanted lines."""
    if not drawings:
        return False
    count = 0
    for dr in drawings:
        if not rect.contains(dr["rect"]):
            continue
        for item in dr.get("items") or ():
            kind = item[0]
            if kind in ("c", "qu"):
                count += 1
            elif kind == "l" and len(item) >= 3:
                p0, p1 = item[1], item[2]
                if abs(p0.x - p1.x) > 2.0 and abs(p0.y - p1.y) > 2.0:
                    count += 1
            if count >= min_count:
                return True
    return False


def _is_valid_vector_cluster(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    filtered_rects: list[pymupdf.Rect],
    raster_rects: list[pymupdf.Rect],
    text_blocks: list[TextBlock],
    fig_captions: list[TextBlock],
    page_raw_clusters: int = 0,
    filtered_drawings: list[dict] | None = None,
) -> bool:
    """Reject tiny artifacts, edge badges, prose blocks, data tables, and outlined text."""
    pw, ph = page.rect.width, page.rect.height
    if _is_page_background(rect, pw, ph):
        return False

    has_fig_cap = _match_caption(rect, fig_captions, text_blocks) is not None
    dim_scale = 1.0 if has_fig_cap else max(1.0, min(pw, ph) / 792.0)
    min_dim = 42.0 * dim_scale
    if rect.width < min_dim or rect.height < min_dim:
        return False
    if _is_edge_ornament(rect, page.rect, fig_captions):
        return False

    txt = page.get_text("text", clip=rect).strip()
    word_count = len(txt.split())
    if word_count > 200:
        return False

    if word_count > 80 and not has_fig_cap:
        return False

    if word_count >= 6:
        tab_captions = [tb for tb in text_blocks if tb.kind == "tab_caption"]
        has_tab_cap = _match_caption(rect, tab_captions, text_blocks) is not None
        if not (has_fig_cap and not has_tab_cap):
            if has_tab_cap and not has_fig_cap:
                return False
            tabs = page.find_tables(clip=rect)
            if not _has_non_grid_detail(filtered_drawings, rect) and any(
                pymupdf.Rect(t.bbox).get_area() > 0.45 * rect.get_area()
                and t.row_count >= 2
                and t.col_count >= 2
                for t in tabs.tables
            ):
                return False
        if word_count >= 20:
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
        if not has_fig_cap and len(inside) <= 2:
            return False
        if not has_fig_cap and rect.height >= 0.50 * ph and rect.width <= 0.18 * pw:
            return False
        if not has_fig_cap and inside and all(min(x.width, x.height) <= 3.0 for x in inside):
            h_rules = sum(1 for x in inside if x.height <= 3.0 and x.width >= 0.4 * rect.width)
            v_rules = sum(1 for x in inside if x.width <= 3.0 and x.height >= 0.4 * rect.height)
            if (
                (word_count >= 6 and h_rules >= 2 and v_rules >= 1)
                or (h_rules >= 3 and v_rules >= 2)
                or (
                    filtered_drawings is not None
                    and word_count >= 10
                    and h_rules >= 2
                    and not _has_non_grid_detail(filtered_drawings, rect, min_count=1)
                )
            ):
                return False
        if not has_fig_cap and inside:
            glyph_cap = 12.0 * max(1.0, min(pw, ph) / 792.0)
            tiny_glyphs = sum(
                1 for x in inside if x.width <= glyph_cap and x.height <= glyph_cap
            )
            tiny_ratio = tiny_glyphs / len(inside)
            long_parts = sum(
                1 for x in inside if max(x.width, x.height) >= 0.45 * min(rect.width, rect.height)
            )
            if long_parts < 2 and (
                (len(inside) >= 120 and tiny_ratio >= 0.72)
                or (len(inside) >= 35 and word_count == 0 and tiny_ratio >= 0.85)
            ):
                return False
        if (
            not has_fig_cap
            and page_raw_clusters >= 80
            and word_count == 0
            and len(inside) <= 16
            and (rect.width * rect.height) < 0.03 * pw * ph
        ):
            return False

    return True


def _is_short_axis_label(tb: TextBlock, vertical_ok: bool = False) -> bool:
    """Return True for compact non-prose axis ticks or plot axis titles."""
    if tb.kind != "text":
        return False
    if vertical_ok and tb.rect.width <= 28.0 and tb.rect.height >= 2.5 * tb.rect.width:
        return True
    cleaned = _clean_text(tb.text)
    return (
        tb.rect.height <= 26.0
        and len(cleaned.split()) <= 4
        and not cleaned.endswith(".")
    )


def _match_caption_scored(
    rect: pymupdf.Rect,
    fig_captions: list[TextBlock],
    text_blocks: list[TextBlock],
    excluded: set[int] | None = None,
) -> tuple[int | None, float]:
    """Return `(best_caption_idx, distance_score)` for `rect`."""
    best_idx: int | None = None
    best_dist = float("inf")

    for idx, cap in enumerate(fig_captions):
        if excluded and idx in excluded:
            continue
        cr = cap.rect
        h_ov = _horiz_overlap(rect, cr)
        min_ov = min(28.0, 0.30 * min(rect.width, cr.width))
        needs_axis_bridge = False

        if h_ov >= min_ov:
            gap_below = cr.y0 - rect.y1
            if -14.0 <= gap_below <= 78.0:
                dist = abs(gap_below)
                needs_axis_bridge = gap_below > 64.0
            elif -14.0 <= rect.y0 - cr.y1 <= 64.0:
                dist = abs(rect.y0 - cr.y1) + 18.0
            else:
                dist = float("inf")
        elif _vert_overlap(rect, cr) >= 10.0 and (
            abs(cr.y0 - rect.y0) <= 35.0 or abs(cr.y1 - rect.y1) <= 35.0
        ):
            gap_x = max(0.0, max(rect.x0, cr.x0) - min(rect.x1, cr.x1))
            dist = gap_x + 10.0 if gap_x <= 35.0 else float("inf")
        else:
            continue

        if dist < best_dist:
            span = rect | cr
            blocked = False
            max_axis_y1 = -1.0
            for tb in text_blocks:
                if tb.rect == cr or tb.kind == "fig_caption":
                    continue
                if (
                    needs_axis_bridge
                    and _horiz_overlap(tb.rect, span) >= 10.0
                    and rect.y1 - 2.0 <= tb.rect.y0
                    and tb.rect.y1 <= cr.y0 + 2.0
                    and _is_short_axis_label(tb)
                ):
                    max_axis_y1 = max(max_axis_y1, tb.rect.y1)
                tb_words = tb.text.split()
                if len(tb_words) < 4:
                    continue
                if len(tb_words) <= 16 and _SUBPANEL_LABEL_RE.match(_clean_text(tb.text)):
                    continue
                if (
                    cr.y1 <= rect.y0
                    and 0.0 <= tb.rect.y0 - cr.y1 <= 10.0
                    and len(tb_words) <= 14
                    and tb.rect.height <= 26.0
                    and _horiz_overlap(tb.rect, cr) >= 20.0
                ):
                    continue
                if (
                    _horiz_overlap(tb.rect, span) >= 20.0
                    and ((rect.y1 <= tb.rect.y0 + 2 and tb.rect.y1 <= cr.y0 + 2)
                         or (cr.y1 <= tb.rect.y0 + 2 and tb.rect.y1 <= rect.y0 + 2))
                ):
                    blocked = True
                    break
            if needs_axis_bridge and (max_axis_y1 < 0.0 or (cr.y0 - max_axis_y1) > 45.0):
                blocked = True
            if not blocked:
                best_dist = dist
                best_idx = idx

    return best_idx, best_dist


def _match_caption(
    rect: pymupdf.Rect, fig_captions: list[TextBlock], text_blocks: list[TextBlock]
) -> int | None:
    """Find the most likely figure caption belonging to `rect`, if any."""
    idx, _ = _match_caption_scored(rect, fig_captions, text_blocks)
    return idx


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
                gap = _rect_gap(a.rect, b.rect)
                shares_col = _horiz_overlap(a.rect, b.rect) >= 0.25 * min(a.rect.width, b.rect.width)
                if gap > (24.0 if shares_col else 18.0):
                    continue
                if _has_obstacle_between(a.rect, b.rect, text_blocks, rules, allow_axis_labels=shares_col):
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
    allow_axis_labels: bool = False,
) -> bool:
    """Return True if a prose/caption block or divider rule lies strictly between `a` and `b`."""
    if a.y1 <= b.y0 or b.y1 <= a.y0:
        top, bot = (a, b) if a.y1 <= b.y0 else (b, a)
        x_lo, x_hi = min(a.x0, b.x0), max(a.x1, b.x1)
        for tb in text_blocks:
            if allow_axis_labels and _is_short_axis_label(tb):
                continue
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
            if allow_axis_labels and _is_short_axis_label(tb, vertical_ok=True):
                continue
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
    same_cap = a.caption_idx is not None and a.caption_idx == b.caption_idx
    if _has_obstacle_between(a.rect, b.rect, text_blocks, rules, allow_axis_labels=same_cap):
        return False
    if _is_table_row_pair(a.rect, b.rect, text_blocks):
        return False

    gap = _rect_gap(a.rect, b.rect)
    if same_cap:
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


def _resolve_opposing_captions(
    candidates: list[CandidateBox],
    scores: list[float],
    fig_captions: list[TextBlock],
    text_blocks: list[TextBlock],
) -> None:
    """Prevent a caption between two vertically stacked figures from claiming both sides."""
    by_cap: dict[int, list[int]] = {}
    for ci, cand in enumerate(candidates):
        if cand.caption_idx is not None:
            by_cap.setdefault(cand.caption_idx, []).append(ci)

    losing_side: dict[int, set[int]] = {}
    for cap_idx, idxs in by_cap.items():
        if len(idxs) < 2:
            continue
        cap_cy = 0.5 * (fig_captions[cap_idx].rect.y0 + fig_captions[cap_idx].rect.y1)
        above = [i for i in idxs if 0.5 * (candidates[i].rect.y0 + candidates[i].rect.y1) < cap_cy]
        below = [i for i in idxs if 0.5 * (candidates[i].rect.y0 + candidates[i].rect.y1) >= cap_cy]
        if not (above and below):
            continue
        best_above_i = min(above, key=lambda i: scores[i])
        best_below_i = min(below, key=lambda i: scores[i])
        best_above = scores[best_above_i]
        best_below = scores[best_below_i]
        losers = below if best_above <= best_below else above

        # Yield to `below` when the above candidate has an unclaimed caption of its own
        # and the below candidate sits within comparable raw edge distance.
        if best_above <= best_below:
            alt_above, _ = _match_caption_scored(
                candidates[best_above_i].rect,
                fig_captions,
                text_blocks,
                excluded=set(by_cap.keys()),
            )
            if alt_above is not None and (best_below - 18.0) <= (best_above + 6.0):
                losers = above

        for i in losers:
            losing_side.setdefault(i, set()).add(cap_idx)

    for ci, excluded in losing_side.items():
        new_cap, _ = _match_caption_scored(
            candidates[ci].rect, fig_captions, text_blocks, excluded=excluded
        )
        candidates[ci].caption_idx = new_cap


def _group_figures(
    raster_rects: list[pymupdf.Rect],
    vector_rects: list[pymupdf.Rect],
    text_blocks: list[TextBlock],
    rules: list[pymupdf.Rect],
) -> list[CandidateBox]:
    """Fuse overlapping raster/vector parts and merge multi-panel figures cleanly."""
    fig_captions = [tb for tb in text_blocks if tb.kind == "fig_caption"]

    base_rects = _merge_touching(raster_rects + vector_rects, pad=2.0)
    candidates: list[CandidateBox] = []
    scores: list[float] = []
    for r in base_rects:
        cap_idx, dist = _match_caption_scored(r, fig_captions, text_blocks)
        candidates.append(CandidateBox(r, cap_idx))
        scores.append(dist)

    _resolve_opposing_captions(candidates, scores, fig_captions, text_blocks)
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


def _fallback_search_band(
    cr: pymupdf.Rect,
    page_rect: pymupdf.Rect,
    direction: int,
    text_blocks: list[TextBlock],
    rules: list[pymupdf.Rect],
    existing_rects: list[pymupdf.Rect],
) -> pymupdf.Rect:
    """Compute the obstacle-free rectangular search band below (+1) or above (-1) `cr`."""
    pw, ph = page_rect.width, page_rect.height
    pad_x = 120.0 if cr.width < 0.50 * pw else 50.0
    bx0 = max(page_rect.x0, cr.x0 - pad_x)
    bx1 = min(page_rect.x1, cr.x1 + pad_x)
    max_reach = min(0.55 * ph, 380.0)

    if direction > 0:
        band_y0 = cr.y1 - 4.0
        band_y1 = min(page_rect.y1 - 24.0, cr.y1 + max_reach)
        band_span = pymupdf.Rect(bx0, band_y0, bx1, band_y1)
        for tb in text_blocks:
            if tb.rect != cr and _horiz_overlap(tb.rect, band_span) >= 25.0 and tb.rect.y0 >= cr.y1 + 2.0:
                if tb.kind in ("fig_caption", "tab_caption") or (tb.kind == "text" and len(tb.text.split()) >= 10):
                    band_y1 = min(band_y1, tb.rect.y0 + 2.0)
        for rr in rules:
            if rr.height <= 4.0 and rr.width >= 0.60 * pw and rr.y0 >= cr.y1 + 6.0:
                band_y1 = min(band_y1, rr.y0 + 2.0)
        for er in existing_rects:
            if _horiz_overlap(er, cr) >= 20.0 and er.y0 >= cr.y1 - 4.0:
                band_y1 = min(band_y1, er.y0 - 2.0)
    else:
        band_y1 = cr.y0 + 4.0
        band_y0 = max(page_rect.y0 + 24.0, cr.y0 - max_reach)
        band_span = pymupdf.Rect(bx0, band_y0, bx1, band_y1)
        for tb in text_blocks:
            if tb.rect != cr and _horiz_overlap(tb.rect, band_span) >= 25.0 and tb.rect.y1 <= cr.y0 - 2.0:
                if tb.kind in ("fig_caption", "tab_caption") or (tb.kind == "text" and len(tb.text.split()) >= 10):
                    band_y0 = max(band_y0, tb.rect.y1 - 2.0)
        for rr in rules:
            if rr.height <= 4.0 and rr.width >= 0.60 * pw and rr.y1 <= cr.y0 - 6.0:
                band_y0 = max(band_y0, rr.y1 - 2.0)
        for er in existing_rects:
            if _horiz_overlap(er, cr) >= 20.0 and er.y1 <= cr.y0 + 4.0:
                band_y0 = max(band_y0, er.y1 + 2.0)

    return pymupdf.Rect(bx0, band_y0, bx1, band_y1)


def _collect_caption_fallback_vectors(
    page: pymupdf.Page,
    filtered: list[dict],
    filtered_rects: list[pymupdf.Rect],
    raster_rects: list[pymupdf.Rect],
    existing_candidates: list[CandidateBox],
    text_blocks: list[TextBlock],
    fig_captions: list[TextBlock],
    rules: list[pymupdf.Rect],
    page_raw_clusters: int,
) -> list[pymupdf.Rect]:
    """Recover disconnected vector charts (e.g., axis-less bar groups) beneath orphaned captions."""
    assigned = {c.caption_idx for c in existing_candidates if c.caption_idx is not None}
    extra_vecs: list[pymupdf.Rect] = []
    existing_rects = [c.rect for c in existing_candidates]

    for cap_idx, cap in enumerate(fig_captions):
        if cap_idx in assigned:
            continue

        for direction in (1, -1):
            band = _fallback_search_band(
                cap.rect, page.rect, direction, text_blocks, rules, existing_rects
            )
            if band.height < 42.0 or band.width < 42.0:
                continue

            band_drawings = [
                dr
                for dr in filtered
                if _rect_center_inside(dr["rect"], band)
                and not any(er.contains(dr["rect"]) for er in existing_rects)
            ]
            if len(band_drawings) < 4:
                continue

            found_here = False
            for c in page.cluster_drawings(drawings=band_drawings, x_tolerance=48, y_tolerance=24):
                if any(c.intersects(er) for er in existing_rects):
                    continue
                if sum(1 for r in filtered_rects if c.contains(r)) < 4:
                    continue
                if _match_caption(c, fig_captions, text_blocks) != cap_idx:
                    continue
                if _is_valid_vector_cluster(
                    page,
                    c,
                    filtered_rects,
                    raster_rects,
                    text_blocks,
                    fig_captions,
                    page_raw_clusters=page_raw_clusters,
                    filtered_drawings=filtered,
                ):
                    extra_vecs.append(c)
                    found_here = True
            if found_here:
                break

    return extra_vecs


def _collect_page_candidates(
    page: pymupdf.Page,
) -> tuple[list[CandidateBox], list[TextBlock], list[TextBlock], bool]:
    """Collect figure candidates, text blocks, figure captions, and scan flag for `page`."""
    _ensure_pymupdf()
    pw, ph = page.rect.width, page.rect.height
    text_blocks = _collect_text_blocks(page)
    fig_captions = [tb for tb in text_blocks if tb.kind == "fig_caption"]

    words = page.get_text("words")
    raster_rects, has_full_page_img = _collect_raster_boxes(
        page, fig_captions, words=words, text_blocks=text_blocks
    )

    drawings = page.get_drawings()
    vector_rects: list[pymupdf.Rect] = []
    filtered: list[dict] = []
    filtered_rects: list[pymupdf.Rect] = []
    rules: list[pymupdf.Rect] = []
    raw_cluster_count = 0
    if drawings:
        rules = _collect_separator_rules(drawings, pw, ph)
        filtered = _filter_drawings_for_clustering(
            drawings, page.rect, words, raster_rects=raster_rects
        )
        if filtered:
            filtered_rects = [dr["rect"] for dr in filtered]
            raw_clusters = page.cluster_drawings(drawings=filtered, x_tolerance=5, y_tolerance=5)
            raw_cluster_count = len(raw_clusters)
            for c in raw_clusters:
                if _is_valid_vector_cluster(
                    page,
                    c,
                    filtered_rects,
                    raster_rects,
                    text_blocks,
                    fig_captions,
                    page_raw_clusters=raw_cluster_count,
                    filtered_drawings=filtered,
                ):
                    vector_rects.append(c)

    all_vecs = list(vector_rects)
    candidates = _group_figures(raster_rects, all_vecs, text_blocks, rules)
    if filtered and fig_captions:
        fallback_vecs = _collect_caption_fallback_vectors(
            page,
            filtered,
            filtered_rects,
            raster_rects,
            candidates,
            text_blocks,
            fig_captions,
            rules,
            raw_cluster_count,
        )
        if fallback_vecs:
            all_vecs = vector_rects + fallback_vecs
            candidates = _group_figures(raster_rects, all_vecs, text_blocks, rules)

    _annotate_candidate_origins(candidates, raster_rects, all_vecs, filtered_rects)
    is_scanned = has_full_page_img and not candidates
    return candidates, text_blocks, fig_captions, is_scanned


def collect_page_figures(page: pymupdf.Page) -> tuple[list[pymupdf.Rect], bool]:
    """Collect logical figure bounding boxes on `page` and flag scanned pages."""
    _ensure_pymupdf()
    candidates, _, _, is_scanned = _collect_page_candidates(page)
    return [c.rect for c in candidates], is_scanned


def extract_images(
    pdf_path: Path,
    out_dir: Path,
    dpi: int = 180,
    write_meta: bool = False,
    stdout_meta: bool = False,
    max_meta_words: int = 20,
    max_meta_bytes: int = 16384,
) -> list[Path]:
    """Render every detected bitmap or vector figure region in `pdf_path` to PNG."""
    _ensure_pymupdf()
    assert_local_no_unc_path(pdf_path, "ResolvedPdf")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if dpi < 36 or dpi > 1200:
        raise ValueError(f"dpi must be between 36 and 1200 (got {dpi})")

    safe_out_dir = resolve_safe_out_directory(out_dir, "-OutDir", create=False)
    saved: list[Path] = []
    scanned_pages: list[int] = []
    manifest_items: list[dict] = []

    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise RuntimeError(f"PDF is password-protected/encrypted and cannot be extracted: {pdf_path}")

        safe_out_dir.mkdir(parents=True, exist_ok=True)
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
                out_path = safe_out_dir / out_name
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

    print(f"Extracted {len(saved)} figures -> {safe_out_dir}")
    if scanned_pages:
        print(
            f"[Note] Detected {len(scanned_pages)} scanned/full-page image page(s): {scanned_pages}"
        )
    if write_meta:
        meta_path = safe_out_dir / "manifest.json"
        meta = {
            "pdf": pdf_path.name,
            "dpi": dpi,
            "total_pages": total_pages,
            "scanned_pages": scanned_pages,
            "figures": manifest_items,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote manifest -> {meta_path}")
        if stdout_meta:
            emit_compacted_manifest_stdout(
                meta,
                meta_path,
                max_words=max_meta_words,
                max_bytes=max_meta_bytes,
            )
    return saved
