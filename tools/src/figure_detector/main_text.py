"""Main text blocks: plain text blocks that read as body prose, scored on a 100-point table.

A figure's box must never grow into body text. Word count alone finds few such blocks (short paragraph tails and
narrow columns slip through), so each plain text block of at least `main_text_min_words` words is scored on eight
features; a block scoring `main_text_min_score` or more is main text. The points come from DocLayNet tune pages
(body Text/List-item blocks vs text inside Picture boxes, banded log-likelihood ratios scaled to a 100-point total):
at 70 points about 97% of body blocks qualify and no text inside a figure did on the val and test sets.
"""

from __future__ import annotations

import collections
import re

from .model import DEFAULT_CONFIG, DetectorConfig, PageContext, pymupdf

_WORD_RE = re.compile(r"[A-Za-z]{2,}")

# feature -> (band lower edges, points per band); a value falls in the last band whose edge it reaches
_POINTS: dict[str, tuple[tuple[float, ...], tuple[int, ...]]] = {
    "words": ((12, 20, 30, 40, 60), (0, 0, 2, 4, 5)),
    "width_rel": ((0, 0.15, 0.25, 0.35, 0.45, 0.6), (0, 4, 10, 22, 17, 24)),
    "chars_per_line": ((0, 20, 35, 50, 70), (0, 6, 10, 14, 14)),
    "lower_frac": ((0, 0.2, 0.35, 0.5, 0.65), (0, 0, 3, 6, 10)),
    "alpha_frac": ((0, 0.5, 0.7, 0.85), (0, 6, 8, 10)),
    "digit_frac": ((0, 0.02, 0.05, 0.1, 0.2), (11, 11, 8, 6, 0)),
    "same_font": ((0, 1), (0, 8)),
    "size_rel": ((0, 0.8, 0.95, 1.05, 1.3), (0, 11, 17, 15, 11)),
}


def _points(feature: str, value: float) -> int:
    edges, pts = _POINTS[feature]
    got = pts[0]
    for edge, p in zip(edges, pts):
        if value >= edge:
            got = p
    return got


def _page_lines(page: pymupdf.Page) -> tuple[list[tuple], float, str]:
    """Text lines as (bbox, size counter, font counter) plus the page's dominant size and font by character count."""
    lines = []
    page_size: collections.Counter = collections.Counter()
    page_font: collections.Counter = collections.Counter()
    for b in page.get_text("dict", flags=0).get("blocks", ()):
        for ln in b.get("lines", ()):
            sizes: collections.Counter = collections.Counter()
            fonts: collections.Counter = collections.Counter()
            for sp in ln.get("spans", ()):
                k = len(sp["text"].strip())
                if k:
                    sizes[round(sp["size"], 1)] += k
                    fonts[sp["font"]] += k
            if sizes:
                page_size.update(sizes)
                page_font.update(fonts)
                lines.append((ln["bbox"], sizes, fonts))
    size = page_size.most_common(1)[0][0] if page_size else 0.0
    font = page_font.most_common(1)[0][0] if page_font else ""
    return lines, size, font


def main_text_score(text: str, rect: pymupdf.Rect, words: int, lines: list[tuple], page_size: float,
                    page_font: str, pw: float) -> int:
    """Score one text block (0-100); `lines` are the page lines whose centre lies in the block."""
    sizes: collections.Counter = collections.Counter()
    fonts: collections.Counter = collections.Counter()
    for _, s, f in lines:
        sizes.update(s)
        fonts.update(f)
    size = sizes.most_common(1)[0][0] if sizes else 0.0
    font = fonts.most_common(1)[0][0] if fonts else ""
    # visual rows: lines sharing a baseline (spans split into several lines) count once
    rows: list[list[float]] = []
    for bbox, _, _ in sorted(lines, key=lambda ln: ln[0][1]):
        if rows and abs(rows[-1][3] - bbox[3]) < 0.5 * max(1.0, bbox[3] - bbox[1]):
            continue
        rows.append(list(bbox))
    text = text.strip()
    toks = text.split()
    feats = {
        "words": words,
        "width_rel": rect.width / pw if pw else 0.0,
        "chars_per_line": len(text) / max(1, len(rows)),
        "lower_frac": sum(1 for w in toks if w[:1].islower()) / max(1, len(toks)),
        "alpha_frac": sum(1 for w in toks if _WORD_RE.search(w)) / max(1, len(toks)),
        "digit_frac": sum(ch.isdigit() for ch in text) / max(1, len(text)),
        "same_font": 1 if font == page_font else 0,
        "size_rel": size / page_size if page_size else 0.0,
    }
    return sum(_points(k, v) for k, v in feats.items())


def main_text_rects(ctx: PageContext, cfg: DetectorConfig = DEFAULT_CONFIG) -> list[pymupdf.Rect]:
    """Rects of the page's main text blocks (computed once per page and kept on `ctx`)."""
    if ctx.main_text is not None:
        return ctx.main_text
    found: list[pymupdf.Rect] = []
    blocks = [tb for tb in ctx.text_blocks if tb.kind == "text" and tb.word_count >= cfg.main_text_min_words]
    if cfg.main_text_min_words > 0 and blocks:
        lines, page_size, page_font = _page_lines(ctx.page)
        for tb in blocks:
            inside = tb.rect + (-0.5, -0.5, 0.5, 0.5)
            mine = [ln for ln in lines
                    if inside.contains(pymupdf.Point((ln[0][0] + ln[0][2]) / 2, (ln[0][1] + ln[0][3]) / 2))]
            s = main_text_score(tb.text, tb.rect, tb.word_count, mine, page_size, page_font, ctx.pw)
            if s >= cfg.main_text_min_score:
                found.append(tb.rect)
    ctx.main_text = found
    return found
