"""Phases 1–5 orchestration per page, plus origin annotation and axis-label expansion."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

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
    RENDER_PAD,
    _SECTION_HEADING_RE,
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
    rescue_small_vector_pieces,
)

ColumnEdge = tuple[str, float, float, float]  # (side 'left'|'right', x, y0, y1) of an aligned text-column edge
_COLUMN_EDGE_TOL = 1.5


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


def _expand_plot_axis_labels(
    candidates: list[CandidateBox], ctx: PageContext, col_edges: Sequence[ColumnEdge] = ()
) -> None:
    """Expand vector/hybrid (or captioned) plot boxes to include tightly attached axis ticks & titles.

    Prevents vector chart crops from slicing off Y-axis numbers, rotated Y-axis titles,
    X-axis labels, and subpanel markers that live just outside the vector axis frame. A block past an aligned
    text-column edge (`_column_edges`) on the far side from the box is never taken.
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
        and not ctx.is_running_head(tb.rect)
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
                if col_edges and _crosses_column_edge(orig, tr, col_edges):
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


_EQUATION_NUMBER_RE = re.compile(r"^\(\d+(?:\.\d+)*[a-z]?\)$")


def _label_lines(ctx: PageContext) -> list[tuple[pymupdf.Rect, bool]]:
    """Label-like text lines outside captions, prose and page margins, as (rect, set larger than body text)."""
    lines: dict[tuple[int, int], pymupdf.Rect] = {}
    words: dict[tuple[int, int], list[str]] = {}
    for w in ctx.words:
        key = (w[5], w[6])
        r = pymupdf.Rect(w[:4])
        lines[key] = lines[key] | r if key in lines else r
        words.setdefault(key, []).append(w[4])
    top_band = ctx.page_rect.y0 + 0.10 * ctx.ph  # running headers sit in the top ~10%
    # When the document's running heads are known, the band ends at the lowest head in the top half of the page,
    # so a figure label set high on the page is not dropped as a header. Pages without heads keep the 10% band.
    top_heads = [h.y1 for h in ctx.running_heads if h.y0 < ctx.page_rect.y0 + 0.5 * ctx.ph]
    if top_heads:
        top_band = min(top_band, max(top_heads))
    bottom_band = ctx.page_rect.y1 - 0.06 * ctx.ph
    # Body font size proxy: median height of horizontal words. Headings and titles are set larger than body text,
    # while axis labels, ticks and legends are the same size or smaller.
    heights = sorted(wr.height for wr in ctx.word_rects if wr.width >= wr.height)
    body = heights[len(heights) // 2] if heights else 0.0

    def looks_like_label(r: pymupdf.Rect, ws: list[str]) -> bool:
        if len(ws) > 8 or r.is_empty or r.width > 0.55 * ctx.pw:
            return False
        if len(ws) >= 2 and ws[-1].endswith((".", ";", ":", ",")):
            return False  # the tail of a sentence
        if ws[-1].endswith("-") and len(ws[-1]) > 1:
            return False  # a hyphenated line break inside running text
        return not _EQUATION_NUMBER_RE.match(ws[-1])  # a display equation: "... (12)"

    owners: dict[tuple[int, int], int] = {}
    block_ok: dict[int, bool] = {}
    for key, r in lines.items():
        centre = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        owner = next((i for i, tb in enumerate(ctx.text_blocks) if (tb.rect + (-0.5, -0.5, 0.5, 0.5)).contains(centre)), -1)
        owners[key] = owner
        # A label stands on its own: every line of its text block must look like a label too. This keeps out
        # single short lines of paragraphs, equations and tables whose other lines give them away.
        block_ok[owner] = block_ok.get(owner, True) and looks_like_label(r, words[key])

    # Lines continuing a caption or prose line on the same baseline (split off by sub/superscripts or inline math)
    anchors = [tb.rect for i, tb in enumerate(ctx.text_blocks) if tb.kind != "text" or not block_ok.get(i, True)]
    out = []
    for key, r in lines.items():
        owner = owners[key]
        if owner < 0 or not block_ok[owner] or r.y1 <= top_band or r.y0 >= bottom_band:
            continue
        if ctx.is_running_head(r):
            continue
        tb = ctx.text_blocks[owner]
        if tb.kind != "text" or _SECTION_HEADING_RE.match(_clean_text(tb.text)):
            continue  # captions and section headings
        if any(
            min(a.y1, r.y1) - max(a.y0, r.y0) >= 0.5 * r.height and max(a.x0 - r.x1, r.x0 - a.x1) <= 40.0
            for a in anchors
        ):
            continue
        thickness = r.width if r.height > 1.5 * r.width else r.height  # vertical lines: rotated axis titles
        out.append((r, bool(body) and thickness > 1.15 * body))
    return out


def _column_gutters(ctx: PageContext, boxes: Sequence[pymupdf.Rect] = ()) -> list[tuple[float, float]]:
    """Gaps between text columns, as (x0, x1), found from where column content sits across the page width.

    Column content is the paragraphs (text blocks of 12+ words), the figure and table captions and the figure
    `boxes`, projected onto the x-axis. An empty stretch at least 6 pt wide, centred in the middle 70% of the page,
    with content filling at least 15% of the page height on each side and paragraphs filling 15% on at least one
    side, is a column gutter. Counting figures and captions finds the gutter beside a column that holds only
    figures. A paragraph running across the columns (a full-width abstract) fills the gap, so such a page reports
    no gutter and keeps the old behaviour.
    """
    prose = [tb.rect for tb in ctx.text_blocks if tb.kind == "text" and tb.word_count >= 12]
    content = prose + [tb.rect for tb in ctx.fig_captions + ctx.tab_captions] + list(boxes)
    if not prose or len(content) < 2:
        return []
    spans: list[list[float]] = []
    for x0, x1 in sorted((r.x0, r.x1) for r in content):
        if spans and x0 <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], x1)
        else:
            spans.append([x0, x1])
    def filled(rects: list[pymupdf.Rect], left_end: float, right_start: float) -> tuple[float, float]:
        """Total height of `rects` left of the gap and right of it."""
        return (sum(r.height for r in rects if r.x1 <= left_end + 0.5),
                sum(r.height for r in rects if r.x0 >= right_start - 0.5))

    gutters = []
    for (_, left_end), (right_start, _) in zip(spans, spans[1:]):
        mid = (left_end + right_start) / 2 - ctx.page_rect.x0
        if right_start - left_end < 6.0 or not 0.15 * ctx.pw <= mid <= 0.85 * ctx.pw:
            continue
        content_l, content_r = filled(content, left_end, right_start)
        prose_l, prose_r = filled(prose, left_end, right_start)
        if min(content_l, content_r) >= 0.15 * ctx.ph and max(prose_l, prose_r) >= 0.15 * ctx.ph:
            gutters.append((left_end, right_start))
    return gutters


