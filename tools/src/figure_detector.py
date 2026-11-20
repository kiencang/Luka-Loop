"""Layout-aware PDF figure, diagram, and chart detector (6-phase linear pipeline on PyMuPDF).

Architecture (strictly top-to-bottom, zero circular calls):
  Phase 1 — analyze_page()          : Build PageContext once (text blocks, captions, words, rules).
  Phase 2 — detect_raster_regions() : Extract foreground bitmaps, detect scanned pages, drop banners/watermarks.
  Phase 3 — detect_vector_regions() : Filter background drawings, cluster vectors, classify via RegionFeatures.
  Phase 4 — link_captions()         : Match captions (vertical > side), arbitrate conflicts, propagate & recover.
  Phase 5 — merge_candidates()      : Merge multi-panel figures under strict anti-swallow geometric invariants.
  Phase 6 — finalize & render       : Annotate origin/table_cell placement, sort reading order, emit PNG + manifest.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from image_ops import MAX_RENDER_DIM, MAX_RENDER_PIXELS, compute_safe_render_zoom, ensure_pymupdf
from manifest import emit_compacted_manifest_stdout
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


# ==============================================================================
# 0. Configuration & Data Models
# ==============================================================================


@dataclass(frozen=True)
class DetectorConfig:
    """Centralized geometric and heuristic thresholds (units: PDF points or page fractions)."""

    # Phase 1: Text & caption segmentation
    col_split_gap_x: float = 12.0
    caption_cont_max_gap_y: float = 5.5
    # Phase 2 & 3: Page background, bleed, and ornament thresholds
    bg_area_ratio: float = 0.78
    bg_width_ratio: float = 0.90
    bg_height_ratio: float = 0.85
    vert_bleed_h_ratio: float = 0.92
    vert_bleed_w_ratio: float = 0.18
    horiz_bleed_w_ratio: float = 0.92
    horiz_bleed_h_ratio: float = 0.16
    hero_banner_h_ratio: float = 0.22
    hero_banner_min_words: int = 4
    # Phase 2: Raster dimensions
    min_raster_dim: float = 36.0
    min_raster_area: float = 1600.0
    min_strip_short_dim: float = 16.0
    min_strip_long_dim: float = 100.0
    min_strip_area: float = 1800.0
    # Phase 3: Vector clustering & text density
    cluster_tol_x: float = 5.0
    cluster_tol_y: float = 5.0
    min_vector_dim: float = 42.0
    max_vector_words: int = 200
    max_uncaptioned_vector_words: int = 80
    max_page_drawings: int = 200000
    dense_drawing_downsample_threshold: int = 2500
    dense_drawing_grid_pt: float = 6.0
    max_clustered_drawings: int = 12000
    # Phase 4: Caption linking & sibling propagation
    caption_below_max_gap: float = 64.0
    caption_below_bridge_gap: float = 96.0
    caption_above_max_gap: float = 68.0
    caption_side_max_gap_x: float = 35.0
    caption_side_align_y: float = 35.0
    sibling_col_max_gap: float = 68.0
    sibling_row_max_gap: float = 42.0
    # Phase 5: Candidate merging
    touch_pad: float = 2.0
    same_caption_merge_gap: float = 68.0
    same_caption_row_merge_gap: float = 74.0
    touching_merge_gap: float = 4.0


DEFAULT_CONFIG = DetectorConfig()

_LEAD_TRIM_RE = re.compile(r"^[\s•·▪▫▶►▸●○■□.\-–—*:]+")
_OPT_SUPP_PREFIX = r"(?:(?i:supplementary|extended\s+data|appendix)\s+)?"
_CAPTION_ID_BODY = (
    r"(?:(?:\s+|(?<=\.)\s*)(?:\d+(?:[.\-]\d+)*(?:[a-zA-Z])?|[IVXLCDM]+|[SA-Z]\.?\d+(?:[.\-]\d+)*(?:[a-zA-Z])?)"
    r"|\d+(?:[.\-]\d+)*(?:[a-zA-Z])?)"
)
_CAPTION_BOUNDARY = r"(?=$|[\s.:;\-–—|)\],])"
_FIG_CAPTION_RE = re.compile(
    rf"^{_OPT_SUPP_PREFIX}"
    r"(?i:figures?\.?|figs?\.?|hình(?:\s+(?:ảnh|minh\s+họa))?|sơ\s*đồ|biểu\s*đồ|scheme|chart|plate|diagram)"
    rf"{_CAPTION_ID_BODY}{_CAPTION_BOUNDARY}"
)
_TAB_CAPTION_RE = re.compile(
    rf"^{_OPT_SUPP_PREFIX}"
    r"(?i:tables?\.?|tabs?\.?|bảng)"
    rf"{_CAPTION_ID_BODY}{_CAPTION_BOUNDARY}"
)
_PROSE_AFTER_NUM_RE = re.compile(
    r"^\s+(?:shows|illustrates|presents|depicts|demonstrates|summarizes|compares|contrasts|displays|"
    r"indicates|lists|provides|gives|reports|reveals|confirms|suggests|highlights|describes|details|"
    r"evaluates|examines|explains|explores|contains|includes|measures|outlines|plots|records|reflects|"
    r"tracks|traces|is|was|are|were|has|have|can|may|will|"
    r"that|where|when|which|while|whereas|because|since|if|unless|although|though|after|before|until|"
    r"during|between|among|within|without|under|over|above|below|through|across|along|around|near|"
    r"against|despite|could|would|should|must|might|had|does|did|do|we|it|they|this|these|those|our|"
    r"their|its|here|there|also|only|still|already|clearly|further|again|"
    r"cho\s+thấy|minh\s+họa|mô\s+tả|trình\s+bày|tóm\s+tắt|so\s+sánh|chỉ\s+ra|thể\s+hiện)\b",
)
_PLURAL_CAPTION_NOUN_RE = re.compile(
    rf"^{_OPT_SUPP_PREFIX}(?i:figures\.?|figs\.?|tables\.?|tabs\.?)\b"
)
_PLURAL_PROSE_AFTER_NUM_RE = re.compile(
    r"^\s+(?:show|illustrate|present|depict|demonstrate|summarize|compare|contrast|display|indicate|"
    r"list|provide|give|report|reveal|confirm|suggest|highlight|describe|detail|evaluate|examine|"
    r"explain|explore|contain|include|measure|outline|plot|record|reflect|track|trace)\b",
)
_COMMA_PROSE_AFTER_NUM_RE = re.compile(r"^\s*,\s+[a-z]")
_INLINE_REF_AFTER_NUM_RE = re.compile(
    r"^(?:\s*[\)\]]|\s+(?:and|or)\s+(?i:fig(?:ure)?s?\.?|tables?\.?|tabs?\.?)\b|"
    r"\s+(?:for|as|to|in|on|at|with|by|from)\s+(?:a|an|the|this|more|further|details?|comparison|illustration|explanation)\b)"
)
_SUBPANEL_LABEL_RE = re.compile(r"^(?:\([a-zA-Z0-9]{1,2}\)|[a-zA-Z]\)\s)")
_NUMERIC_TOKEN_RE = re.compile(r"^[($€£¥+\-−±≈~<>≤≥]?\d[\d,./:%×x^eE+\-–—]*[)%°]?$|^(?:n/a|na|-|—|–)$", re.IGNORECASE)
_TICK_TOKEN_RE = re.compile(
    r"^[($€£¥+\-−±]?\d[\d,./:%^eE+\-]*[)%°]?$|^\([a-zA-Z0-9]{1,2}\)$|^[xyztrfkpqvnmXYZT]$"
)
_SECTION_HEADING_RE = re.compile(
    r"^(?:(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.)\s+[A-Z][a-zA-Z]{2,}|(?:Abstract|Introduction|Conclusion|References|Appendix|Methods|Results|Discussion)\b)"
)


@dataclass
class TextBlock:
    rect: pymupdf.Rect
    text: str
    kind: str  # "fig_caption", "tab_caption", "text"
    word_count: int = 0

    def __post_init__(self) -> None:
        if self.word_count == 0 and self.text:
            self.word_count = len(self.text.split())


@dataclass
class CandidateBox:
    rect: pymupdf.Rect
    caption_idx: int | None = None
    caption_side: str = ""  # "below", "above", "side", ""
    caption_score: float = float("inf")
    source: str = "vector"  # "raster", "vector", "hybrid"
    drawings: int = 0
    origin_kind: str = "vector"  # "raster" | "vector"


@dataclass(frozen=True)
class FilterDecision:
    keep: bool
    reason: str
    soft_reject: bool = False


@dataclass
class PageTableInfo:
    rect: pymupdf.Rect
    row_count: int
    col_count: int


@dataclass
class PageContext:
    """Single-pass extracted structure of one PDF page shared across all pipeline phases."""

    page: pymupdf.Page
    page_rect: pymupdf.Rect
    pw: float
    ph: float
    text_blocks: list[TextBlock]
    fig_captions: list[TextBlock]
    tab_captions: list[TextBlock]
    words: list[tuple]
    word_rects: list[pymupdf.Rect]
    drawings: list[dict]
    separator_rules: list[pymupdf.Rect]
    trace: list[str] = field(default_factory=list)
    _page_tables: list[PageTableInfo] | None = None

    def get_page_tables(self) -> list[PageTableInfo]:
        """Lazily run whole-page `find_tables()` at most once per page."""
        if self._page_tables is None:
            self._page_tables = [
                PageTableInfo(pymupdf.Rect(t.bbox), t.row_count, t.col_count)
                for t in self.page.find_tables().tables
            ]
        return self._page_tables

    def log(self, msg: str) -> None:
        self.trace.append(msg)


# ==============================================================================
# 1. Phase 1 — Page Context & Text/Caption Analysis
# ==============================================================================


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


def _split_dict_block(blk: dict, cfg: DetectorConfig = DEFAULT_CONFIG) -> list[TextBlock]:
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
        if gap_x >= cfg.col_split_gap_x or caption_split:
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


def _merge_caption_continuations(
    blocks: list[TextBlock],
    rules: list[pymupdf.Rect],
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> list[TextBlock]:
    """Re-attach continuation lines of a multi-line caption split into adjacent dict blocks."""
    if len(blocks) < 2:
        return blocks

    consumed: set[int] = set()
    changed = True
    while changed:
        changed = False
        for i, cap in enumerate(blocks):
            if i in consumed or cap.kind not in ("fig_caption", "tab_caption"):
                continue
            cap_clean = _clean_text(cap.text)
            cap_ends_sentence = cap_clean.endswith((".", "!", "?"))

            best_j: int | None = None
            best_gap = cfg.caption_cont_max_gap_y + 0.1
            for j, nxt in enumerate(blocks):
                if j == i or j in consumed or nxt.kind != "text":
                    continue
                gap_y = nxt.rect.y0 - cap.rect.y1
                if not (-2.0 <= gap_y <= cfg.caption_cont_max_gap_y):
                    continue
                if nxt.rect.x0 < cap.rect.x0 - 10.0 or nxt.rect.x0 > cap.rect.x0 + 60.0:
                    continue
                if nxt.rect.x1 > cap.rect.x1 + 35.0:
                    continue
                if _horiz_overlap(cap.rect, nxt.rect) < 0.35 * min(cap.rect.width, nxt.rect.width):
                    continue
                nxt_clean = _clean_text(nxt.text)
                if not nxt_clean:
                    continue
                if cap_ends_sentence and not (nxt_clean[0].islower() or nxt_clean[0] in "(["):
                    continue
                if any(
                    rr.height <= 4.0
                    and cap.rect.y1 - 1.0 <= rr.y0 <= nxt.rect.y0 + 1.0
                    and _horiz_overlap(rr, cap.rect | nxt.rect) >= 0.4 * cap.rect.width
                    for rr in rules
                ):
                    continue
                if gap_y < best_gap:
                    best_gap = gap_y
                    best_j = j

            if best_j is not None:
                nxt = blocks[best_j]
                cap.rect = cap.rect | nxt.rect
                cap.text = cap.text.rstrip() + "\n" + nxt.text.lstrip()
                cap.word_count = len(cap.text.split())
                consumed.add(best_j)
                changed = True

    return [b for idx, b in enumerate(blocks) if idx not in consumed]


def _collect_separator_rules(drawings: list[dict], pw: float, ph: float) -> list[pymupdf.Rect]:
    """Identify long thin horizontal/vertical rules used as table/section dividers."""
    rules: list[pymupdf.Rect] = []
    for dr in drawings:
        r = dr["rect"]
        if r.height <= 4.0 and r.width >= 0.25 * pw:
            rules.append(r)
        elif r.width <= 4.0 and r.height >= 0.30 * ph:
            rules.append(r)
    return rules


def analyze_page(page: pymupdf.Page, cfg: DetectorConfig = DEFAULT_CONFIG) -> PageContext:
    """Phase 1: Build reusable `PageContext` once per page."""
    _ensure_pymupdf()
    page_rect = page.rect
    pw, ph = page_rect.width, page_rect.height

    drawings = page.get_drawings()
    rules = _collect_separator_rules(drawings, pw, ph) if drawings else []

    raw_blocks: list[TextBlock] = []
    for b in page.get_text("dict").get("blocks", ()):
        if b.get("type") != 0:
            continue
        raw_blocks.extend(_split_dict_block(b, cfg=cfg))
    text_blocks = _merge_caption_continuations(raw_blocks, rules, cfg=cfg)

    fig_captions = [tb for tb in text_blocks if tb.kind == "fig_caption"]
    tab_captions = [tb for tb in text_blocks if tb.kind == "tab_caption"]
    words = page.get_text("words")
    word_rects = [pymupdf.Rect(w[:4]) for w in words]

    return PageContext(
        page=page,
        page_rect=page_rect,
        pw=pw,
        ph=ph,
        text_blocks=text_blocks,
        fig_captions=fig_captions,
        tab_captions=tab_captions,
        words=words,
        word_rects=word_rects,
        drawings=drawings,
        separator_rules=rules,
    )


# ==============================================================================
# 2. Geometry & Drawing Feature Primitives
# ==============================================================================


def _horiz_overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))


def _vert_overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def _rect_gap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    """Euclidean gap between two rectangles (0 if overlapping)."""
    dx = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    dy = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    return math.hypot(dx, dy)


def _rect_center_inside(inner: pymupdf.Rect, outer: pymupdf.Rect) -> bool:
    """Return True if `inner`'s midpoint lies inside `outer` (or overlaps >=50%)."""
    cx = 0.5 * (inner.x0 + inner.x1)
    cy = 0.5 * (inner.y0 + inner.y1)
    if outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1:
        return True
    return (inner & outer).get_area() >= 0.5 * max(1.0, inner.get_area())


