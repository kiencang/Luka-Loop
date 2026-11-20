"""Phase 2 — foreground raster regions; scanned-page detection; banner/watermark rejection."""

from __future__ import annotations

from .caption_match import (
    _match_caption,
)
from .geometry import (
    _count_words_inside,
    _is_edge_ornament,
    _is_full_bleed_edge_strip,
    _is_hero_header_banner,
    _is_page_background,
    _is_vertical_bleed_strip,
    _merge_touching,
    _vert_overlap,
)
from .model import (
    DEFAULT_CONFIG,
    DetectorConfig,
    PageContext,
    pymupdf,
)


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