def _column_edges(ctx: PageContext, boxes: Sequence[pymupdf.Rect]) -> list[ColumnEdge]:
    """Aligned edges of text columns: x where at least 3 paragraphs (text blocks of 12+ words touching none of the
    figure `boxes`) start (`left` edge) or end (`right` edge, justified text), within 1.5 pt.

    Typesetting puts every paragraph of a column on the same x, so such an edge is a near-certain column boundary,
    found even where a wide figure elsewhere on the page fills the gap between the columns (which hides the gutter
    of `_column_gutters`). Paragraphs touching a figure box are left out: text set inside an infographic or a
    colour-bar scale can line up too. Each edge is `(side, x, y0, y1)`, with the vertical span of its paragraphs.
    """
    paras = [tb.rect for tb in ctx.text_blocks
             if tb.kind == "text" and tb.word_count >= 12 and not any(b.intersects(tb.rect) for b in boxes)]
    edges: list[ColumnEdge] = []
    for side in ("left", "right"):
        xs = sorted(((r.x0 if side == "left" else r.x1), i) for i, r in enumerate(paras))
        i = 0
        while i < len(xs):
            j = i
            while j + 1 < len(xs) and xs[j + 1][0] - xs[i][0] <= _COLUMN_EDGE_TOL:
                j += 1
            if j - i + 1 >= 3:
                grp = [paras[k] for _, k in xs[i:j + 1]]
                x = sum(v for v, _ in xs[i:j + 1]) / len(grp)
                edges.append((side, x, min(r.y0 for r in grp), max(r.y1 for r in grp)))
            i = j + 1
    return edges