def _is_frame_for(inner: pymupdf.Rect, outer: pymupdf.Rect) -> bool:
    """Return True if `inner` is just an enclosing border/cell box around `outer`."""
    outer_area = max(1.0, outer.get_area())
    return (inner & outer).get_area() >= 0.85 * outer_area and inner.get_area() >= 0.85 * outer_area


def _is_page_background(r: pymupdf.Rect, pw: float, ph: float, cfg: DetectorConfig = DEFAULT_CONFIG) -> bool:
    """Return True if rectangle covers almost the entire page/slide canvas."""
    area_ratio = (r.width * r.height) / max(1.0, pw * ph)
    return area_ratio >= cfg.bg_area_ratio or (r.width >= cfg.bg_width_ratio * pw and r.height >= cfg.bg_height_ratio * ph)


def _is_vertical_bleed_strip(r: pymupdf.Rect, page_rect: pymupdf.Rect, cfg: DetectorConfig = DEFAULT_CONFIG) -> bool:
    """Return True for narrow full-page-height decorative bleed strips along left/right edges."""
    pw, ph = page_rect.width, page_rect.height
    return (
        r.height >= cfg.vert_bleed_h_ratio * ph
        and r.width <= cfg.vert_bleed_w_ratio * pw
        and (r.x0 <= page_rect.x0 + 12.0 or r.x1 >= page_rect.x1 - 12.0)
    )


def _is_horizontal_bleed_strip(r: pymupdf.Rect, page_rect: pymupdf.Rect, cfg: DetectorConfig = DEFAULT_CONFIG) -> bool:
    """Return True for full-page-width decorative bleed bands along top/bottom edges."""
    pw, ph = page_rect.width, page_rect.height
    return (
        r.width >= cfg.horiz_bleed_w_ratio * pw
        and r.height <= cfg.horiz_bleed_h_ratio * ph
        and (r.y0 <= page_rect.y0 + 12.0 or r.y1 >= page_rect.y1 - 12.0)
    )


def _is_full_bleed_edge_strip(r: pymupdf.Rect, page_rect: pymupdf.Rect, cfg: DetectorConfig = DEFAULT_CONFIG) -> bool:
    return _is_vertical_bleed_strip(r, page_rect, cfg) or _is_horizontal_bleed_strip(r, page_rect, cfg)


def _count_words_inside(box: pymupdf.Rect, word_rects: list[pymupdf.Rect]) -> int:
    return sum(
        1
        for wr in word_rects
        if box.contains(wr) or (box & wr).get_area() >= 0.5 * max(1e-6, wr.get_area())
    )


def _is_hero_header_banner(
    r: pymupdf.Rect, ctx: PageContext, cfg: DetectorConfig = DEFAULT_CONFIG
) -> bool:
    """Return True for top full-bleed datasheet/brochure hero banners overlaid with title text."""
    if r.width < cfg.horiz_bleed_w_ratio * ctx.pw:
        return False
    if r.y0 > ctx.page_rect.y0 + 8.0 or r.height > cfg.hero_banner_h_ratio * ctx.ph:
        return False
    return _count_words_inside(r, ctx.word_rects) >= cfg.hero_banner_min_words


def _is_edge_ornament(r: pymupdf.Rect, page_rect: pymupdf.Rect, fig_captions: list[TextBlock]) -> bool:
    """Filter out small running header/footer logos, page badges, and margin bars."""
    if r.height >= 62.0:
        return False
    top_y, bot_y = page_rect.y0, page_rect.y1
    in_margin = (
        r.y1 < (top_y + 54.0)
        or r.y0 > (bot_y - 45.0)
        or (r.y0 < (top_y + 42.0) and r.height < 50.0)
        or (r.width >= 0.60 * page_rect.width and (r.y0 < (top_y + 36.0) or r.y1 > (bot_y - 36.0)))
    )
    if not in_margin:
        return False
    for cap in fig_captions:
        if _horiz_overlap(r, cap.rect) >= 20.0 and abs(cap.rect.y0 - r.y1) < 40.0:
            return False
    return True


def _merge_touching(
    rects: list[pymupdf.Rect],
    pad: float = 2.0,
    prevent_page_bg: tuple[float, float, DetectorConfig] | None = None,
) -> list[pymupdf.Rect]:
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
                    cand_union = cur | m
                    if prevent_page_bg is not None:
                        pw, ph, cfg = prevent_page_bg
                        if (
                            _is_page_background(cand_union, pw, ph, cfg)
                            and not _is_page_background(cur, pw, ph, cfg)
                            and not _is_page_background(m, pw, ph, cfg)
                        ):
                            rest.append(m)
                            continue
                    cur = cand_union
                    changed = True
                else:
                    rest.append(m)
            merged = rest
        merged.append(cur)
    return sorted(merged, key=lambda x: (round(x.y0, 1), round(x.x0, 1)))


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


def _is_rounded_rect_drawing(dr: dict) -> bool:
    """Return True if `dr` is a rounded rectangle or pill badge (axis-aligned sides + corner arcs).

    Handles both single-Bézier-per-corner renderers (ReportLab, LaTeX, Illustrator: 4–10 items)
    and multi-segment arc renderers (Chromium/Skia, WeasyPrint, Cairo: up to ~44 items).
    """
    items = dr.get("items") or ()
    if not (4 <= len(items) <= 44):
        return False
    r = dr["rect"]
    if r.width < 10.0 or r.height < 6.0:
        return False
    edge_tol = max(3.0, 0.12 * min(r.width, r.height))
    is_pill = max(r.width, r.height) >= 2.2 * min(r.width, r.height) and min(r.width, r.height) <= 24.0
    max_corner = (0.55 * min(r.width, r.height) + 2.0) if is_pill else max(16.0, 0.30 * min(r.width, r.height))
    corners = ((r.x0, r.y0), (r.x1, r.y0), (r.x0, r.y1), (r.x1, r.y1))

    def _near_corner(pt) -> bool:
        return any(max(abs(pt.x - cx), abs(pt.y - cy)) <= max_corner for cx, cy in corners)

    lines = 0
    curves = 0
    for it in items:
        kind = it[0]
        if kind == "l" and len(it) >= 3:
            p0, p1 = it[1], it[2]
            is_h = abs(p0.y - p1.y) <= 1.5
            is_v = abs(p0.x - p1.x) <= 1.5
            if not (is_h or is_v):
                return False
            if is_h and min(abs(p0.y - r.y0), abs(p0.y - r.y1)) > edge_tol:
                return False
            if is_v and min(abs(p0.x - r.x0), abs(p0.x - r.x1)) > edge_tol:
                return False
            if math.hypot(p0.x - p1.x, p0.y - p1.y) >= 1.5:
                lines += 1
        elif kind == "c" and len(it) >= 5:
            p0, p3 = it[1], it[4]
            if not (_near_corner(p0) and _near_corner(p3)):
                return False
            if math.hypot(p0.x - p3.x, p0.y - p3.y) > max_corner * 1.45:
                return False
            curves += 1
        elif kind == "re":
            continue
        else:
            return False
    return curves > 0 and lines >= 2


