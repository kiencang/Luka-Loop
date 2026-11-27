"""Running heads and folios found from repetition across the pages of one document.

A running head (journal or chapter title, page number) repeats at the same height on page after page, while
the labels of a figure do not. Looking at the whole document first lets the per-page pipeline keep these lines
out of figure boxes, even when they sit right on top of a figure or below the top band of the page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import pymupdf

_DIGITS_RE = re.compile(r"\d+")
_LETTER_RE = re.compile(r"[^\W\d_]")
TOP_BAND = 0.16  # share of page height searched for running heads
BOTTOM_BAND = 0.16  # share of page height searched for running feet: DocLayNet tune Page-footer tops sit within
#   16% of the page bottom for 99.9% of boxes, within 10% for only 81.6% (dev/doclaynet_reference.md §9, §16)
Y_TOLERANCE = 3.0  # pt between the same line on different pages
MIN_OTHER_PAGES = 2  # pages, besides this one, that must repeat the line
PAGE_WINDOW = 8  # ...within this many pages: heads recur page after page, a repeated figure label does not
MAX_WORDS = 16


@dataclass(frozen=True)
class EdgeLine:
    """One text line of the topmost or bottommost row of a page."""

    side: str  # "top" | "bottom"
    key: str  # lower-cased text with every number replaced by "#"
    text: str
    rect: pymupdf.Rect


def _row(lines: list[tuple[pymupdf.Rect, str]], first: pymupdf.Rect) -> list[tuple[pymupdf.Rect, str]]:
    """Lines sharing a row with `first` (vertical overlap of at least half the smaller line)."""
    return [
        (r, t)
        for r, t in lines
        if min(r.y1, first.y1) - max(r.y0, first.y0) >= 0.5 * min(r.height, first.height)
    ]


def page_edge_lines(page: pymupdf.Page) -> list[EdgeLine]:
    """The topmost and bottommost rows of horizontal text lines of `page`, when they lie in the page margins."""
    area = page.rect
    groups: dict[tuple[int, int], tuple[pymupdf.Rect, list[str]]] = {}
    for w in page.get_text("words"):
        key = (w[5], w[6])
        r = pymupdf.Rect(w[:4])
        if key in groups:
            groups[key] = (groups[key][0] | r, groups[key][1] + [w[4]])
        else:
            groups[key] = (r, [w[4]])
    # Rotated text (a tall line of several characters) has no row; a lone folio digit is tall too, so keep it.
    lines = [
        (r, " ".join(ws))
        for r, ws in groups.values()
        if not r.is_empty and (r.height <= 1.5 * r.width or len("".join(ws)) <= 3)
    ]
    if not lines:
        return []
    out: list[EdgeLine] = []
    top = min(lines, key=lambda lt: lt[0].y0)[0]
    for r, t in _row(lines, top):
        if r.y1 <= area.y0 + TOP_BAND * area.height and len(t.split()) <= MAX_WORDS:
            out.append(EdgeLine("top", _DIGITS_RE.sub("#", t.lower()).strip(), t, r))
    bottom = max(lines, key=lambda lt: lt[0].y1)[0]
    for r, t in _row(lines, bottom):
        if r.y0 >= area.y1 - BOTTOM_BAND * area.height and len(t.split()) <= MAX_WORDS:
            out.append(EdgeLine("bottom", _DIGITS_RE.sub("#", t.lower()).strip(), t, r))
    return out


def find_running_heads(pages: list[list[EdgeLine]]) -> list[list[pymupdf.Rect]]:
    """Per page, the edge lines repeated at the same height on `MIN_OTHER_PAGES` other pages nearby.

    A line made mostly of digits ("3", "S3", "- 3 -") must change from page to page, as a page counter does:
    tick values of the same chart layout repeated on several pages stay identical and are never taken.
    """
    index: dict[tuple[str, str], list[tuple[int, float, str]]] = {}
    for i, lines in enumerate(pages):
        for line in lines:
            index.setdefault((line.side, line.key), []).append((i, (line.rect.y0 + line.rect.y1) / 2, line.text))
    found: list[list[pymupdf.Rect]] = [[] for _ in pages]
    for i, lines in enumerate(pages):
        for line in lines:
            cy = (line.rect.y0 + line.rect.y1) / 2
            counter = len(_LETTER_RE.findall(line.text)) < 3
            others = {
                j
                for j, y, text in index[(line.side, line.key)]
                if j != i and abs(j - i) <= PAGE_WINDOW and abs(y - cy) <= Y_TOLERANCE and (not counter or text != line.text)
            }
            if len(others) >= MIN_OTHER_PAGES:
                found[i].append(pymupdf.Rect(line.rect))
    return found