def _crosses_column_edge(box: pymupdf.Rect, label: pymupdf.Rect, edges: Sequence[ColumnEdge]) -> bool:
    """True when `box` lies wholly outside a text column (left of a column's left edge, or right of its right edge),
    overlaps the column's paragraphs vertically, and `label` reaches past that edge into the column."""
    for side, x, y0, y1 in edges:
        if min(box.y1, y1) - max(box.y0, y0) <= 0:
            continue
        if side == "left" and box.x1 <= x + _COLUMN_EDGE_TOL and label.x1 > x + _COLUMN_EDGE_TOL:
            return True
        if side == "right" and box.x0 >= x - _COLUMN_EDGE_TOL and label.x0 < x - _COLUMN_EDGE_TOL:
            return True
    return False


def _across_gutter(box: pymupdf.Rect, line: pymupdf.Rect, gutters: list[tuple[float, float]]) -> bool:
    """True when `box` stays on one side of a gutter's midline and the centre of `line` lies on the other side.

    The midline, not the gutter edge, decides the side: a figure may reach a little into the gutter (its frame or
    last tick label set wider than the paragraphs) and still belongs to its own column.
    """
    centre = (line.x0 + line.x1) / 2
    for g0, g1 in gutters:
        mid = (g0 + g1) / 2
        if (box.x1 <= mid and centre >= mid) or (box.x0 >= mid and centre <= mid):
            return True
    return False


def _attach_adjacent_label_lines(
    candidates: list[CandidateBox], ctx: PageContext, cfg: DetectorConfig, col_edges: Sequence[ColumnEdge] = ()
) -> None:
    """Grow figure boxes line by line to take in adjacent axis titles, tick values and legends.

    Complements `_expand_plot_axis_labels`, which works on whole text blocks: a block can join the tick values of
    two neighbouring panels (too wide to attach) or straddle the box edge (matching no side). Working on lines,
    with side-specific gaps, recovers those labels. Never crosses captions, prose, another figure, page margins or
    a column gutter or an aligned text-column edge (a figure set in one text column takes no line from the column
    beside it).
    """
    lines = _label_lines(ctx)
    if not lines:
        return
    gutters = _column_gutters(ctx, [c.rect for c in candidates])
    captions = [tb.rect for tb in ctx.fig_captions + ctx.tab_captions]
    prose = [
        tb.rect
        for tb in ctx.text_blocks
        if tb.kind == "text" and tb.word_count >= 12 and not _is_short_axis_label(tb, vertical_ok=True)
    ]
    gaps = (cfg.label_gap_left, cfg.label_gap_right, cfg.label_gap_top, cfg.label_gap_bottom)
    table_cache: list[list[pymupdf.Rect]] = []

    def tables() -> list[pymupdf.Rect]:
        if not table_cache:
            table_cache.append([t.rect for t in ctx.get_page_tables()])
        return table_cache[0]

    for idx, cand in enumerate(candidates):
        if cand.source == "raster" and cand.caption_idx is None:
            continue
        orig = pymupdf.Rect(cand.rect)
        cur = pymupdf.Rect(cand.rect)
        others = [c.rect for j, c in enumerate(candidates) if j != idx]
        for _ in range(8):
            changed = False
            for lr, large in lines:
                if cur.contains(lr):
                    continue
                ho = max(0.0, min(cur.x1, lr.x1) - max(cur.x0, lr.x0))
                vo = max(0.0, min(cur.y1, lr.y1) - max(cur.y0, lr.y0))
                inter = (cur & lr).get_area()
                if inter >= 0.3 * max(1e-6, lr.get_area()):
                    ok = True  # straddles the box edge
                elif lr.x1 <= cur.x0 + 3 and vo >= 0.5 * lr.height:
                    ok = cur.x0 - lr.x1 <= gaps[0]
                elif lr.x0 >= cur.x1 - 3 and vo >= 0.5 * lr.height:
                    ok = lr.x0 - cur.x1 <= gaps[1]
                elif lr.y1 <= cur.y0 + 3 and ho >= 0.5 * lr.width:
                    # above the figure, a line set larger than the body text is a heading, not a panel title
                    ok = not large and cur.y0 - lr.y1 <= gaps[2]
                elif lr.y0 >= cur.y1 - 3 and ho >= 0.5 * lr.width:
                    ok = lr.y0 - cur.y1 <= gaps[3]
                else:
                    ok = False
                if not ok:
                    continue
                if gutters and _across_gutter(orig, lr, gutters):
                    continue
                if col_edges and _crosses_column_edge(orig, lr, col_edges):
                    continue
                expanded = cur | lr
                g = cfg.label_max_growth
                if (orig.x0 - expanded.x0 > g or expanded.x1 - orig.x1 > g
                        or orig.y0 - expanded.y0 > g or expanded.y1 - orig.y1 > g):
                    continue
                if any(expanded.intersects(c + (-2, -2, 2, 2)) for c in captions):
                    continue
                shrunk = [o + (1, 1, -1, -1) for o in others]
                if any(expanded.intersects(o) for o in shrunk if not o.is_empty):
                    continue
                if any(not orig.intersects(p) and (expanded & p).get_area() >= 0.25 * max(1.0, p.get_area()) for p in prose):
                    continue
                if any((t + (-1, -1, 1, 1)).contains(lr) for t in tables()):
                    continue  # a table row (tables are only searched once something is about to be attached)
                cur = expanded
                changed = True
            if not changed:
                break
        if cur != orig:
            ctx.log(f"labels:attach_lines {orig} -> {cur}")
        cand.rect = cur & ctx.page_rect