def _is_tiny_bullet_dot(dr: dict) -> bool:
    """Return True for a tiny strokeless filled dot/bullet (<= 6.5pt), e.g., an HTML list marker."""
    r = dr["rect"]
    return dr.get("color") is None and dr.get("fill") is not None and max(r.width, r.height) <= 6.5


def _is_simple_box_drawing(dr: dict) -> bool:
    """Return True if `dr` is a single rectangular or rounded-rectangular border/backdrop."""
    items = dr.get("items") or ()
    if not items:
        return False
    if len(items) == 1 and items[0][0] == "re":
        return True
    if _is_rounded_rect_drawing(dr):
        return True
    if len(items) <= 5 and all(
        it[0] == "l" and len(it) >= 3 and (abs(it[1].x - it[2].x) <= 1.5 or abs(it[1].y - it[2].y) <= 1.5)
        for it in items
    ):
        return True
    return False


def _has_non_grid_detail(drawings: list[dict] | None, rect: pymupdf.Rect, min_count: int = 12) -> bool:
    """Return True if `drawings` inside `rect` contain >= `min_count` true curves/diagonals (ignoring card corners)."""
    if not drawings:
        return False
    count = 0
    for dr in drawings:
        if not rect.contains(dr["rect"]):
            continue
        if _is_rounded_rect_drawing(dr):
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


def _is_short_axis_label(tb: TextBlock, vertical_ok: bool = False) -> bool:
    """Return True for compact axis titles, rotated Y labels, tick-value rows, or subpanel markers."""
    if tb.kind != "text":
        return False
    cleaned = _clean_text(tb.text)
    if not cleaned or _SECTION_HEADING_RE.match(cleaned):
        return False
    tokens = cleaned.split()
    if vertical_ok and tb.rect.width <= 32.0 and (
        tb.rect.height >= 1.4 * tb.rect.width or (tb.rect.height <= 42.0 and len(tokens) <= 8)
    ):
        return True
    if tb.rect.height <= 30.0 and len(tokens) <= 4 and not cleaned.endswith("."):
        return True
    # Narrow inline math/chemical/axis label whose subscripts/superscripts split into extra short tokens
    if tb.rect.width <= 115.0 and tb.rect.height <= 26.0 and len(tokens) <= 10 and not cleaned.endswith("."):
        return True
    if tb.rect.height <= 26.0 and len(tokens) <= 12:
        tick_hits = sum(1 for tok in tokens if _TICK_TOKEN_RE.match(tok))
        if tick_hits >= max(2, int(math.ceil(0.60 * len(tokens)))):
            return True
    if tb.rect.height <= 26.0 and len(tokens) <= 16 and _SUBPANEL_LABEL_RE.match(cleaned):
        return True
    return False


# ==============================================================================
# 3. Phase 2 — Raster Region Detection
# ==============================================================================


