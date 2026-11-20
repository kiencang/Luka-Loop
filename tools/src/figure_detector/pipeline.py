"""Phases 1–5 orchestration per page, plus origin annotation and axis-label expansion."""

from __future__ import annotations

from .captions import (
    _recover_orphan_caption_vectors,
    link_captions,
)
from .geometry import (
    _is_frame_for,
    _merge_touching,
    _rect_center_inside,
    _rect_gap,
)
from .merge import (
    merge_candidates,
)
from .model import (
    _SUBPANEL_LABEL_RE,
    DEFAULT_CONFIG,
    CandidateBox,
    DetectorConfig,
    PageContext,
    _ensure_pymupdf,
    pymupdf,
)
from .raster import (
    detect_raster_regions,
)
from .text import (
    _clean_text,
    _is_short_axis_label,
    analyze_page,
)
from .vector import (
    detect_vector_regions,
)


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