def _stroke_segments(ctx: PageContext) -> list[tuple[pymupdf.Point, pymupdf.Point]]:
    """Thin straight strokes that may join a figure to a label: line items of stroked paths no wider than 1 pt,
    5 pt to 40% of the page width long. Display-fraction bars (text centred right above and right below the middle
    of a horizontal stroke) are left out: the numerator is not a label of the figure beside the equation.
    """
    segs = []
    for d in ctx.drawings:
        if "s" not in (d.get("type") or "") or (d.get("width") or 0) > 1.0:
            continue
        for it in d["items"]:
            if it[0] == "l" and 5.0 <= abs(it[2] - it[1]) <= 0.4 * ctx.pw:
                segs.append((pymupdf.Point(it[1]), pymupdf.Point(it[2])))
    if not segs:
        return segs
    word_rects = [pymupdf.Rect(w[:4]) for w in ctx.words]

    def fraction_bar(a: pymupdf.Point, b: pymupdf.Point) -> bool:
        if abs(a.y - b.y) > 0.5:
            return False
        x0, x1, y = min(a.x, b.x), max(a.x, b.x), a.y
        m0, m1 = x0 + 0.2 * (x1 - x0), x1 - 0.2 * (x1 - x0)  # over the middle, not at an end (a leader's label)
        over = [w for w in word_rects if m0 <= (w.x0 + w.x1) / 2 <= m1]
        return any(0 <= y - w.y1 <= 8 for w in over) and any(0 <= w.y0 - y <= 8 for w in over)

    return [s for s in segs if not fraction_bar(*s)]