def detect_raster_regions(
    ctx: PageContext, cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[list[pymupdf.Rect], bool]:
    """Phase 2: Collect foreground raster regions and report whether a full-page image exists."""
    raw_rects: list[pymupdf.Rect] = []
    has_full_page_img = False

    for info in ctx.page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"]) & ctx.page_rect
        if r.is_empty or r.width < 1.0 or r.height < 1.0:
            continue
        if _is_page_background(r, ctx.pw, ctx.ph, cfg):
            has_full_page_img = True
            ctx.log(f"raster:skip page_background {r}")
            continue
        if _is_vertical_bleed_strip(r, ctx.page_rect, cfg) and _match_caption(r, ctx.fig_captions, ctx.text_blocks, cfg) is None:
            ctx.log(f"raster:skip vertical_bleed {r}")
            continue
        raw_rects.append(r)

    merged = _merge_touching(raw_rects, pad=cfg.touch_pad)
    kept: list[pymupdf.Rect] = []
    for r in merged:
        if _is_page_background(r, ctx.pw, ctx.ph, cfg):
            has_full_page_img = True
            ctx.log(f"raster:skip tiled_page_background {r}")
            continue
        is_normal_box = r.width >= cfg.min_raster_dim and r.height >= cfg.min_raster_dim and r.get_area() >= cfg.min_raster_area
        is_banner_strip = (
            min(r.width, r.height) >= cfg.min_strip_short_dim
            and max(r.width, r.height) >= cfg.min_strip_long_dim
            and r.get_area() >= cfg.min_strip_area
        )
        if not (is_normal_box or is_banner_strip):
            continue

        has_cap = _match_caption(r, ctx.fig_captions, ctx.text_blocks, cfg) is not None
        if not has_cap and (_is_full_bleed_edge_strip(r, ctx.page_rect, cfg) or _is_hero_header_banner(r, ctx, cfg)):
            ctx.log(f"raster:skip edge_or_hero_banner {r}")
            continue
        if _is_edge_ornament(r, ctx.page_rect, ctx.fig_captions):
            ctx.log(f"raster:skip edge_ornament {r}")
            continue

        if not has_cap:
            if not is_normal_box:
                if r.width < cfg.min_raster_dim and r.height >= 0.45 * ctx.ph:
                    continue
                if any(
                    r.intersects(wr) and _vert_overlap(r, wr) >= 0.45 * min(r.height, wr.height)
                    for wr in ctx.word_rects
                ):
                    ctx.log(f"raster:skip text_overlaid_strip {r}")
                    continue
            else:
                prose_blocks = [
                    tb
                    for tb in ctx.text_blocks
                    if tb.kind == "text"
                    and tb.word_count >= 10
                    and (tb.rect & r).get_area() >= 0.5 * min(tb.rect.get_area(), r.get_area())
                ]
                is_single_col_prose = (
                    _count_words_inside(r, ctx.word_rects) >= 85
                    and any(
                        (tb.rect & r).get_area() >= 0.75 * max(1.0, r.get_area()) and tb.word_count >= 85
                        for tb in prose_blocks
                    )
                )
                if (len(prose_blocks) >= 3 and sum(tb.word_count for tb in prose_blocks) >= 85) or is_single_col_prose:
                    ctx.log(f"raster:skip prose_backdrop_watermark {r}")
                    continue
        kept.append(r)

    return kept, has_full_page_img


# ==============================================================================
# 4. Phase 3 — Vector Region Detection & Feature-Based Classification
# ==============================================================================


def _filter_drawings(
    ctx: PageContext, raster_rects: list[pymupdf.Rect], cfg: DetectorConfig = DEFAULT_CONFIG
) -> list[dict]:
    """Remove page frames, divider rules, highlights, watermarks, and tall sidebar containers."""
    top_y, bot_y = ctx.page_rect.y0, ctx.page_rect.y1
    wm_indices = {i for i, dr in enumerate(ctx.drawings) if _is_light_gray_watermark_glyph(dr)}
    drop_wm = len(wm_indices) >= 4 and any(
        ctx.drawings[i]["rect"].intersects(wr) for i in wm_indices for wr in ctx.word_rects
    )

    filtered: list[dict] = []
    for idx, dr in enumerate(ctx.drawings):
        if drop_wm and idx in wm_indices:
            continue
        r = dr["rect"]
        # Keep axis-aligned straight lines (width == 0 or height == 0) for flowchart connectors & plot axes.
        if r.is_infinite or r.x1 < r.x0 or r.y1 < r.y0 or (r.width <= 0.0 and r.height <= 0.0):
            continue
        if (
            r.x1 < ctx.page_rect.x0
            or r.x0 > ctx.page_rect.x1
            or r.y1 < ctx.page_rect.y0
            or r.y0 > ctx.page_rect.y1
        ):
            continue
        if _is_page_background(r, ctx.pw, ctx.ph, cfg) or _is_full_bleed_edge_strip(r, ctx.page_rect, cfg):
            continue
        if r.height <= 4.0 and r.width >= 0.62 * ctx.pw:
            continue
        if r.width <= 4.0 and r.height >= 0.45 * ctx.ph:
            continue
        if (r.y1 < (top_y + 48.0) or r.y0 > (bot_y - 40.0)) and r.height < 28.0:
            continue

        if dr.get("color") is None and dr.get("fill") is not None:
            is_highlight = 4.0 <= r.height <= 24.0 and any(
                r.intersects(wr) and _vert_overlap(r, wr) >= 0.5 * min(r.height, wr.height)
                for wr in ctx.word_rects
            )
            is_tall_backdrop = (
                r.height >= 0.45 * ctx.ph
                and r.width >= 0.12 * ctx.pw
                and _count_words_inside(r, ctx.word_rects) >= 10
            )
            if is_highlight or r.width >= 0.30 * ctx.pw or is_tall_backdrop:
                continue
        elif r.height >= 0.45 * ctx.ph and r.width >= 0.12 * ctx.pw and _is_simple_box_drawing(dr):
            # Drop tall framed sidebar card backdrops (stroked + filled) enclosing dense sidebar prose/tables.
            if (
                _count_words_inside(r, ctx.word_rects) >= 25
                and _match_caption(r, ctx.fig_captions, ctx.text_blocks, cfg, allow_side=False) is None
            ):
                ctx.log(f"drawing:skip tall_sidebar_box {r}")
                continue
        if dr.get("fill") is None and r.height >= 0.40 * ctx.ph and r.width >= 0.12 * ctx.pw and raster_rects:
            inside_rasters = sorted(
                (rr for rr in raster_rects if _rect_center_inside(rr, r)),
                key=lambda x: x.y0,
            )
            if len(inside_rasters) >= 2:
                max_gap = max(
                    inside_rasters[k + 1].y0 - inside_rasters[k].y1
                    for k in range(len(inside_rasters) - 1)
                )
                if max_gap >= 40.0 and _count_words_inside(r, ctx.word_rects) >= 10:
                    continue

        filtered.append(dr)

    return filtered


def _is_dense_heatmap_not_table(tab: PageTableInfo, word_count: int) -> bool:
    """Return True when PyMuPDF misclassifies a dense multi-cell vector heatmap/grid plot as a table."""
    cells = tab.row_count * tab.col_count
    return cells >= 20 and word_count < int(0.25 * cells)


def _is_ui_text_card(
    rect: pymupdf.Rect,
    inside_drawings: list[dict],
    word_count: int,
    ctx: PageContext,
) -> bool:
    """Return True for uncaptioned UI pricing/KPI/callout cards containing only chrome + stacked text."""
    if word_count < 15 or len(inside_drawings) > 12:
        return False
    has_outer_box = False
    bullet_x0s: list[float] = []
    for dr in inside_drawings:
        r = dr["rect"]
        if _is_frame_for(r, rect) and _is_simple_box_drawing(dr):
            has_outer_box = True
            continue
        # Accent bar or divider rule
        if min(r.width, r.height) <= 4.0 and (r.width >= 0.35 * rect.width or r.height >= 0.35 * rect.height):
            continue
        # Tiny list bullet dot (validated for vertical column alignment below)
        if _is_tiny_bullet_dot(dr):
            bullet_x0s.append(r.x0)
            continue
        # Text-bearing pill badge or sub-card (never empty bar-chart bars)
        if _is_simple_box_drawing(dr) and _count_words_inside(r, ctx.word_rects) >= 1:
            continue
        return False

    if not has_outer_box:
        return False
    if len(bullet_x0s) > 8:
        return False
    if len(bullet_x0s) >= 2 and (max(bullet_x0s) - min(bullet_x0s)) > 12.0:
        return False

    # Count distinct vertical text lines inside the card
    y_centers = sorted(
        0.5 * (wr.y0 + wr.y1)
        for wr in ctx.word_rects
        if rect.contains(wr) or (rect & wr).get_area() >= 0.5 * max(1e-6, wr.get_area())
    )
    lines = 0
    last_y = -999.0
    for cy in y_centers:
        if cy - last_y >= 7.0:
            lines += 1
            last_y = cy
    return lines >= 4


def _is_financial_numeric_table(
    rect: pymupdf.Rect,
    inside_drawings: list[dict],
    txt: str,
    word_count: int,
    ctx: PageContext,
) -> bool:
    """Return True for uncaptioned shaded/ruled financial tables dominated by tabular numbers."""
    if word_count < 12 or not inside_drawings:
        return False
    # Every drawing must be either a thin rule or a wide row/column shading band (never varying-height bars).
    for dr in inside_drawings:
        r = dr["rect"]
        is_thin = min(r.width, r.height) <= 3.0
        is_wide_band = r.width >= 0.35 * rect.width and r.height <= 32.0 and dr.get("color") is None
        is_outer_frame = _is_frame_for(r, rect) and _is_simple_box_drawing(dr)
        if not (is_thin or is_wide_band or is_outer_frame):
            return False
    tokens = txt.split()
    num_tokens = sum(1 for tok in tokens if _NUMERIC_TOKEN_RE.match(tok))
    if num_tokens < max(5, int(0.45 * len(tokens))):
        return False
    y_centers = sorted(
        0.5 * (wr.y0 + wr.y1)
        for wr in ctx.word_rects
        if rect.contains(wr) or (rect & wr).get_area() >= 0.5 * max(1e-6, wr.get_area())
    )
    lines = 0
    last_y = -999.0
    for cy in y_centers:
        if cy - last_y >= 7.0:
            lines += 1
            last_y = cy
    return lines >= 3


def _is_in_caption_above_zone(rect: pymupdf.Rect, ctx: PageContext) -> bool:
    """Return True if `rect` sits in an unobstructed figure zone above a `fig_caption`."""
    for cap in ctx.fig_captions:
        cr = cap.rect
        if rect.y1 > cr.y0 + 4.0 or (cr.y0 - rect.y0) > min(0.75 * ctx.ph, 540.0):
            continue
        pad_x = 120.0 if cr.width < 0.50 * ctx.pw else 60.0
        if rect.x0 < cr.x0 - pad_x or rect.x1 > cr.x1 + pad_x:
            continue
        span = pymupdf.Rect(min(rect.x0, cr.x0), rect.y1, max(rect.x1, cr.x1), cr.y0)
        blocked = any(
            tb.rect != cr
            and _horiz_overlap(tb.rect, span) >= 25.0
            and rect.y1 - 2.0 <= tb.rect.y0
            and tb.rect.y1 <= cr.y0 - 2.0
            and (tb.kind in ("fig_caption", "tab_caption") or (tb.kind == "text" and tb.word_count >= 10))
            for tb in ctx.text_blocks
        )
        if not blocked:
            return True
    return False


def _evaluate_vector_cluster(
    ctx: PageContext,
    rect: pymupdf.Rect,
    filtered_drawings: list[dict],
    raster_rects: list[pymupdf.Rect],
    page_raw_clusters: int,
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> FilterDecision:
    """Phase 3 classifier: return `FilterDecision(keep, reason)` for one vector cluster."""
    if _is_page_background(rect, ctx.pw, ctx.ph, cfg):
        return FilterDecision(False, "reject:page_background")

    cap_idx, cap_side, _ = _match_caption_scored(rect, ctx.fig_captions, ctx.text_blocks, cfg=cfg)
    has_fig_cap = cap_idx is not None and cap_side != "side"
    dim_scale = 1.0 if has_fig_cap else max(1.0, min(ctx.pw, ctx.ph) / 792.0)
    min_dim = cfg.min_vector_dim * dim_scale

    has_raster = any(rect.intersects(rr) for rr in raster_rects)
    inside_drawings = [dr for dr in filtered_drawings if rect.contains(dr["rect"])]
    inside_rects = [dr["rect"] for dr in inside_drawings]
    has_curves_12 = _has_non_grid_detail(filtered_drawings, rect, min_count=12)
    has_curves_2 = has_curves_12 or _has_non_grid_detail(filtered_drawings, rect, min_count=2)
    has_curves_1 = has_curves_2 or _has_non_grid_detail(filtered_drawings, rect, min_count=1)

    is_captioned_strip = (
        has_fig_cap
        and min(rect.width, rect.height) >= 18.0
        and max(rect.width, rect.height) >= 95.0
        and rect.get_area() >= 1800.0
    )
    is_caption_zone_subdiagram = (
        min(rect.width, rect.height) >= 24.0
        and max(rect.width, rect.height) >= 38.0
        and rect.get_area() >= 1100.0
        and has_curves_2
        and len(inside_rects) >= 4
        and _is_in_caption_above_zone(rect, ctx)
    )
    if (rect.width < min_dim or rect.height < min_dim) and not (is_captioned_strip or is_caption_zone_subdiagram):
        return FilterDecision(False, "reject:too_small")
    if _is_edge_ornament(rect, ctx.page_rect, ctx.fig_captions):
        return FilterDecision(False, "reject:edge_ornament")

    # Reject framed table cards whose `Table X` title sits inside the box itself (e.g. rounded card tables).
    if not has_fig_cap and any(
        (rect & tc.rect).get_area() >= 0.65 * max(1.0, tc.rect.get_area())
        for tc in ctx.tab_captions
    ):
        return FilterDecision(False, "reject:inner_table_caption")

    txt = ctx.page.get_text("text", clip=rect).strip()
    tokens = txt.split()
    word_count = len(tokens)
    non_tick_word_count = (
        sum(1 for tok in tokens if not _TICK_TOKEN_RE.match(tok))
        if has_curves_12
        else word_count
    )
    if non_tick_word_count > cfg.max_vector_words:
        return FilterDecision(False, "reject:excessive_words")
    if non_tick_word_count > cfg.max_uncaptioned_vector_words and not has_fig_cap:
        return FilterDecision(False, "reject:uncaptioned_high_words")

    if word_count >= 6:
        has_tab_cap = _match_caption(rect, ctx.tab_captions, ctx.text_blocks, cfg) is not None
        if not (has_fig_cap and not has_tab_cap):
            if has_tab_cap and not has_fig_cap:
                return FilterDecision(False, "reject:table_caption")
            if not has_curves_12:
                # Check cached page-level tables first; fallback to clip find_tables only if cluster has grid lines.
                rect_area = max(1.0, rect.get_area())
                matched_tab = any(
                    (t.rect & rect).get_area() > 0.45 * rect_area
                    and t.row_count >= 2
                    and t.col_count >= 2
                    and not _is_dense_heatmap_not_table(t, word_count)
                    for t in ctx.get_page_tables()
                )
                if not matched_tab and len(inside_rects) >= 4:
                    clip_tabs = [
                        PageTableInfo(pymupdf.Rect(t.bbox), t.row_count, t.col_count)
                        for t in ctx.page.find_tables(clip=rect).tables
                    ]
                    matched_tab = any(
                        t.rect.get_area() > 0.45 * rect_area
                        and t.row_count >= 2
                        and t.col_count >= 2
                        and not _is_dense_heatmap_not_table(t, word_count)
                        for t in clip_tabs
                    )
                if matched_tab:
                    return FilterDecision(False, "reject:pymupdf_table", soft_reject=True)
        if word_count >= 20:
            prose_inside = [
                tb
                for tb in ctx.text_blocks
                if tb.kind == "text"
                and (tb.rect & rect).get_area() > 0.5 * tb.rect.get_area()
                and not _is_short_axis_label(tb, vertical_ok=True)
            ]
            long_blocks = [
                tb
                for tb in prose_inside
                if sum(1 for tok in tb.text.split() if not _TICK_TOKEN_RE.match(tok)) >= 12
            ]
            is_prose_callout = len(long_blocks) >= 2 or any(
                sum(1 for tok in tb.text.split() if not _TICK_TOKEN_RE.match(tok)) >= 40 for tb in long_blocks
            )
            if is_prose_callout and not (has_fig_cap and not has_tab_cap and has_curves_12):
                return FilterDecision(False, "reject:prose_box")

    if not has_raster:
        if not has_fig_cap and len(inside_rects) <= 2:
            return FilterDecision(False, "reject:trivial_shape")
        if not has_fig_cap and rect.height >= 0.50 * ctx.ph and rect.width <= 0.18 * ctx.pw:
            return FilterDecision(False, "reject:tall_narrow_column")
        if not has_fig_cap and _is_ui_text_card(rect, inside_drawings, word_count, ctx):
            return FilterDecision(False, "reject:ui_text_card")
        if not has_fig_cap and not has_curves_1:
            if _is_financial_numeric_table(rect, inside_drawings, txt, word_count, ctx):
                return FilterDecision(False, "reject:financial_numeric_table")
        if not has_fig_cap and inside_rects and all(min(x.width, x.height) <= 3.0 for x in inside_rects):
            h_rules = sum(1 for x in inside_rects if x.height <= 3.0 and x.width >= 0.4 * rect.width)
            v_rules = sum(1 for x in inside_rects if x.width <= 3.0 and x.height >= 0.4 * rect.height)
            if (
                (word_count >= 6 and h_rules >= 2 and v_rules >= 1)
                or (h_rules >= 3 and v_rules >= 2)
                or (
                    h_rules >= 2
                    and v_rules >= 2
                    and not has_curves_1
                    and all(dr.get("fill") is None for dr in inside_drawings)
                )
                or (word_count >= 10 and h_rules >= 2 and not has_curves_1)
            ):
                return FilterDecision(False, "reject:hairline_table_grid")
        if not has_fig_cap and inside_drawings:
            # Only strokeless filled tiny paths represent outlined text/formula glyphs; stroked diagrams survive.
            glyph_cap = 12.0 * max(1.0, min(ctx.pw, ctx.ph) / 792.0)
            tiny_filled_glyphs = sum(
                1
                for dr in inside_drawings
                if dr.get("color") is None
                and dr.get("fill") is not None
                and dr["rect"].width <= glyph_cap
                and dr["rect"].height <= glyph_cap
            )
            tiny_ratio = tiny_filled_glyphs / len(inside_drawings)
            long_parts = sum(
                1
                for x in inside_rects
                if max(x.width, x.height) >= 0.45 * min(rect.width, rect.height)
            )
            if long_parts < 2 and (
                (len(inside_drawings) >= 120 and tiny_ratio >= 0.72)
                or (len(inside_drawings) >= 35 and word_count == 0 and tiny_ratio >= 0.85)
            ):
                return FilterDecision(False, "reject:outlined_glyph_confetti")
        if (
            not has_fig_cap
            and page_raw_clusters >= 80
            and word_count == 0
            and len(inside_rects) <= 16
            and rect.get_area() < 0.03 * ctx.pw * ctx.ph
        ):
            return FilterDecision(False, "reject:dense_poster_fragment")

    return FilterDecision(True, "keep:vector_figure")


def _downsample_dense_drawings(drawings: list[dict], grid_pt: float = 6.0) -> list[dict]:
    """Coalesce ultra-dense micro-segments onto an O(n) spatial grid before O(n^2) clustering."""
    inv = 1.0 / max(1.0, grid_pt)
    small_cap = grid_pt
    buckets: dict[tuple[int, ...], dict] = {}
    for dr in drawings:
        r = dr["rect"]
        is_stroked = 1 if dr.get("color") is not None else 0
        if max(r.width, r.height) <= small_cap:
            key: tuple[int, ...] = (
                0,
                is_stroked,
                int((r.x0 + r.x1) * 0.5 * inv),
                int((r.y0 + r.y1) * 0.5 * inv),
            )
        else:
            key = (
                1,
                is_stroked,
                int(r.x0 * inv),
                int(r.y0 * inv),
                int(r.x1 * inv),
                int(r.y1 * inv),
            )
        existing = buckets.get(key)
        if existing is None:
            buckets[key] = dict(dr)
        else:
            existing["rect"] = existing["rect"] | r
    return list(buckets.values())


def detect_vector_regions(
    ctx: PageContext,
    raster_rects: list[pymupdf.Rect],
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> tuple[list[pymupdf.Rect], list[dict], int]:
    """Phase 3: Filter page drawings, cluster vector graphics, and classify valid figure clusters."""
    if not ctx.drawings:
        return [], [], 0
    if len(ctx.drawings) > cfg.max_page_drawings:
        ctx.log(f"vector:skip excessive_drawings count={len(ctx.drawings)} limit={cfg.max_page_drawings}")
        pno = getattr(ctx.page, "number", 0) + 1
        print(
            f"WARNING: Page {pno} has {len(ctx.drawings):,} vector drawings (> {cfg.max_page_drawings:,} limit); "
            f"skipped vector clustering on this page to prevent DoS (use RenderPages fallback if needed).",
            file=sys.stderr,
        )
        return [], [], 0

    filtered = _filter_drawings(ctx, raster_rects, cfg=cfg)
    if not filtered:
        return [], [], 0
    if len(filtered) > cfg.dense_drawing_downsample_threshold:
        orig_len = len(filtered)
        filtered = _downsample_dense_drawings(filtered, grid_pt=cfg.dense_drawing_grid_pt)
        ctx.log(f"vector:downsample_dense {orig_len}->{len(filtered)}")

    if len(filtered) > cfg.max_clustered_drawings:
        ctx.log(
            f"vector:skip excessive_clustered_drawings count={len(filtered)} limit={cfg.max_clustered_drawings}"
        )
        pno = getattr(ctx.page, "number", 0) + 1
        print(
            f"WARNING: Page {pno} still has {len(filtered):,} vector drawings after downsampling "
            f"(> {cfg.max_clustered_drawings:,} limit); skipped vector clustering on this page to prevent DoS "
            f"(use RenderPages fallback if needed).",
            file=sys.stderr,
        )
        return [], [], 0

    raw_clusters = ctx.page.cluster_drawings(
        drawings=filtered, x_tolerance=cfg.cluster_tol_x, y_tolerance=cfg.cluster_tol_y
    )
    raw_count = len(raw_clusters)
    kept: list[pymupdf.Rect] = []
    for c in raw_clusters:
        dec = _evaluate_vector_cluster(ctx, c, filtered, raster_rects, raw_count, cfg=cfg)
        ctx.log(f"vector:{dec.reason} {[round(v, 1) for v in c]}")
        if dec.keep:
            kept.append(c)
    return kept, filtered, raw_count


# ==============================================================================
# 5. Phase 4 — Caption Linking, Conflict Arbitration, Propagation & Recovery
# ==============================================================================


def _match_caption_scored(
    rect: pymupdf.Rect,
    fig_captions: list[TextBlock],
    text_blocks: list[TextBlock],
    excluded: set[int] | None = None,
    cfg: DetectorConfig = DEFAULT_CONFIG,
    allow_side: bool = True,
) -> tuple[int | None, str, float]:
    """Return `(best_caption_idx, placement_side, distance_score)` for `rect`."""
    best_idx: int | None = None
    best_side = ""
    best_dist = float("inf")

    for idx, cap in enumerate(fig_captions):
        if excluded and idx in excluded:
            continue
        cr = cap.rect
        h_ov = _horiz_overlap(rect, cr)
        min_ov = min(28.0, 0.30 * min(rect.width, cr.width))
        needs_axis_bridge = False
        side = ""

        # Allow modest bottom overlap (up to 26pt on tall figures) when EPS plot frame extends behind caption.
        max_bot_overlap = -26.0 if rect.height >= 120.0 else -14.0
        if h_ov >= min_ov:
            gap_below = cr.y0 - rect.y1
            gap_above = rect.y0 - cr.y1
            if max_bot_overlap <= gap_below <= cfg.caption_below_bridge_gap:
                dist = abs(gap_below)
                side = "below"
                needs_axis_bridge = gap_below > cfg.caption_below_max_gap
            elif -14.0 <= gap_above <= cfg.caption_above_max_gap:
                dist = abs(gap_above) + 18.0
                side = "above"
            else:
                dist = float("inf")
        elif (
            allow_side
            and _vert_overlap(rect, cr) >= 10.0
            and (
                abs(cr.y0 - rect.y0) <= cfg.caption_side_align_y
                or abs(cr.y1 - rect.y1) <= cfg.caption_side_align_y
            )
        ):
            gap_x = max(0.0, max(rect.x0, cr.x0) - min(rect.x1, cr.x1))
            if gap_x <= cfg.caption_side_max_gap_x:
                dist = gap_x + 24.0
                side = "side"
            else:
                dist = float("inf")
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
                if tb.word_count < 4 or _is_short_axis_label(tb):
                    continue
                if (
                    cr.y1 <= rect.y0
                    and 0.0 <= tb.rect.y0 - cr.y1 <= 10.0
                    and tb.word_count <= 14
                    and tb.rect.height <= 26.0
                    and _horiz_overlap(tb.rect, cr) >= 20.0
                ):
                    continue
                if _horiz_overlap(tb.rect, span) >= 20.0 and (
                    (rect.y1 <= tb.rect.y0 + 2 and tb.rect.y1 <= cr.y0 + 2)
                    or (cr.y1 <= tb.rect.y0 + 2 and tb.rect.y1 <= rect.y0 + 2)
                ):
                    blocked = True
                    break
            if needs_axis_bridge and (max_axis_y1 < 0.0 or (cr.y0 - max_axis_y1) > 45.0):
                blocked = True
            if not blocked:
                best_dist = dist
                best_idx = idx
                best_side = side

    return best_idx, best_side, best_dist


def _match_caption(
    rect: pymupdf.Rect,
    fig_captions: list[TextBlock],
    text_blocks: list[TextBlock],
    cfg: DetectorConfig = DEFAULT_CONFIG,
    allow_side: bool = True,
) -> int | None:
    """Find the most likely figure caption belonging to `rect`, if any."""
    idx, _, _ = _match_caption_scored(rect, fig_captions, text_blocks, cfg=cfg, allow_side=allow_side)
    return idx


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
            tr_area = max(1.0, tr.get_area())
            if (tr & a).get_area() >= 0.5 * tr_area or (tr & b).get_area() >= 0.5 * tr_area:
                continue
            if tr.y0 >= top.y1 - 4.0 and tr.y1 <= bot.y0 + 4.0:
                if max(0.0, min(x_hi, tr.x1) - max(x_lo, tr.x0)) >= 15.0:
                    return True
        for rr in rules:
            if top.y1 + 0.5 < rr.y0 and rr.y1 < bot.y0 - 0.5 and rr.height <= 4.0:
                if max(0.0, min(x_hi, rr.x1) - max(x_lo, rr.x0)) >= 0.4 * (x_hi - x_lo):
                    return True

    if a.x1 <= b.x0 or b.x1 <= a.x0:
        left, right = (a, b) if a.x1 <= b.x0 else (b, a)
        y_lo, y_hi = min(a.y0, b.y0), max(a.y1, b.y1)
        for tb in text_blocks:
            if allow_axis_labels and _is_short_axis_label(tb, vertical_ok=True):
                continue
            tr = tb.rect
            tr_area = max(1.0, tr.get_area())
            if (tr & a).get_area() >= 0.5 * tr_area or (tr & b).get_area() >= 0.5 * tr_area:
                continue
            if tr.x0 >= left.x1 - 4.0 and tr.x1 <= right.x0 + 4.0:
                if max(0.0, min(y_hi, tr.y1) - max(y_lo, tr.y0)) >= 12.0:
                    return True
        for rr in rules:
            if left.x1 + 0.5 < rr.x0 and rr.x1 < right.x0 - 0.5 and rr.width <= 4.0:
                if max(0.0, min(y_hi, rr.y1) - max(y_lo, rr.y0)) >= 0.4 * (y_hi - y_lo):
                    return True

    return False


def _row_aligned_text_indices(
    rect: pymupdf.Rect, text_blocks: list[TextBlock], max_gap_x: float = 80.0
) -> list[int]:
    """Return sorted indices of regular horizontal text blocks sharing a table row with `rect`."""
    indices: list[int] = []
    for idx, tb in enumerate(text_blocks):
        if tb.kind != "text":
            continue
        tr = tb.rect
        # Never treat rotated Y-axis titles as horizontal table-row cells.
        if tr.width <= 28.0 and tr.height >= 1.8 * tr.width:
            continue
        if _horiz_overlap(rect, tr) > 5.0:
            continue
        gap_x = max(0.0, max(rect.x0, tr.x0) - min(rect.x1, tr.x1))
        if gap_x > max_gap_x:
            continue
        # Never treat adjacent Y-axis tick values, short particle/math symbols, or subpanel markers as table rows.
        cleaned = _clean_text(tb.text)
        tokens = cleaned.split()
        if not tokens or len(cleaned) <= 4 or all(len(tok) <= 2 for tok in tokens):
            continue
        if len(tokens) <= 4 and all(
            _TICK_TOKEN_RE.match(tok) or _SUBPANEL_LABEL_RE.match(tok) for tok in tokens
        ):
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


def _is_table_row_pair(a: pymupdf.Rect, b: pymupdf.Rect, text_blocks: list[TextBlock]) -> bool:
    """Return True if vertically stacked `a` and `b` align with separate adjacent table-row texts."""
    if min(a.width, b.width) >= 165.0:
        return False
    if not (a.y1 <= b.y0 + 2.0 or b.y1 <= a.y0 + 2.0):
        return False
    if _horiz_overlap(a, b) < 0.5 * min(a.width, b.width):
        return False
    ma = _row_aligned_text_indices(a, text_blocks, max_gap_x=80.0)
    mb = _row_aligned_text_indices(b, text_blocks, max_gap_x=80.0)
    return bool(ma and mb and ma[0] != mb[0])


def _resolve_caption_conflicts(
    candidates: list[CandidateBox], ctx: PageContext, cfg: DetectorConfig = DEFAULT_CONFIG
) -> None:
    """Arbitrate when one caption is claimed by incompatible sides (vertical vs side, or above vs below)."""
    by_cap: dict[int, list[int]] = {}
    for ci, cand in enumerate(candidates):
        if cand.caption_idx is not None:
            by_cap.setdefault(cand.caption_idx, []).append(ci)

    losing_side: dict[int, set[int]] = {}
    for cap_idx, idxs in by_cap.items():
        if len(idxs) < 2:
            continue

        # Rule A: Direct vertical caption ownership (below/above) always beats weak side-caption matches.
        vert_claimants = [i for i in idxs if candidates[i].caption_side in ("below", "above")]
        side_claimants = [i for i in idxs if candidates[i].caption_side == "side"]
        if vert_claimants and side_claimants:
            for i in side_claimants:
                losing_side.setdefault(i, set()).add(cap_idx)
            idxs = vert_claimants
            if len(idxs) < 2:
                continue

        # Rule B: Prevent a caption sandwiched between two stacked figures from claiming both above and below.
        cap_cy = 0.5 * (ctx.fig_captions[cap_idx].rect.y0 + ctx.fig_captions[cap_idx].rect.y1)
        above = [i for i in idxs if 0.5 * (candidates[i].rect.y0 + candidates[i].rect.y1) < cap_cy]
        below = [i for i in idxs if 0.5 * (candidates[i].rect.y0 + candidates[i].rect.y1) >= cap_cy]
        if not (above and below):
            continue
        best_above_i = min(above, key=lambda i: candidates[i].caption_score)
        best_below_i = min(below, key=lambda i: candidates[i].caption_score)
        best_above = candidates[best_above_i].caption_score
        best_below = candidates[best_below_i].caption_score
        losers = below if best_above <= best_below else above

        if best_above <= best_below:
            alt_above, _, _ = _match_caption_scored(
                candidates[best_above_i].rect,
                ctx.fig_captions,
                ctx.text_blocks,
                excluded=set(by_cap.keys()),
                cfg=cfg,
            )
            if alt_above is not None and (best_below - 18.0) <= (best_above + 6.0):
                losers = above

        for i in losers:
            losing_side.setdefault(i, set()).add(cap_idx)

    for ci, excluded in losing_side.items():
        new_cap, new_side, new_score = _match_caption_scored(
            candidates[ci].rect, ctx.fig_captions, ctx.text_blocks, excluded=excluded, cfg=cfg
        )
        candidates[ci].caption_idx = new_cap
        candidates[ci].caption_side = new_side
        candidates[ci].caption_score = new_score


def _same_side_of_caption(a: pymupdf.Rect, b: pymupdf.Rect, cap: pymupdf.Rect) -> bool:
    cap_cy = 0.5 * (cap.y0 + cap.y1)
    a_above = 0.5 * (a.y0 + a.y1) < cap_cy
    b_above = 0.5 * (b.y0 + b.y1) < cap_cy
    return a_above == b_above


def _propagate_captions(
    candidates: list[CandidateBox], ctx: PageContext, cfg: DetectorConfig = DEFAULT_CONFIG
) -> None:
    """Propagate caption ownership across tightly aligned multi-panel sibling subplots."""
    changed = True
    while changed:
        changed = False
        for i, a in enumerate(candidates):
            if a.caption_idx is not None:
                continue
            for j, b in enumerate(candidates):
                if i == j or b.caption_idx is None or b.caption_side == "side":
                    continue
                cap = ctx.fig_captions[b.caption_idx].rect
                if not _same_side_of_caption(a.rect, b.rect, cap):
                    continue

                gap = _rect_gap(a.rect, b.rect)
                shares_col = _horiz_overlap(a.rect, b.rect) >= 0.35 * min(a.rect.width, b.rect.width)
                shares_row = _vert_overlap(a.rect, b.rect) >= 0.45 * min(a.rect.height, b.rect.height)
                exact_col_align = (
                    abs(a.rect.x0 - b.rect.x0) <= 12.0
                    and abs(a.rect.x1 - b.rect.x1) <= 12.0
                    and _horiz_overlap(a.rect, b.rect) >= 0.85 * max(a.rect.width, b.rect.width)
                )

                if shares_col:
                    col_limit = cfg.sibling_col_max_gap * 1.65 if exact_col_align else cfg.sibling_col_max_gap
                    if gap > col_limit:
                        continue
                elif shares_row:
                    if gap > cfg.sibling_row_max_gap:
                        continue
                    # Do not propagate horizontally into an unrelated tall sidebar.
                    if max(a.rect.height, b.rect.height) > 2.2 * max(1.0, min(a.rect.height, b.rect.height)):
                        continue
                else:
                    continue

                # Avoid crossing from a narrow single-column caption into an unrelated other column.
                if cap.width < 0.45 * ctx.pw and _horiz_overlap(a.rect, cap) == 0.0 and not shares_col and gap > 16.0:
                    continue
                if _has_obstacle_between(a.rect, b.rect, ctx.text_blocks, ctx.separator_rules, allow_axis_labels=True):
                    continue
                if _is_table_row_pair(a.rect, b.rect, ctx.text_blocks):
                    continue

                a.caption_idx = b.caption_idx
                a.caption_side = b.caption_side
                a.caption_score = b.caption_score + gap
                changed = True
                break


def _fallback_search_band(
    cr: pymupdf.Rect,
    ctx: PageContext,
    direction: int,
    existing_rects: list[pymupdf.Rect],
) -> pymupdf.Rect:
    """Compute the obstacle-free rectangular search band below (+1) or above (-1) an orphaned caption."""
    pad_x = 120.0 if cr.width < 0.50 * ctx.pw else 50.0
    bx0 = max(ctx.page_rect.x0, cr.x0 - pad_x)
    bx1 = min(ctx.page_rect.x1, cr.x1 + pad_x)
    max_reach = min(0.55 * ctx.ph, 380.0)

    if direction > 0:
        band_y0 = cr.y1 - 4.0
        band_y1 = min(ctx.page_rect.y1 - 24.0, cr.y1 + max_reach)
        band_span = pymupdf.Rect(bx0, band_y0, bx1, band_y1)
        for tb in ctx.text_blocks:
            if tb.rect != cr and _horiz_overlap(tb.rect, band_span) >= 25.0 and tb.rect.y0 >= cr.y1 + 2.0:
                if tb.kind in ("fig_caption", "tab_caption") or (tb.kind == "text" and tb.word_count >= 10):
                    band_y1 = min(band_y1, tb.rect.y0 + 2.0)
        for rr in ctx.separator_rules:
            if rr.height <= 4.0 and rr.width >= 0.60 * ctx.pw and rr.y0 >= cr.y1 + 6.0:
                band_y1 = min(band_y1, rr.y0 + 2.0)
        for er in existing_rects:
            if _horiz_overlap(er, cr) >= 20.0 and er.y0 >= cr.y1 - 4.0:
                band_y1 = min(band_y1, er.y0 - 2.0)
    else:
        band_y1 = cr.y0 + 4.0
        band_y0 = max(ctx.page_rect.y0 + 24.0, cr.y0 - max_reach)
        band_span = pymupdf.Rect(bx0, band_y0, bx1, band_y1)
        for tb in ctx.text_blocks:
            if tb.rect != cr and _horiz_overlap(tb.rect, band_span) >= 25.0 and tb.rect.y1 <= cr.y0 - 2.0:
                if tb.kind in ("fig_caption", "tab_caption") or (tb.kind == "text" and tb.word_count >= 10):
                    band_y0 = max(band_y0, tb.rect.y1 - 2.0)
        for rr in ctx.separator_rules:
            if rr.height <= 4.0 and rr.width >= 0.60 * ctx.pw and rr.y1 <= cr.y0 - 6.0:
                band_y0 = max(band_y0, rr.y1 - 2.0)
        for er in existing_rects:
            if _horiz_overlap(er, cr) >= 20.0 and er.y1 <= cr.y0 + 4.0:
                band_y0 = max(band_y0, er.y1 + 2.0)

    return pymupdf.Rect(bx0, band_y0, bx1, band_y1)


def _recover_orphan_caption_vectors(
    ctx: PageContext,
    filtered_drawings: list[dict],
    raster_rects: list[pymupdf.Rect],
    candidates: list[CandidateBox],
    raw_cluster_count: int,
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> list[pymupdf.Rect]:
    """Recover disconnected vector charts (e.g., axis-less bar groups or sparse schematics) near orphaned captions."""
    if not filtered_drawings or not ctx.fig_captions:
        return []
    assigned = {c.caption_idx for c in candidates if c.caption_idx is not None}
    existing_rects = [c.rect for c in candidates if c.caption_idx is not None]
    extra_vecs: list[pymupdf.Rect] = []

    for cap_idx, cap in enumerate(ctx.fig_captions):
        if cap_idx in assigned:
            continue
        for direction in (1, -1):
            band = _fallback_search_band(cap.rect, ctx, direction, existing_rects)
            if band.height < cfg.min_vector_dim or band.width < cfg.min_vector_dim:
                continue
            band_drawings = [
                dr
                for dr in filtered_drawings
                if _rect_center_inside(dr["rect"], band)
                and not any(er.contains(dr["rect"]) for er in existing_rects)
            ]
            if len(band_drawings) < 4:
                continue

            found_here = False
            tol_passes = ((48, 24), (112, 68)) if direction < 0 else ((48, 24),)
            for x_tol, y_tol in tol_passes:
                for c in ctx.page.cluster_drawings(drawings=band_drawings, x_tolerance=x_tol, y_tolerance=y_tol):
                    if any(c.intersects(er) for er in existing_rects):
                        continue
                    if sum(1 for dr in filtered_drawings if c.contains(dr["rect"])) < 4:
                        continue
                    if _match_caption(c, ctx.fig_captions, ctx.text_blocks, cfg) != cap_idx:
                        continue
                    dec = _evaluate_vector_cluster(ctx, c, filtered_drawings, raster_rects, raw_cluster_count, cfg=cfg)
                    if dec.keep:
                        extra_vecs.append(c)
                        found_here = True
                if found_here:
                    break
            if found_here:
                break

    return extra_vecs


def _is_unlabeled_two_col_plot_grid(base_rects: list[pymupdf.Rect], ctx: PageContext) -> bool:
    """Return True for a multi-row 2-column grid of large standalone plots lacking `(a)/(b)` subpanel labels."""
    large_plots = [r for r in base_rects if r.width >= 155.0 and r.height >= 75.0]
    if len(large_plots) < 4:
        return False
    mid_x = 0.50 * ctx.pw
    left_col = [r for r in large_plots if r.x1 <= mid_x]
    right_col = [r for r in large_plots if r.x0 >= mid_x]
    if len(left_col) < 2 or len(right_col) < 2:
        return False
    col_gap = min(r.x0 for r in right_col) - max(r.x1 for r in left_col)
    if col_gap < 45.0:
        return False
    grid_box = pymupdf.Rect(large_plots[0])
    for r in large_plots[1:]:
        grid_box = grid_box | r
    grid_box = pymupdf.Rect(grid_box.x0 - 30.0, grid_box.y0 - 24.0, grid_box.x1 + 30.0, grid_box.y1 + 24.0)
    has_subpanel_labels = any(
        tb.kind == "text"
        and grid_box.intersects(tb.rect)
        and _SUBPANEL_LABEL_RE.match(_clean_text(tb.text))
        for tb in ctx.text_blocks
    )
    return not has_subpanel_labels


def link_captions(
    ctx: PageContext,
    base_rects: list[pymupdf.Rect],
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> list[CandidateBox]:
    """Phase 4: Assign, arbitrate, and propagate figure captions across candidate regions."""
    if _is_unlabeled_two_col_plot_grid(base_rects, ctx):
        return [CandidateBox(r, None, "", float("inf")) for r in base_rects]
    candidates: list[CandidateBox] = []
    for r in base_rects:
        cap_idx, cap_side, dist = _match_caption_scored(r, ctx.fig_captions, ctx.text_blocks, cfg=cfg)
        candidates.append(CandidateBox(r, cap_idx, cap_side, dist))

    _resolve_caption_conflicts(candidates, ctx, cfg=cfg)
    _propagate_captions(candidates, ctx, cfg=cfg)
    return candidates


# ==============================================================================
# 6. Phase 5 — Safe Multi-Panel Merging (with Anti-Swallow Invariants)
# ==============================================================================


def _violates_merge_invariants(
    a: CandidateBox,
    b: CandidateBox,
    all_candidates: list[CandidateBox],
    ctx: PageContext,
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> bool:
    """Block merges that balloon to full-page background, swallow another captioned figure, or swallow prose."""
    union = a.rect | b.rect
    if (
        _is_page_background(union, ctx.pw, ctx.ph, cfg)
        and not _is_page_background(a.rect, ctx.pw, ctx.ph, cfg)
        and not _is_page_background(b.rect, ctx.pw, ctx.ph, cfg)
    ):
        return True

    # Never swallow an unrelated candidate that belongs to a different caption.
    for other in all_candidates:
        if other is a or other is b:
            continue
        if other.caption_idx is not None and other.caption_idx not in (a.caption_idx, b.caption_idx):
            other_area = max(1.0, other.rect.get_area())
            if (union & other.rect).get_area() >= 0.50 * other_area:
                return True

    # Never swallow >=2 newly enclosed long prose blocks that weren't already inside a or b.
    newly_swallowed_prose = 0
    for tb in ctx.text_blocks:
        if tb.kind != "text" or tb.word_count < 12:
            continue
        tb_area = max(1.0, tb.rect.get_area())
        if (union & tb.rect).get_area() >= 0.65 * tb_area:
            in_a = (a.rect & tb.rect).get_area() >= 0.50 * tb_area
            in_b = (b.rect & tb.rect).get_area() >= 0.50 * tb_area
            if not in_a and not in_b:
                newly_swallowed_prose += 1
                if newly_swallowed_prose >= 2:
                    return True

    return False


def _should_merge_candidates(
    a: CandidateBox,
    b: CandidateBox,
    all_candidates: list[CandidateBox],
    ctx: PageContext,
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> bool:
    """Decide whether two figure candidates belong to the same logical figure."""
    if a.caption_idx is not None and b.caption_idx is not None and a.caption_idx != b.caption_idx:
        return False
    same_cap = a.caption_idx is not None and a.caption_idx == b.caption_idx
    if _has_obstacle_between(a.rect, b.rect, ctx.text_blocks, ctx.separator_rules, allow_axis_labels=same_cap):
        return False
    if _is_table_row_pair(a.rect, b.rect, ctx.text_blocks):
        return False

    gap = _rect_gap(a.rect, b.rect)
    if same_cap:
        shares_row = _vert_overlap(a.rect, b.rect) >= 0.40 * min(a.rect.height, b.rect.height)
        exact_col_align = (
            abs(a.rect.x0 - b.rect.x0) <= 12.0
            and abs(a.rect.x1 - b.rect.x1) <= 12.0
            and _horiz_overlap(a.rect, b.rect) >= 0.85 * max(a.rect.width, b.rect.width)
        )
        limit = (
            cfg.same_caption_row_merge_gap
            if shares_row
            else (cfg.same_caption_merge_gap * 1.65 if exact_col_align else cfg.same_caption_merge_gap)
        )
        if gap > limit:
            return False
    elif gap > cfg.touching_merge_gap:
        return False

    if _violates_merge_invariants(a, b, all_candidates, ctx, cfg=cfg):
        return False
    return True


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


def merge_candidates(
    ctx: PageContext,
    candidates: list[CandidateBox],
    cfg: DetectorConfig = DEFAULT_CONFIG,
) -> list[CandidateBox]:
    """Phase 5: Iteratively merge multi-panel candidates respecting anti-swallow invariants."""
    changed = True
    while changed:
        changed = False
        merged: list[CandidateBox] = []
        for c in candidates:
            did_merge = False
            for m in merged:
                if _should_merge_candidates(m, c, candidates, ctx, cfg=cfg):
                    m.rect = m.rect | c.rect
                    if m.caption_idx is None:
                        m.caption_idx = c.caption_idx
                        m.caption_side = c.caption_side
                        m.caption_score = c.caption_score
                    did_merge = True
                    changed = True
                    break
            if not did_merge:
                merged.append(c)
        candidates = merged
    return _sort_reading_order(candidates)


# ==============================================================================
# 7. Phase 6 — Finalization, Manifest Generation & Public API
# ==============================================================================


def _annotate_candidate_origins(
    candidates: list[CandidateBox],
    raster_rects: list[pymupdf.Rect],
    filtered_rects: list[pymupdf.Rect],
) -> None:
    """Populate `source` ('raster'|'vector'|'hybrid') and `drawings` count on each candidate."""
    for cand in candidates:
        bb = cand.rect
        overlapping_rasters = [rr for rr in raster_rects if bb.intersects(rr)]
        intersecting_vecs = [r for r in filtered_rects if bb.intersects(r) and _rect_center_inside(r, bb)]
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


def _extract_context_snippet(rect: pymupdf.Rect, text_blocks: list[TextBlock]) -> str | None:
    """Find concise nearby row or paragraph text when a figure has no explicit caption."""
    row_indices = _row_aligned_text_indices(rect, text_blocks, max_gap_x=120.0)
    if row_indices:
        joined = " | ".join(_clean_text(text_blocks[i].text) for i in row_indices)
        return joined[:220]

    best_tb: TextBlock | None = None
    best_gap = float("inf")
    for tb in text_blocks:
        gap = _rect_gap(rect, tb.rect)
        if gap < best_gap and gap <= 65.0 and tb.word_count >= 2:
            best_gap = gap
            best_tb = tb
    if best_tb is not None:
        return _clean_text(best_tb.text)[:220]
    return None


def _detect_table_placement(
    candidates: list[CandidateBox],
    idx: int,
    ctx: PageContext,
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

    row_indices = _row_aligned_text_indices(bb, ctx.text_blocks, max_gap_x=120.0)
    if len(row_indices) >= 2:
        return "table_cell"
    if len(row_indices) == 1 and ctx.text_blocks[row_indices[0]].word_count <= 25:
        if any(i != idx and _is_table_row_pair(bb, other.rect, ctx.text_blocks) for i, other in enumerate(candidates)):
            return "table_cell"
        row_span = bb | ctx.text_blocks[row_indices[0]].rect
        for tb in ctx.tab_captions:
            if 0.0 <= bb.y0 - tb.rect.y1 <= 55.0 and _horiz_overlap(tb.rect, row_span) >= 40.0:
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


def _expand_plot_axis_labels(candidates: list[CandidateBox], ctx: PageContext) -> None:
    """Expand vector/hybrid (or captioned) plot boxes to include tightly attached axis ticks & titles.

    Prevents vector chart crops from slicing off Y-axis numbers, rotated Y-axis titles,
    X-axis labels, and subpanel markers that live just outside the vector axis frame.
    """
    all_captions = ctx.fig_captions + ctx.tab_captions
    prose_blocks = [
        tb
        for tb in ctx.text_blocks
        if tb.kind != "text" or (tb.word_count >= 6 and not _is_short_axis_label(tb, vertical_ok=True))
    ]
    axis_blocks = [
        tb
        for tb in ctx.text_blocks
        if tb.kind == "text"
        and _is_short_axis_label(tb, vertical_ok=True)
        and tb.rect.y1 >= ctx.page_rect.y0 + 36.0
        and tb.rect.y0 <= ctx.page_rect.y1 - 36.0
    ]
    if not axis_blocks:
        return

    for idx, cand in enumerate(candidates):
        if cand.source == "raster" and cand.caption_idx is None:
            continue
        orig = pymupdf.Rect(cand.rect)
        cur = pymupdf.Rect(cand.rect)
        other_rects = [c.rect for j, c in enumerate(candidates) if j != idx]

        changed = True
        while changed:
            changed = False
            for tb in axis_blocks:
                tr = tb.rect
                if cur.contains(tr):
                    continue
                # Hard expansion caps relative to the original graphic box so absorption cannot run away.
                if (
                    orig.x0 - tr.x0 > 52.0
                    or tr.x1 - orig.x1 > 40.0
                    or tr.y1 - orig.y1 > 36.0
                    or orig.y0 - tr.y0 > 24.0
                ):
                    continue

                is_rotated = tr.width <= 28.0 and tr.height >= 1.8 * tr.width
                cleaned = _clean_text(tb.text)
                is_subpanel = bool(_SUBPANEL_LABEL_RE.match(cleaned))
                attachable = False

                # Left side (Y-axis ticks, rotated Y-axis title, or subpanel marker)
                if (
                    tr.x1 <= cur.x0 + 6.0
                    and (cur.x0 - tr.x1) <= 16.0
                    and tr.y0 >= cur.y0 - 10.0
                    and tr.y1 <= cur.y1 + 10.0
                ):
                    if cand.source != "raster" or is_rotated or is_subpanel or tr.width <= 32.0:
                        attachable = True
                # Right side (only rotated secondary Y-axis title or narrow right-axis tick/unit)
                elif (
                    tr.x0 >= cur.x1 - 6.0
                    and (tr.x0 - cur.x1) <= 16.0
                    and tr.y0 >= cur.y0 - 10.0
                    and tr.y1 <= cur.y1 + 10.0
                    and (is_rotated or tr.width <= 42.0)
                ):
                    if cand.source != "raster" or is_rotated or tr.width <= 28.0:
                        attachable = True
                # Bottom side (X-axis ticks or X-axis title)
                elif (
                    tr.y0 >= cur.y1 - 6.0
                    and (tr.y0 - cur.y1) <= 16.0
                    and tr.x0 >= cur.x0 - 16.0
                    and tr.x1 <= cur.x1 + 16.0
                ):
                    if cand.source != "raster" or is_subpanel or tr.height <= 16.0:
                        attachable = True
                # Top side (compact panel title, top ticks, or subpanel marker)
                elif (
                    tr.y1 <= cur.y0 + 6.0
                    and (cur.y0 - tr.y1) <= 14.0
                    and tr.x0 >= cur.x0 - 16.0
                    and tr.x1 <= cur.x1 + 16.0
                    and (is_subpanel or (tb.word_count <= 4 and tr.height <= 18.0))
                ):
                    if cand.source != "raster" or is_subpanel:
                        attachable = True

                if not attachable:
                    continue

                expanded = cur | tr
                if any(_rect_gap(expanded, cap.rect) < 3.0 for cap in all_captions):
                    continue
                if any(expanded.intersects(orect) for orect in other_rects):
                    continue
                if any(
                    not orig.intersects(pb.rect) and (expanded & pb.rect).get_area() >= 0.25 * max(1.0, pb.rect.get_area())
                    for pb in prose_blocks
                ):
                    continue

                cur = expanded
                changed = True

        cand.rect = cur & ctx.page_rect


def _run_page_pipeline(
    page: pymupdf.Page, cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[PageContext, list[CandidateBox], bool]:
    """Execute Phases 1–5 on `page` and return `(PageContext, candidates, is_scanned)`."""
    _ensure_pymupdf()
    # Phase 1
    ctx = analyze_page(page, cfg=cfg)
    # Phase 2
    raster_rects, has_full_page_img = detect_raster_regions(ctx, cfg=cfg)
    # Phase 3
    vector_rects, filtered_drawings, raw_cluster_count = detect_vector_regions(ctx, raster_rects, cfg=cfg)
    filtered_rects = [dr["rect"] for dr in filtered_drawings]

    # Phase 4 & 5
    base_rects = _merge_touching(
        raster_rects + vector_rects,
        pad=cfg.touch_pad,
        prevent_page_bg=(ctx.pw, ctx.ph, cfg),
    )
    candidates = merge_candidates(ctx, link_captions(ctx, base_rects, cfg=cfg), cfg=cfg)

    # Orphan-caption vector recovery (e.g., axis-less bar groups beneath an unclaimed caption)
    extra_vecs = _recover_orphan_caption_vectors(
        ctx, filtered_drawings, raster_rects, candidates, raw_cluster_count, cfg=cfg
    )
    if extra_vecs:
        base_rects = _merge_touching(
            raster_rects + vector_rects + extra_vecs,
            pad=cfg.touch_pad,
            prevent_page_bg=(ctx.pw, ctx.ph, cfg),
        )
        candidates = merge_candidates(ctx, link_captions(ctx, base_rects, cfg=cfg), cfg=cfg)

    _annotate_candidate_origins(candidates, raster_rects, filtered_rects)
    _expand_plot_axis_labels(candidates, ctx)
    if len(candidates) >= 2:
        candidates = merge_candidates(ctx, candidates, cfg=cfg)
        _annotate_candidate_origins(candidates, raster_rects, filtered_rects)
        _expand_plot_axis_labels(candidates, ctx)
    min_uncap_vec_dim = cfg.min_vector_dim * max(1.0, min(ctx.pw, ctx.ph) / 792.0)
    candidates = [
        c
        for c in candidates
        if c.caption_idx is not None
        or c.source != "vector"
        or (c.rect.width >= min_uncap_vec_dim and c.rect.height >= min_uncap_vec_dim)
    ]
    is_scanned = has_full_page_img and not candidates
    return ctx, candidates, is_scanned


def detect_page_figures_debug(
    page: pymupdf.Page, cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[list[CandidateBox], bool, list[str]]:
    """Run full pipeline and also return human-readable per-region decision trace for diagnostics."""
    ctx, candidates, is_scanned = _run_page_pipeline(page, cfg=cfg)
    return candidates, is_scanned, ctx.trace


def collect_page_figures(page: pymupdf.Page) -> tuple[list[pymupdf.Rect], bool]:
    """Collect logical figure bounding boxes on `page` and flag scanned pages."""
    _, candidates, is_scanned = _run_page_pipeline(page)
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
    """Phase 6: Render every detected bitmap or vector figure region in `pdf_path` to PNG."""
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
            ctx, candidates, is_scanned = _run_page_pipeline(page)
            if is_scanned:
                scanned_pages.append(pno)
            table_bboxes: list[pymupdf.Rect] = []
            if write_meta and any(c.caption_idx is None for c in candidates):
                table_bboxes = [t.rect for t in ctx.get_page_tables()]

            for idx0, cand in enumerate(candidates):
                idx = idx0 + 1
                bb = cand.rect
                clip = pymupdf.Rect(bb.x0 - 4.0, bb.y0 - 4.0, bb.x1 + 4.0, bb.y1 + 4.0) & ctx.page_rect
                if clip.is_empty:
                    continue
                out_name = f"fig_p{pno}_{idx}.png"
                out_path = safe_out_dir / out_name
                desired_zoom = dpi / 72.0
                safe_zoom, was_clamped = compute_safe_render_zoom(clip.width, clip.height, desired_zoom)
                if was_clamped:
                    print(
                        f"WARNING: Clamped {out_name} render DPI ({dpi} -> {int(round(safe_zoom * 72.0))}) "
                        f"to stay within {MAX_RENDER_DIM}px / {MAX_RENDER_PIXELS:,}px safety limit.",
                        file=sys.stderr,
                    )
                pix = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(safe_zoom, safe_zoom))
                pix.save(out_path)
                saved.append(out_path)

                if write_meta:
                    cap_text = (
                        _clean_text(ctx.fig_captions[cand.caption_idx].text)
                        if cand.caption_idx is not None
                        else None
                    )
                    ctx_text = (
                        None
                        if cap_text is not None
                        else _extract_context_snippet(bb, ctx.text_blocks)
                    )
                    placement = _detect_table_placement(candidates, idx0, ctx, table_bboxes)
                    manifest_items.append(
                        {
                            "file": out_name,
                            "page": pno,
                            "source": cand.source,
                            "drawings": cand.drawings,
                            "placement": placement,
                            "box": _normalize_box(bb, ctx.page_rect),
                            "width_px": pix.width,
                            "height_px": pix.height,
                            "caption": cap_text,
                            "context": ctx_text,
                        }
                    )

    print(f"Extracted {len(saved)} figures -> {safe_out_dir}")
    if scanned_pages:
        print(f"[Note] Detected {len(scanned_pages)} scanned/full-page image page(s): {scanned_pages}")
    if write_meta:
        meta_path = safe_out_dir / "manifest.json"
        safe_pdf_name = re.sub(r"[\x00-\x1F\x7F]+", " ", pdf_path.name).strip()
        meta = {
            "pdf": safe_pdf_name,
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