def _attach_stroke_labels(
    candidates: list[CandidateBox], ctx: PageContext, cfg: DetectorConfig, col_edges: Sequence[ColumnEdge] = ()
) -> None:
    """Take in short labels joined to a figure by a thin straight stroke running out of the box.

    A leader line in an anatomy atlas, an axis or a dashed reference line in a plot: one end lies inside the box,
    the other touches a line of text outside it. The whole text block of that line is taken (labels set on 2-3
    lines), even across a column gutter, in the top band of the page or farther than the side gaps of
    `_attach_adjacent_label_lines`. The block must be a short label (at most 10 words, no line over 8 words, not a
    caption, section heading or running head, not inside another figure), and the grown box must touch no caption,
    other figure or paragraph and grow at most `stroke_label_max_growth` pt on any side, and the label must not lie
    past an aligned text-column edge on the far side from the box.
    """
    segs = _stroke_segments(ctx)
    if not segs:
        return
    touch = cfg.stroke_label_touch
    lines: dict[tuple[int, int], pymupdf.Rect] = {}
    nwords: dict[tuple[int, int], int] = {}
    for w in ctx.words:
        key, r = (w[5], w[6]), pymupdf.Rect(w[:4])
        lines[key] = lines[key] | r if key in lines else r
        nwords[key] = nwords.get(key, 0) + 1
    captions = [tb.rect for tb in ctx.fig_captions + ctx.tab_captions]
    prose = [tb.rect for tb in ctx.text_blocks if tb.kind == "text" and tb.word_count >= 12]
    # spatial index: grid cell -> lines within `touch` of it (a page can hold thousands of strokes)
    cell = 24.0
    grid: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for key, r in lines.items():
        for gx in range(int((r.x0 - touch) // cell), int((r.x1 + touch) // cell) + 1):
            for gy in range(int((r.y0 - touch) // cell), int((r.y1 + touch) // cell) + 1):
                grid.setdefault((gx, gy), []).append(key)

    def owner(r: pymupdf.Rect):
        c = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
        return next((tb for tb in ctx.text_blocks if (tb.rect + (-0.5, -0.5, 0.5, 0.5)).contains(c)), None)

    def has_long_line(tb) -> bool:
        box = tb.rect + (-0.5, -0.5, 0.5, 0.5)
        return any(nwords[k] > 8 and box.contains((r.tl + r.br) / 2) for k, r in lines.items())

    g = cfg.stroke_label_max_growth
    for idx, cand in enumerate(candidates):
        if cand.source == "raster" and cand.caption_idx is None:
            continue
        orig = pymupdf.Rect(cand.rect)
        cur = pymupdf.Rect(orig)
        others = [c.rect for j, c in enumerate(candidates) if j != idx]
        deep = orig + (1, 1, -1, -1)
        for a, b in segs:
            for pin, pout in ((a, b), (b, a)):
                if not deep.contains(pin):
                    continue
                best = None
                for key in grid.get((int(pout.x // cell), int(pout.y // cell)), ()):
                    lr = lines[key]
                    if cur.contains(lr):
                        continue
                    d = abs(pymupdf.Point(max(lr.x0 - pout.x, 0, pout.x - lr.x1), max(lr.y0 - pout.y, 0, pout.y - lr.y1)))
                    if d <= touch and (best is None or d < best[0]):
                        best = (d, lr)
                if best is None:
                    continue
                tb = owner(best[1])
                if tb is None or tb.kind != "text" or tb.word_count > 10 or has_long_line(tb):
                    continue
                if _SECTION_HEADING_RE.match(_clean_text(tb.text)) or ctx.is_running_head(tb.rect):
                    continue
                lab = pymupdf.Rect(tb.rect)
                if col_edges and _crosses_column_edge(orig, lab, col_edges):
                    continue
                if any(o.intersects(lab) for o in others):
                    continue
                exp = cur | lab
                if (orig.x0 - exp.x0 > g or exp.x1 - orig.x1 > g
                        or orig.y0 - exp.y0 > g or exp.y1 - orig.y1 > g):
                    continue
                if any(exp.intersects(c + (-2, -2, 2, 2)) for c in captions):
                    continue
                if any(exp.intersects(o + (1, 1, -1, -1)) for o in others if not o.is_empty):
                    continue
                if any(not orig.intersects(p) and (exp & p).get_area() >= 0.25 * max(1.0, p.get_area()) for p in prose):
                    continue
                cur = exp
        if cur != orig:
            ctx.log(f"labels:stroke {orig} -> {cur}")
            cand.rect = cur & ctx.page_rect


def _drop_page_edge_tabs(
    rects: list[pymupdf.Rect], ctx: PageContext, cfg: DetectorConfig = DEFAULT_CONFIG
) -> list[pymupdf.Rect]:
    """Drop boxes that bleed off the top or bottom page edge and stay inside that edge band.

    These are page-number or chapter tabs (a coloured block holding the folio). Run before caption linking: a
    caption set just below such a tab would otherwise claim it as "below" and the real figure beside the
    caption would lose it.
    """
    pr = ctx.page_rect
    band = cfg.edge_tab_band_frac * ctx.ph
    kept = []
    for r in rects:
        top_tab = r.y0 <= pr.y0 + 1.0 and r.y1 <= pr.y0 + band
        bottom_tab = r.y1 >= pr.y1 - 1.0 and r.y0 >= pr.y1 - band
        if top_tab or bottom_tab:
            ctx.log(f"edge_tab:drop {r}")
            continue
        kept.append(r)
    return kept


def _pair_last_orphan_caption(
    candidates: list[CandidateBox], ctx: PageContext, cfg: DetectorConfig = DEFAULT_CONFIG
) -> None:
    """Link the page's only uncaptioned figure to its only unclaimed figure caption.

    Runs last and changes no box. Captions a little beyond the regular reach stay unlinked: a side caption level with
    the figure's bottom 110 pt away, or a label row between figure and caption (Surgical Atlas p109, p157, p376).
    When a page has exactly one of each left over, they almost surely belong together. Three guards keep it safe:
    the caption has at most `orphan_pair_max_caption_lines` lines (a paragraph opening with "Figures 5 (a), (b)..."
    is read as a caption, DocLayNet 1001.1179 p5); the gap is at most `orphan_pair_max_gap`; and the caption must not
    sit nearer to an already captioned figure than that figure's own caption (plus `orphan_pair_swap_margin`). That
    case means an earlier link went wrong, and the leftover pair is not each other's (Surgical Atlas p150, p213).
    """
    owned = {c.caption_idx for c in candidates if c.caption_idx is not None}
    free_caps = [k for k in range(len(ctx.fig_captions)) if k not in owned]
    free_boxes = [c for c in candidates if c.caption_idx is None]
    if len(free_caps) != 1 or len(free_boxes) != 1:
        return
    k, box = free_caps[0], free_boxes[0]
    lines = len(ctx.fig_captions[k].text.strip().splitlines())
    if lines > cfg.orphan_pair_max_caption_lines:
        ctx.log(f"orphan_pair:skip long_caption lines={lines}")
        return
    cr = ctx.fig_captions[k].rect
    gap = _rect_gap(box.rect, cr)
    if gap > cfg.orphan_pair_max_gap:
        ctx.log(f"orphan_pair:skip far gap={gap:.1f}")
        return
    for c in candidates:
        if c.caption_idx is None:
            continue
        own = _rect_gap(c.rect, ctx.fig_captions[c.caption_idx].rect)
        if _rect_gap(c.rect, cr) <= own + cfg.orphan_pair_swap_margin:
            ctx.log(f"orphan_pair:skip near_captioned {c.rect}")
            return
    if min(box.rect.x1, cr.x1) - max(box.rect.x0, cr.x0) > 0:
        side = "below" if cr.y0 >= box.rect.y1 - 2.0 else "above" if cr.y1 <= box.rect.y0 + 2.0 else "side"
    else:
        side = "side"
    box.caption_idx, box.caption_side, box.caption_score = k, side, gap
    ctx.log(f"orphan_pair:link {box.rect} cap={k} side={side} gap={gap:.1f}")


def _clear_running_heads(candidates: list[CandidateBox], ctx: PageContext) -> None:
    """Pull each box edge back past a running head or folio that the box (with its render padding) would show.

    Heads are kept out of every label attachment, but a figure's own box can still reach the head band: a loose
    white EPS bounding box, or an image with an off-white margin. The edge moves only when most of the box stays.
    """
    pad = RENDER_PAD + 0.5
    for cand in candidates:
        r = pymupdf.Rect(cand.rect)
        for head in ctx.running_heads:
            if not (r + (-pad, -pad, pad, pad)).intersects(head):
                continue
            if (head.y0 + head.y1) / 2 < (r.y0 + r.y1) / 2:
                r.y0 = max(r.y0, head.y1 + pad)
            else:
                r.y1 = min(r.y1, head.y0 - pad)
        if r != cand.rect and not r.is_empty and r.height >= 0.6 * cand.rect.height:
            ctx.log(f"running_head:clear {cand.rect} -> {r}")
            cand.rect = r


def _run_page_pipeline(
    page: pymupdf.Page,
    cfg: DetectorConfig = DEFAULT_CONFIG,
    running_heads: list[pymupdf.Rect] | None = None,
    *,
    clock: Callable[[], float] | None = None,
) -> tuple[PageContext, list[CandidateBox], bool]:
    """Execute Phases 1–5 on `page` and return `(PageContext, candidates, is_scanned)`.

    `running_heads` are the page's repeated heads and folios (`running_heads.find_running_heads`), in the same
    unrotated coordinates; single-page callers leave it out.
    """
    _ensure_pymupdf()
    # Phase 1
    ctx = analyze_page(page, cfg=cfg, clock=clock)
    ctx.running_heads = list(running_heads or [])
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
    base_rects = _drop_page_edge_tabs(base_rects, ctx, cfg)
    candidates = merge_candidates(ctx, link_captions(ctx, base_rects, cfg=cfg), cfg=cfg)

    # Orphan-caption vector recovery (e.g., axis-less bar groups beneath an unclaimed caption)
    extra_vecs = _recover_orphan_caption_vectors(
        ctx, filtered_drawings, raster_rects, candidates, raw_cluster_count, cfg=cfg
    )
    # Phase 3b runs after the orphan-caption recovery so that step keeps first claim on its caption
    # (it also gathers vector-drawn axis titles that sit farther away than the rescue gap).
    extra_vecs += rescue_small_vector_pieces(
        ctx, filtered_drawings, raster_rects, [c.rect for c in candidates] + extra_vecs, raw_cluster_count, cfg=cfg
    )
    if extra_vecs:
        base_rects = _merge_touching(
            raster_rects + vector_rects + extra_vecs,
            pad=cfg.touch_pad,
            prevent_page_bg=(ctx.pw, ctx.ph, cfg),
        )
        base_rects = _drop_page_edge_tabs(base_rects, ctx, cfg)
        candidates = merge_candidates(ctx, link_captions(ctx, base_rects, cfg=cfg), cfg=cfg)

    _annotate_candidate_origins(candidates, raster_rects, filtered_rects)
    # Column edges are read once, before any label step grows a box into a neighbouring column.
    col_edges = _column_edges(ctx, [c.rect for c in candidates])
    _expand_plot_axis_labels(candidates, ctx, col_edges)
    if len(candidates) >= 2:
        candidates = merge_candidates(ctx, candidates, cfg=cfg)
        _annotate_candidate_origins(candidates, raster_rects, filtered_rects)
        _expand_plot_axis_labels(candidates, ctx, col_edges)
    _attach_adjacent_label_lines(candidates, ctx, cfg, col_edges)
    _attach_stroke_labels(candidates, ctx, cfg, col_edges)
    _clear_running_heads(candidates, ctx)
    min_uncap_vec_dim = cfg.min_vector_dim * max(1.0, min(ctx.pw, ctx.ph) / 792.0)
    candidates = [
        c
        for c in candidates
        if c.caption_idx is not None
        or c.source != "vector"
        or (c.rect.width >= min_uncap_vec_dim and c.rect.height >= min_uncap_vec_dim)
    ]
    _pair_last_orphan_caption(candidates, ctx, cfg)
    is_scanned = has_full_page_img and not candidates
    return ctx, candidates, is_scanned


def detect_page_figures_debug(
    page: pymupdf.Page, cfg: DetectorConfig = DEFAULT_CONFIG
) -> tuple[list[CandidateBox], bool, list[str]]:
    """Run full pipeline and also return human-readable per-region decision trace for diagnostics."""
    ctx, candidates, is_scanned = _run_page_pipeline(page, cfg=cfg)
    return candidates, is_scanned, ctx.trace


@contextmanager
def unrotated_page(page: pymupdf.Page) -> Iterator[pymupdf.Matrix]:
    """Temporarily clear the page's /Rotate so detection sees one coordinate space.

    On a rotated page PyMuPDF reports text, drawings and image boxes in unrotated coordinates, while `page.rect`
    and `get_pixmap(clip=...)` use the displayed (rotated) page, so the detector's page-size rules and the crop
    disagree. Inside this block every query is unrotated; the yielded matrix maps those coordinates onto the
    displayed page. The original rotation is restored on exit (the document is never saved).
    """
    rotation = page.rotation
    if rotation % 360 == 0:
        yield pymupdf.Identity
        return
    to_display = page.rotation_matrix
    page.set_rotation(0)
    try:
        yield to_display
    finally:
        page.set_rotation(rotation)


def collect_page_figures(page: pymupdf.Page) -> tuple[list[pymupdf.Rect], bool]:
    """Collect logical figure bounding boxes on `page` (displayed-page coordinates) and flag scanned pages."""
    with unrotated_page(page) as to_display:
        _, candidates, is_scanned = _run_page_pipeline(page)
    return [c.rect * to_display for c in candidates], is_scanned
