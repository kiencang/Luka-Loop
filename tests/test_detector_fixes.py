"""Regression tests for raster white-margin trimming and line-level axis-label attachment (dev-only; PyMuPDF).

Both fixes came from the DocLayNet severity evaluation (dev/eval_doclaynet.py): extracted images that swallowed
nearby text through an embedded image's white border, and plots whose axis titles were cut off.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pymupdf

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "tools" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import figure_detector as fd  # noqa: E402

BODY = 10.0


def _png_with_white_margin(w: int, h: int, ink: tuple[int, int, int, int]) -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pix.set_rect(pix.irect, (255, 255, 255))
    pix.set_rect(pymupdf.IRect(*ink), (30, 90, 160))
    return pix.tobytes("png")


def _paragraph(page: pymupdf.Page, y: float, lines: int, x0: float = 72.0) -> float:
    text = "The measured response follows the expected trend across all sampled operating conditions here"
    for i in range(lines):
        page.insert_text((x0, y + i * 13), text, fontsize=BODY)
    return y + lines * 13


class TestRasterWhiteMarginTrim(unittest.TestCase):
    def test_text_over_white_border_is_not_swallowed_but_overlaid_labels_are_kept(self) -> None:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        _paragraph(page, 90, 3)
        # Placement box 72..540 x 120..420, but the image content only fills ~ 180..430 x 170..340 (page space)
        page.insert_image(pymupdf.Rect(72, 120, 540, 420), stream=_png_with_white_margin(936, 600, (216, 100, 716, 440)))
        page.insert_text((80, 135), "Body text sitting over the white border of the image", fontsize=BODY)
        page.insert_text((300, 352), "Time (s)", fontsize=8)  # axis title printed over the bottom white margin
        page.insert_text((72, 440), "Figure 1: Response of the sensor array under load.", fontsize=BODY)
        _paragraph(page, 470, 4)

        rects, _ = fd.collect_page_figures(page)
        self.assertEqual(len(rects), 1, rects)
        box = rects[0]
        self.assertGreater(box.y0, 140, f"image must not extend over the body text line at y=135: {box}")
        self.assertLess(box.x0, 185)
        self.assertGreater(box.x1, 425)
        self.assertGreaterEqual(box.y1, 353, f"axis title printed over the trimmed margin must be kept: {box}")
        self.assertLess(box.y1, 425)


    def test_image_decode_errors_fall_back_to_the_placement_box(self) -> None:
        # Real PDFs carry soft masks of a different size or images that already have alpha; PyMuPDF raises its own
        # exception types for those. Trimming is optional, so any failure must keep the original box, not crash.
        from unittest import mock

        import figure_detector.raster as raster

        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        _paragraph(page, 90, 3)
        page.insert_image(pymupdf.Rect(72, 120, 540, 420), stream=_png_with_white_margin(936, 600, (216, 100, 716, 440)))
        page.insert_text((72, 440), "Figure 1: Response of the sensor array under load.", fontsize=BODY)

        class FzLikeError(Exception):
            pass

        fd._ensure_pymupdf()
        with mock.patch.object(raster.pymupdf, "Pixmap", side_effect=FzLikeError("mask size mismatch")):
            rects, _ = fd.collect_page_figures(page)
        self.assertEqual(len(rects), 1)
        self.assertAlmostEqual(rects[0].y0, 120, delta=1)


class TestAxisLabelLineAttachment(unittest.TestCase):
    def _plot_page(self) -> tuple[pymupdf.Page, pymupdf.Rect]:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 150), "Results Overview", fontsize=16)  # heading, set larger than body text
        page.insert_text((72, 176), "end of a sentence.", fontsize=BODY)  # tail of a paragraph above the figure
        frame = pymupdf.Rect(170, 210, 470, 420)
        shape = page.new_shape()
        shape.draw_rect(frame)
        pts = [pymupdf.Point(frame.x0 + i * 15, frame.y1 - 10 - (i * i) % 170) for i in range(21)]
        shape.draw_polyline(pts)
        for i in range(12):  # curved markers so the cluster reads as a plot
            c = pymupdf.Point(frame.x0 + 20 + i * 22, frame.y0 + 40 + (i % 4) * 30)
            shape.draw_circle(c, 3)
        shape.finish(color=(0, 0, 0), width=0.8)
        shape.commit()
        for i, x in enumerate(range(170, 471, 60)):  # x tick labels just below the frame
            page.insert_text((x - 4, 432), str(i), fontsize=8)
        page.insert_text((280, 456), "Elapsed time (minutes)", fontsize=9)  # x-axis title ~22 pt below the ticks row
        page.insert_text((150, 380), "Normalised signal", fontsize=9, rotate=90)  # y title 20+ pt left of frame
        page.insert_text((72, 490), "Figure 2: Normalised signal against elapsed time for all runs.", fontsize=BODY)
        _paragraph(page, 520, 5)
        return page, frame

    def test_axis_titles_beyond_the_old_16pt_reach_are_attached(self) -> None:
        page, frame = self._plot_page()
        rects, _ = fd.collect_page_figures(page)
        self.assertEqual(len(rects), 1, rects)
        box = rects[0]
        self.assertGreaterEqual(box.y1, 455, f"x-axis title must be inside the image: {box}")
        self.assertLessEqual(box.x0, 150, f"rotated y-axis title must be inside the image: {box}")
        self.assertLess(box.y1, 480, f"caption must stay outside: {box}")

    def test_heading_and_paragraph_tail_above_the_figure_stay_outside(self) -> None:
        page, frame = self._plot_page()
        box = fd.collect_page_figures(page)[0][0]
        self.assertGreater(box.y0, 180, f"heading / sentence tail above the plot must not be attached: {box}")


def _blue_png(w: int, h: int) -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    pix.set_rect(pix.irect, (30, 90, 160))
    return pix.tobytes("png")


def _blue_share(png: Path) -> float:
    pix = pymupdf.Pixmap(str(png))
    s, n = pix.samples, pix.n
    total = blue = 0
    for i in range(0, len(s) - n, n * 5):
        total += 1
        blue += s[i] < 80 and s[i + 2] > 120
    return blue / max(1, total)


class TestRotatedPages(unittest.TestCase):
    """DocLayNet showed every figure on /Rotate pages was cropped from the wrong place (10/10 on 27 pages).

    PyMuPDF reports text, drawings and images in unrotated coordinates, but `page.rect` and the render clip use the
    displayed page. Detection now runs on the unrotated page and the box is mapped onto the displayed page.
    """

    IMAGE = pymupdf.Rect(150, 200, 450, 387.5)  # unrotated placement on a 612 x 792 page

    def _pdf(self, folder: Path, rotation: int, second_image: pymupdf.Rect | None = None) -> Path:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        _paragraph(page, 90, 4)
        page.insert_image(self.IMAGE, stream=_blue_png(400, 250))
        page.insert_text((150, 405), "Figure 1: Response of the sensor array under load.", fontsize=BODY)
        _paragraph(page, 440, 6)
        if second_image is not None:
            page.insert_image(second_image, stream=_blue_png(int(second_image.width), int(second_image.height)))
        page.set_rotation(rotation)
        path = folder / f"rot{rotation}.pdf"
        doc.save(path)
        return path

    def _extract(self, rotation: int, second_image: pymupdf.Rect | None = None) -> tuple[dict, Path, pymupdf.Rect]:
        import json
        import tempfile

        from figure_detector.extract import extract_images

        tmp = Path(tempfile.mkdtemp(prefix="luka_rot_"))
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        pdf = self._pdf(tmp, rotation, second_image)
        out = tmp / "out"
        extract_images(pdf, out, dpi=72, write_meta=True)
        with pymupdf.open(pdf) as doc:
            page = doc[0]
            displayed_page = page.rect
            expected = self.IMAGE * page.rotation_matrix
        meta = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        meta["_expected"] = [
            round((expected.x0 - displayed_page.x0) / displayed_page.width, 3),
            round((expected.y0 - displayed_page.y0) / displayed_page.height, 3),
            round((expected.x1 - displayed_page.x0) / displayed_page.width, 3),
            round((expected.y1 - displayed_page.y0) / displayed_page.height, 3),
        ]
        return meta, out, displayed_page

    def test_figure_is_cropped_and_boxed_on_the_displayed_page_for_every_rotation(self) -> None:
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                meta, out, _ = self._extract(rotation)
                self.assertEqual(len(meta["figures"]), 1, meta["figures"])
                fig = meta["figures"][0]
                for got, want in zip(fig["box"], meta["_expected"]):
                    self.assertAlmostEqual(got, want, delta=0.012, msg=f"box {fig['box']} vs {meta['_expected']}")
                self.assertGreater(_blue_share(out / fig["file"]), 0.85, "crop must show the figure, not nearby page")
                if rotation in (90, 270):
                    self.assertGreater(fig["height_px"], fig["width_px"], "PNG must be upright on the displayed page")
                else:
                    self.assertGreater(fig["width_px"], fig["height_px"])
                self.assertTrue((fig["caption"] or "").startswith("Figure 1"), fig)

    def test_rotated_page_numbers_figures_in_displayed_reading_order(self) -> None:
        # Unrotated, the small image sits below the big one; on a 90-degree page it is displayed to the LEFT of it,
        # on the same band, so it must be numbered first.
        meta, _, displayed_page = self._extract(90, second_image=pymupdf.Rect(155, 640, 430, 700))
        self.assertEqual(len(meta["figures"]), 2, meta["figures"])
        first, second = meta["figures"]
        self.assertEqual(first["file"], "fig_p1_1.png")
        self.assertLess(first["box"][0], second["box"][0], f"displayed left figure must be fig_p1_1: {meta['figures']}")

    def test_collect_page_figures_reports_displayed_boxes_and_keeps_the_rotation(self) -> None:
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="luka_rot_"))
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        with pymupdf.open(self._pdf(tmp, 90)) as doc:
            page = doc[0]
            rects, _ = fd.collect_page_figures(page)
            self.assertEqual(page.rotation, 90, "detection must restore the page rotation")
            expected = self.IMAGE * page.rotation_matrix
        self.assertEqual(len(rects), 1, rects)
        self.assertLess(abs(rects[0].x0 - expected.x0) + abs(rects[0].y0 - expected.y0), 6, f"{rects[0]} vs {expected}")


def _line(side: str, text: str, y: float, x: float = 300.0):
    from figure_detector.running_heads import _DIGITS_RE, EdgeLine

    return EdgeLine(side, _DIGITS_RE.sub("#", text.lower()).strip(), text, pymupdf.Rect(x, y, x + 6 * len(text), y + 9))


class TestRunningHeads(unittest.TestCase):
    """Running heads and folios printed right above a top figure were taken into the image (dev/header-pdf set:
    18 of 42 images). Repetition across pages tells them apart from figure labels, which single-page rules cannot.
    """

    def test_repeated_heads_and_page_counters_are_found(self) -> None:
        from figure_detector.running_heads import find_running_heads

        pages = [[]] + [[_line("top", "J. Appl. Hydrodyn. 41 (2026)", 40, 48), _line("top", str(n), 40, 540)] for n in range(2, 6)]
        pages.append([_line("bottom", "Page 6 of 6", 770)])
        found = find_running_heads(pages)
        self.assertEqual(found[0], [])
        for n in range(1, 5):
            self.assertEqual(len(found[n]), 2, f"title and folio of page {n + 1}: {found[n]}")
        self.assertEqual(found[5], [], "a foot printed on one page only is not a running foot")

    def test_identical_numbers_and_far_apart_labels_are_not_heads(self) -> None:
        from figure_detector.running_heads import find_running_heads

        # The same chart layout at the top of several pages: its top tick value never changes like a page counter.
        ticks = find_running_heads([[_line("top", "1.50", 60)] for _ in range(5)])
        self.assertTrue(all(not f for f in ticks), ticks)
        # A figure label repeated at the same place, but far apart in a long book.
        pages: list[list] = [[] for _ in range(60)]
        for i in (5, 30, 55):
            pages[i] = [_line("top", "Supine position", 70)]
        self.assertTrue(all(not f for f in find_running_heads(pages)))

    def _plot_pdf(self, folder: Path, pages: int) -> Path:
        """A report whose page number sits 10 pt above a captioned vector plot on every page after the first."""
        doc = pymupdf.open()
        for n in range(1, pages + 1):
            page = doc.new_page(width=595, height=842)
            if n == 1:
                _paragraph(page, 90, 30)
                continue
            page.insert_text((295, 38), str(n), fontsize=9)
            frame = pymupdf.Rect(140, 50, 470, 230)
            page.draw_rect(frame, color=(0, 0, 0), width=0.8)
            pts = [pymupdf.Point(frame.x0 + 6 * i, frame.y1 - 20 - 120 * abs(((i * 7) % 40) - 20) / 20) for i in range(55)]
            page.draw_polyline(pts, color=(0.1, 0.3, 0.8), width=1.2)
            for k, label in enumerate(("0", "2", "4", "6", "8", "10")):
                page.insert_text((frame.x0 + k * 64, frame.y1 + 11), label, fontsize=8)
            for k, label in enumerate(("1.0", "0.5", "0.0")):
                page.insert_text((frame.x0 - 18, frame.y0 + 8 + k * 80), label, fontsize=8)
            page.insert_text((140, 262), f"Figure {n - 1}. Response of the sensor array under load.", fontsize=BODY)
            _paragraph(page, 290, 30)
        path = folder / f"report{pages}.pdf"
        doc.save(path)
        return path

    def test_page_number_above_a_top_figure_stays_out_of_the_image(self) -> None:
        import json
        import tempfile

        from figure_detector.extract import extract_images

        tmp = Path(tempfile.mkdtemp(prefix="luka_rh_"))
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        pdf = self._plot_pdf(tmp, 5)
        with pymupdf.open(pdf) as doc:
            rects, _ = fd.collect_page_figures(doc[2])  # one page alone: no repetition to go by
        self.assertEqual(len(rects), 1, rects)
        self.assertLess(rects[0].y0, 32, f"precondition: the single-page rules take the folio in: {rects[0]}")

        extract_images(pdf, tmp / "out", dpi=72, write_meta=True)
        figures = json.loads((tmp / "out" / "manifest.json").read_text(encoding="utf-8"))["figures"]
        self.assertEqual(len(figures), 4, figures)
        for fig in figures:
            top = fig["box"][1] * 842 - 4.0  # crop top, with the render padding
            self.assertGreater(top, 40.5, f"folio (y 28-40.7) inside the image of page {fig['page']}: {fig}")
            self.assertLess(fig["box"][1] * 842, 52, f"the plot frame itself must stay whole: {fig}")


class TestSmallVectorRescue(unittest.TestCase):
    """Vector clustering joins drawings only within 5 pt, so a panel of small cells (or dots, legend marks,
    vector-drawn tick labels) spaced a little wider broke into pieces that were each rejected as too_small, and
    the panel was cut off the figure (DocLayNet tune: 98 clipped and 11 missed figures recovered).
    """

    def _page(self) -> pymupdf.Page:
        doc = pymupdf.open()
        self.addCleanup(doc.close)
        page = doc.new_page(width=595, height=842)
        y = _paragraph(page, 90, 8)
        frame = pymupdf.Rect(110, y + 20, 280, y + 130)
        page.draw_rect(frame, color=(0, 0, 0), width=0.8)
        pts = [pymupdf.Point(frame.x0 + 3 * i, frame.y1 - 10 - 80 * abs(((i * 7) % 40) - 20) / 20) for i in range(56)]
        page.draw_polyline(pts, color=(0.1, 0.3, 0.8), width=1.2)
        # Right panel: 8 x 5 cells of 10 pt, 8 pt apart -- every cell is its own cluster.
        for i in range(8):
            for j in range(5):
                x, top = 296 + 18 * i, frame.y0 + 10 + 18 * j
                page.draw_rect(pymupdf.Rect(x, top, x + 10, top + 10), color=(0, 0, 0), fill=(0.2, 0.4, 0.8), width=0.6)
        page.insert_text(
            (110, frame.y1 + 24), "Figure 1. Load curve (left) and the map of active sensor cells (right).", fontsize=BODY
        )
        _paragraph(page, frame.y1 + 50, 10)
        # Control: short equation bars inside prose lines must not become a figure.
        for k in range(6):
            page.insert_text((72, 640 + k * 13), "the ratio of the two measured loads equals", fontsize=BODY)
            page.draw_line((300, 637 + k * 13), (316, 637 + k * 13), width=0.5)
            page.draw_line((330, 637 + k * 13), (346, 637 + k * 13), width=0.5)
        return page

    def test_panel_of_small_cells_joins_the_figure(self) -> None:
        from figure_detector.model import DetectorConfig
        from figure_detector.pipeline import _run_page_pipeline

        page = self._page()
        _, before, _ = _run_page_pipeline(page, cfg=DetectorConfig(small_rescue_gap=0.0))
        self.assertEqual(len(before), 1, before)
        self.assertLess(before[0].rect.x1, 290, f"precondition: the cell panel is cut off without the rescue: {before}")

        rects, _ = fd.collect_page_figures(page)
        self.assertEqual(len(rects), 1, f"one figure, no figure from the equation bars: {rects}")
        self.assertLessEqual(rects[0].x0, 110.5, rects)
        self.assertGreaterEqual(rects[0].x1, 431.5, f"all 8 cell columns inside the image: {rects}")
        self.assertLess(rects[0].y1, 340, f"caption stays out of the image: {rects}")

    def test_pieces_never_bridge_two_figures_across_a_caption(self) -> None:
        from figure_detector.pipeline import _run_page_pipeline

        doc = pymupdf.open()
        self.addCleanup(doc.close)
        page = doc.new_page(width=595, height=842)
        for n, top in ((1, 90), (2, 262)):
            frame = pymupdf.Rect(120, top, 400, top + 130)
            page.draw_rect(frame, color=(0, 0, 0), width=0.8)
            pts = [pymupdf.Point(frame.x0 + 3 * i, frame.y1 - 10 - 60 * abs(((i * 7) % 40) - 20) / 20) for i in range(93)]
            page.draw_polyline(pts, color=(0.1, 0.3, 0.8), width=1.2)
            page.insert_text((120, frame.y1 + 20), f"Figure {n}. Strain on the beam.", fontsize=BODY)
        # A column of small markers 8 pt apart beside both plots chains them past the caption of Figure 1.
        for k in range(17):
            page.draw_rect(pymupdf.Rect(412, 96 + 18 * k, 422, 106 + 18 * k), color=(0, 0, 0), fill=(0.8, 0.2, 0.2), width=0.6)
        ctx, cands, _ = _run_page_pipeline(page)
        self.assertTrue(any("rescue_small:skip" in t for t in ctx.trace), ctx.trace)
        self.assertEqual(len(cands), 2, [c.rect for c in cands])
        for c in cands:
            self.assertFalse(c.rect.contains(pymupdf.Point(200, 236)), f"caption of Figure 1 inside an image: {c.rect}")


class TestWordBandEquivalence(unittest.TestCase):
    """The Y-band word index in `_filter_drawings` must agree with brute-force `intersects` on every edge case."""

    def test_word_bands_match_brute_force_on_boundaries_and_spans(self) -> None:
        from figure_detector.geometry import _vert_overlap
        from figure_detector.vector import _build_word_bands, _has_overlapping_word

        words = [
            pymupdf.Rect(10, -8, 40, 2),
            pymupdf.Rect(50, 15.9, 90, 16.1),  # straddles a 16 pt band boundary
            pymupdf.Rect(100, 16.0, 160, 32.0),  # sits cleanly on band boundary [16, 32]
            pymupdf.Rect(200, 40.0, 260, 75.0),  # spans 3 bands
            pymupdf.Rect(300, 100.0, 300, 110.0),  # degenerate zero-width rect
        ]
        bands = _build_word_bands(words)
        probes = [
            pymupdf.Rect(15, -4, 35, 1),
            pymupdf.Rect(40, -8, 50, 2),  # touches x1==x0 only (no intersection)
            pymupdf.Rect(60, 10, 80, 16.0),  # overlaps straddling word vertically by 0.1
            pymupdf.Rect(105, 32.0, 150, 44.0),  # touches y0==y1 only
            pymupdf.Rect(110, 18.0, 150, 30.0),  # fully inside boundary word
            pymupdf.Rect(210, 52.0, 240, 62.0),  # middle band of multi-band word
            pymupdf.Rect(295, 100.0, 305, 110.0),  # crosses degenerate word
            pymupdf.Rect(0, 200.0, 50, 220.0),  # empty band
        ]
        for r in probes:
            for half_v in (False, True):
                expected = any(
                    r.intersects(w) and (not half_v or _vert_overlap(r, w) >= 0.5 * min(r.height, w.height))
                    for w in words
                )
                got = _has_overlapping_word(r, bands, require_half_vert=half_v)
                self.assertEqual(got, expected, f"probe={r}, half_v={half_v}")


class TestColumnGutter(unittest.TestCase):
    """A figure set in one text column takes no label line from the column beside it (DocLayNet 1001.1552 p11)."""

    @staticmethod
    def _two_column_page(left_prose: bool = True) -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        text = "Measured response follows the expected trend here"
        for i in range(12 if left_prose else 0):  # left column paragraph above the figure
            page.insert_text((54, 72 + i * 12), text, fontsize=BODY)
        frame = pymupdf.Rect(70, 260, 296, 400)
        shape = page.new_shape()
        shape.draw_rect(frame)
        shape.draw_polyline([pymupdf.Point(frame.x0 + i * 11, frame.y1 - 10 - (i * i) % 120) for i in range(21)])
        for i in range(10):
            shape.draw_circle(pymupdf.Point(frame.x0 + 20 + i * 20, frame.y0 + 30 + (i % 4) * 25), 3)
        shape.finish(color=(0, 0, 0), width=0.8)
        shape.commit()
        for i, x in enumerate(range(70, 297, 45)):
            page.insert_text((x - 3, 412), str(i), fontsize=8)
        page.insert_text((54, 440), "Figure 1: Response against time for all runs.", fontsize=BODY)
        for i in range(14):  # right column paragraph above the equation
            page.insert_text((316, 72 + i * 12), text, fontsize=BODY)
        page.insert_text((316, 300), "= a + b", fontsize=BODY)  # short display-equation line, 20 pt from the frame
        for i in range(14):  # right column paragraph below the equation
            page.insert_text((316, 340 + i * 12), text, fontsize=BODY)
        return page

    def test_equation_line_in_the_next_column_stays_outside(self) -> None:
        from unittest import mock

        import figure_detector.pipeline as pipe

        page = self._two_column_page()
        with mock.patch.object(pipe, "_column_gutters", return_value=[]):
            before = fd.collect_page_figures(page)[0]
        self.assertEqual(len(before), 1, before)
        self.assertGreater(before[0].x1, 316, f"fixture must reproduce the crossing without the rule: {before}")

        rects = fd.collect_page_figures(page)[0]
        self.assertEqual(len(rects), 1, rects)
        self.assertLess(rects[0].x1, 300, f"figure must stop at its own column: {rects[0]}")
        self.assertGreaterEqual(rects[0].y1, 412, f"tick labels under the plot must still be attached: {rects[0]}")

    def test_gutter_found_beside_a_column_of_figures_only(self) -> None:
        """The left column holds only the figure and its caption: the figure box counts as column content
        (Surgical Atlas p361, where a label line of the text column was pulled into the image)."""
        from unittest import mock

        import figure_detector.pipeline as pipe

        page = self._two_column_page(left_prose=False)
        ctx, cands, _ = pipe._run_page_pipeline(page)
        self.assertEqual(pipe._column_gutters(ctx), [], "precondition: paragraphs and captions alone find no gutter")
        self.assertTrue(pipe._column_gutters(ctx, [c.rect for c in cands]), "the figure box reveals the gutter")
        with mock.patch.object(pipe, "_column_gutters", return_value=[]):
            before = fd.collect_page_figures(page)[0]
        self.assertEqual(len(before), 1, before)
        self.assertGreater(before[0].x1, 316, f"fixture must reproduce the crossing without the rule: {before}")

        rects = fd.collect_page_figures(page)[0]
        self.assertEqual(len(rects), 1, rects)
        self.assertLess(rects[0].x1, 300, f"figure must stop at its own column: {rects[0]}")
        self.assertGreaterEqual(rects[0].y1, 412, f"tick labels under the plot must still be attached: {rects[0]}")


class TestStrokeLabels(unittest.TestCase):
    """A label joined to the figure by a thin stroke (leader line, axis) is taken in whole, even beyond the side
    gaps (Surgical Atlas leader lines, DocLayNet axis titles); the bar of a display fraction is not a leader."""

    @staticmethod
    def _image_page() -> tuple[pymupdf.Page, pymupdf.Rect]:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        frame = pymupdf.Rect(150, 300, 450, 500)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 200), False)
        pix.clear_with(150)
        page.insert_image(frame, pixmap=pix)
        page.insert_text((150, 522), "Figure 1: Knee joint seen from the front.", fontsize=BODY)
        return page, frame

    @staticmethod
    def _stroke(page: pymupdf.Page, a: tuple[float, float], b: tuple[float, float]) -> None:
        shape = page.new_shape()
        shape.draw_line(a, b)
        shape.finish(color=(0, 0, 0), width=0.4)
        shape.commit()

    def test_leader_line_takes_the_whole_label(self) -> None:
        page, frame = self._image_page()
        page.insert_text((322, 238), "Medial collateral\nligament", fontsize=9)  # 2-line label, 44 pt above
        self.assertEqual(fd.collect_page_figures(page)[0], [frame], "no stroke: the label is too far to attach")

        self._stroke(page, (345, 360), (345, 255))  # from inside the image up to the label
        rects = fd.collect_page_figures(page)[0]
        self.assertEqual(len(rects), 1, rects)
        self.assertLess(rects[0].y0, 232, f"both label lines must be taken: {rects[0]}")
        self.assertEqual((rects[0].x0, rects[0].x1, rects[0].y1), (frame.x0, frame.x1, frame.y1), rects[0])

    def test_fraction_bar_is_not_a_leader(self) -> None:
        page, frame = self._image_page()
        self._stroke(page, (440, 400), (522, 400))
        page.insert_text((475, 396), "alpha beta", fontsize=BODY)  # touches the stroke's outer end
        self.assertGreater(fd.collect_page_figures(page)[0][0].x1, 515, "a stroke to a label: taken")

        page.insert_text((490, 413), "2z", fontsize=BODY)  # a denominator turns the stroke into a fraction bar
        self.assertEqual(fd.collect_page_figures(page)[0], [frame])


class TestColumnEdge(unittest.TestCase):
    """Paragraphs starting on one x mark a text column: a figure left of it takes no label from the column, even
    where a full-width figure fills the gap between the columns and hides the gutter (Surgical Atlas p42, p110)."""

    @staticmethod
    def _page() -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        para = "\n".join(["Measured response follows the expected trend in all runs"] * 3)
        for k in range(5):  # right column paragraphs, all starting at x = 316
            page.insert_text((316, 80 + k * 100), para, fontsize=BODY)

        def plot(frame: pymupdf.Rect) -> None:
            shape = page.new_shape()
            shape.draw_rect(frame)
            step = frame.width / 20
            shape.draw_polyline([pymupdf.Point(frame.x0 + i * step, frame.y1 - 10 - (i * i) % (frame.height - 20)) for i in range(21)])
            for i in range(10):
                shape.draw_circle(pymupdf.Point(frame.x0 + 15 + i * (frame.width - 30) / 9, frame.y0 + 25 + (i % 4) * 20), 3)
            shape.finish(color=(0, 0, 0), width=0.8)
            shape.commit()

        plot(pymupdf.Rect(70, 120, 300, 260))
        page.insert_text((54, 280), "Figure 1: Response against time for all runs.", fontsize=BODY)
        page.insert_text((316, 240), "Imaging", fontsize=BODY)  # short heading of the right column, 16 pt away
        plot(pymupdf.Rect(70, 600, 540, 740))  # full width: fills the gap between the columns
        page.insert_text((54, 760), "Figure 2: Full width response map for every run.", fontsize=BODY)
        return page

    def test_label_step_stops_at_the_column_edge(self) -> None:
        from unittest import mock

        import figure_detector.pipeline as pipe

        page = self._page()
        ctx, cands, _ = pipe._run_page_pipeline(page)
        self.assertEqual(pipe._column_gutters(ctx, [c.rect for c in cands]), [], "precondition: no gutter is found")
        self.assertIn(316.0, [round(x, 1) for side, x, _, _ in pipe._column_edges(ctx, []) if side == "left"])
        with mock.patch.object(pipe, "_column_edges", return_value=[]):
            before = fd.collect_page_figures(page)[0]
        self.assertGreater(before[0].x1, 316, f"fixture must reproduce the crossing without the rule: {before}")

        rects = fd.collect_page_figures(page)[0]
        self.assertEqual(len(rects), 2, rects)
        self.assertEqual(rects[0], pymupdf.Rect(70, 120, 300, 260), "the figure must stop at its own column")
        self.assertEqual(rects[1], pymupdf.Rect(70, 600, 540, 740), "the full-width figure is untouched")

    def test_paragraphs_touching_a_figure_make_no_edge(self) -> None:
        import figure_detector.pipeline as pipe

        ctx, _, _ = pipe._run_page_pipeline(self._page())
        self.assertEqual(pipe._column_edges(ctx, [pymupdf.Rect(300, 60, 600, 520)]), [])


class TestFinePolylinePlot(unittest.TestCase):
    """A line plot whose curves are fine polylines is a figure, not a table (DocLayNet 1002.0011 p19 and 11 more).

    Every step of such a curve is under 2 pt, so the curve counter used to see only the frame, the panel divider and
    the tick numbers: PyMuPDF found a table there and the uncaptioned plot was dropped.
    """

    @staticmethod
    def _plot_page() -> pymupdf.Page:
        import math

        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        _paragraph(page, 72, 10)
        frame = pymupdf.Rect(130, 230, 480, 470)
        mid = (frame.x0 + frame.x1) / 2
        shape = page.new_shape()
        shape.draw_rect(frame)
        shape.finish(color=(0, 0, 0), width=0.8)
        shape.draw_line((mid, frame.y0), (mid, frame.y1))  # divider between panels (A) and (B)
        shape.finish(color=(0, 0, 0), width=0.8)
        shape.draw_line((frame.x0, 300), (frame.x1, 300))  # zero line
        shape.finish(color=(0.6, 0.6, 0.6), width=0.4)
        for x0, x1 in ((frame.x0, mid), (mid, frame.x1)):
            ts = [k * 1.2 for k in range(int((x1 - x0) / 1.2))]
            shape.draw_polyline([pymupdf.Point(x0 + t, 300 + 120 * math.sin(t / 50.0) * t / (x1 - x0)) for t in ts])
            shape.finish(color=(0, 0, 1), width=0.8)
        shape.commit()
        for k, x in enumerate(range(130, 481, 35)):
            page.insert_text((x - 3, 482), str(k), fontsize=8)
        for k, y in enumerate(range(240, 471, 40)):
            page.insert_text((112, y + 3), f"-{k}.5", fontsize=8)
        page.insert_text((140, 245), "(A) phi(y) sigma(y)", fontsize=9)
        page.insert_text((315, 245), "(B) phi(y) chi(y)", fontsize=9)
        page.insert_text((280, 500), "y [M]", fontsize=9)
        _paragraph(page, 600, 10)
        return page

    def test_fine_polyline_curves_keep_the_plot(self) -> None:
        from unittest import mock

        import figure_detector.geometry as geo

        with mock.patch.object(geo, "_POLYLINE_MIN_STEPS", 10**9):
            before = fd.collect_page_figures(self._plot_page())[0]
        self.assertEqual(before, [], "fixture must reproduce the table rejection without polyline steps")

        rects = fd.collect_page_figures(self._plot_page())[0]
        self.assertEqual(len(rects), 1, rects)
        self.assertTrue(rects[0].contains(pymupdf.Rect(130, 230, 480, 470)), rects[0])


class TestTablePathReuse(unittest.TestCase):
    """`find_tables()` gets copies of the page drawings, so table searches never edit the detector's own paths."""

    def test_table_searches_leave_drawing_items_and_rects_unchanged(self) -> None:
        from figure_detector.text import analyze_page

        doc = pymupdf.open()
        self.addCleanup(doc.close)
        page = doc.new_page(width=612, height=792)
        # A ruled 3x3 grid with text (a table) and a closed triangle drawn with line segments.
        for k in range(4):
            page.draw_line((100, 100 + 30 * k), (400, 100 + 30 * k))
            page.draw_line((100 + 100 * k, 100), (100 + 100 * k, 190))
        for r in range(3):
            for c in range(3):
                page.insert_text((110 + 100 * c, 120 + 30 * r), f"cell {r}{c}", fontsize=BODY)
        page.draw_polyline([(150, 300), (300, 450), (120, 420)])
        ctx = analyze_page(page)
        # PyMuPDF 1.28 reports closed line paths with an explicit closing segment and closePath=False; other
        # versions may report closePath=True instead, which is when find_tables appends a segment. Model that form.
        tri = next(dr for dr in ctx.drawings if dr["rect"].y0 >= 290)
        tri["closePath"] = True
        before = [(len(dr["items"]), tuple(dr["rect"])) for dr in ctx.drawings]
        ctx.get_page_tables()
        ctx.find_tables_in_clip(pymupdf.Rect(90, 90, 410, 200))
        ctx.find_tables_in_clip(pymupdf.Rect(100, 280, 320, 470))
        after = [(len(dr["items"]), tuple(dr["rect"])) for dr in ctx.drawings]
        self.assertEqual(after, before)


class TestPageBudget(unittest.TestCase):
    """Per-page 30 s budget: never alters pages below the limit, and cleanly skips heavy passes once exceeded."""

    def test_budget_disabled_and_enabled_give_identical_results_below_threshold(self) -> None:
        from figure_detector.model import DetectorConfig
        from figure_detector.pipeline import _run_page_pipeline, unrotated_page

        samples = sorted((REPO_ROOT / "tests" / "layout_samples").glob("*.pdf"))
        self.assertTrue(samples)
        for pdf_path in samples:
            with pymupdf.open(pdf_path) as doc_off, pymupdf.open(pdf_path) as doc_on:
                for p_off, p_on in zip(doc_off, doc_on):
                    with unrotated_page(p_off):
                        ctx_off, cands_off, scan_off = _run_page_pipeline(p_off, cfg=DetectorConfig(max_page_seconds=0.0))
                    with unrotated_page(p_on):
                        ctx_on, cands_on, scan_on = _run_page_pipeline(p_on, cfg=DetectorConfig(max_page_seconds=30.0))
                    self.assertFalse(ctx_off.timed_out)
                    self.assertFalse(ctx_on.timed_out)
                    self.assertEqual(scan_on, scan_off, pdf_path.name)
                    self.assertEqual(
                        [(tuple(round(v, 3) for v in c.rect), c.source, c.caption_idx) for c in cands_on],
                        [(tuple(round(v, 3) for v in c.rect), c.source, c.caption_idx) for c in cands_off],
                        f"30s budget changed output on fast page of {pdf_path.name}",
                    )

    def test_timeout_after_phase1_keeps_untrimmed_raster_and_skips_vector_clustering(self) -> None:
        from unittest import mock

        from figure_detector.model import DetectorConfig
        from figure_detector.pipeline import _run_page_pipeline

        doc = pymupdf.open()
        self.addCleanup(doc.close)
        page = doc.new_page(width=612, height=792)
        _paragraph(page, 90, 3)
        page.insert_image(pymupdf.Rect(72, 120, 540, 420), stream=_png_with_white_margin(936, 600, (216, 100, 716, 440)))
        page.insert_text((72, 440), "Figure 1: Response of the sensor array under load.", fontsize=BODY)
        # Also draw a vector plot below so we can verify Phase 3 is skipped when expired before Phase 2 trim.
        page.draw_rect(pymupdf.Rect(100, 500, 340, 640), color=(0, 0, 0), width=1.0)

        ticks = iter([0.0, 31.0])
        cur_t = [0.0]

        def fake_clock() -> float:
            try:
                cur_t[0] = next(ticks)
            except StopIteration:
                pass
            return cur_t[0]

        with mock.patch.object(page, "cluster_drawings", side_effect=AssertionError("must skip cluster_drawings")):
            ctx, cands, _ = _run_page_pipeline(page, cfg=DetectorConfig(max_page_seconds=30.0), clock=fake_clock)

        self.assertTrue(ctx.timed_out)
        self.assertIn("budget:skip raster_trim", ctx.trace)
        self.assertIn("budget:skip vector_phase", ctx.trace)
        self.assertEqual(len(cands), 1, cands)
        self.assertAlmostEqual(cands[0].rect.y0, 120.0, delta=1.5, msg="untrimmed raster placement box must be preserved")

    def test_timeout_before_phase3b_keeps_main_figure_and_skips_small_rescue(self) -> None:
        from figure_detector.model import DetectorConfig
        from figure_detector.pipeline import _run_page_pipeline

        page = TestSmallVectorRescue()._page()
        now = [0.0]

        def clock() -> float:
            return now[0]

        orig_rescue = fd.vector.rescue_small_vector_pieces

        def expire_at_phase3b(*args, **kwargs):
            now[0] = 35.0
            return orig_rescue(*args, **kwargs)

        from unittest import mock

        import figure_detector.pipeline as pipe

        with mock.patch.object(pipe, "rescue_small_vector_pieces", side_effect=expire_at_phase3b):
            ctx, cands, _ = _run_page_pipeline(page, cfg=DetectorConfig(max_page_seconds=30.0), clock=clock)

        self.assertTrue(ctx.timed_out)
        self.assertIn("budget:skip rescue_small", ctx.trace)
        self.assertEqual(len(cands), 1, cands)
        self.assertLess(cands[0].rect.x1, 290, "left main plot kept, Phase 3b cell panel skipped on timeout")

    def test_timeout_before_label_lines_still_attaches_labels_without_find_tables(self) -> None:
        from unittest import mock

        import figure_detector.pipeline as pipe
        from figure_detector.model import DetectorConfig
        from figure_detector.pipeline import _run_page_pipeline

        page, frame = TestAxisLabelLineAttachment()._plot_page()
        head_rect = pymupdf.Rect(170, 200, 470, 214)  # running head overlapping top of figure frame
        now = [0.0]
        orig_attach = pipe._attach_adjacent_label_lines

        def expire_at_labels(*args, **kwargs):
            now[0] = 35.0
            return orig_attach(*args, **kwargs)

        with (
            mock.patch.object(pipe, "_attach_adjacent_label_lines", side_effect=expire_at_labels),
            mock.patch.object(page, "find_tables", side_effect=AssertionError("find_tables must not run after timeout")),
        ):
            ctx, cands, _ = _run_page_pipeline(
                page,
                cfg=DetectorConfig(max_page_seconds=30.0),
                running_heads=[head_rect],
                clock=lambda: now[0],
            )

        self.assertTrue(ctx.timed_out)
        self.assertIn("budget:skip find_tables", ctx.trace)
        self.assertTrue(any(t.startswith("labels:attach_lines") for t in ctx.trace), "cheap label pass must still run")
        self.assertEqual(len(cands), 1, cands)
        self.assertGreaterEqual(cands[0].rect.y0, head_rect.y1 + 4.0, "running heads must still be cleared after timeout")

    def test_timeout_after_clustering_still_judges_the_clusters(self) -> None:
        from figure_detector.model import DetectorConfig
        from figure_detector.pipeline import _run_page_pipeline

        page = TestSmallVectorRescue()._page()
        now = [0.0]
        orig_cluster = page.cluster_drawings

        def slow_cluster(*args, **kwargs):
            out = orig_cluster(*args, **kwargs)
            now[0] = 35.0  # clustering used up the budget
            return out

        page.cluster_drawings = slow_cluster
        ctx, cands, _ = _run_page_pipeline(page, cfg=DetectorConfig(max_page_seconds=30.0), clock=lambda: now[0])
        _, ref, _ = _run_page_pipeline(TestSmallVectorRescue()._page(), cfg=DetectorConfig(small_rescue_gap=0.0))

        self.assertTrue(ctx.timed_out)
        self.assertTrue(any(t.startswith("budget:late_clusters") for t in ctx.trace), ctx.trace)
        self.assertEqual(len(cands), 1, "the plot found by clustering must not be dropped")
        self.assertEqual(tuple(round(v, 1) for v in cands[0].rect), tuple(round(v, 1) for v in ref[0].rect),
                         "same box as an unhurried run without the small-piece rescue (skipped after timeout)")

    def test_extract_images_warns_to_stderr_on_timeout_and_keeps_valid_outputs(self) -> None:
        import io
        import json
        import shutil
        import tempfile
        from contextlib import redirect_stderr, redirect_stdout
        from unittest import mock

        import figure_detector.pipeline as pipe
        from figure_detector.extract import extract_images
        from figure_detector.model import DetectorConfig

        tmp = Path(tempfile.mkdtemp(prefix="luka_budget_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        pdf_path = tmp / "sample.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_image(pymupdf.Rect(100, 120, 420, 360), stream=_blue_png(320, 240))
        page.insert_text((100, 380), "Figure 1: Sample raster figure.", fontsize=BODY)
        doc.save(pdf_path)
        doc.close()

        orig_run = pipe._run_page_pipeline

        def timed_out_pipeline(p, cfg=DetectorConfig(), running_heads=None):
            ticks = iter([0.0, 31.0])
            cur = [0.0]

            def clk() -> float:
                try:
                    cur[0] = next(ticks)
                except StopIteration:
                    pass
                return cur[0]

            return orig_run(p, cfg=cfg, running_heads=running_heads, clock=clk)

        out_dir = tmp / "out"
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with (
            mock.patch("figure_detector.extract._run_page_pipeline", side_effect=timed_out_pipeline),
            redirect_stdout(out_buf),
            redirect_stderr(err_buf),
        ):
            saved = extract_images(pdf_path, out_dir, dpi=72, write_meta=True, stdout_meta=True)

        self.assertEqual(len(saved), 1)
        self.assertIn("WARNING: Page 1 exceeded 30s detection budget", err_buf.getvalue())
        self.assertIn("=== MANIFEST JSON START ===", out_buf.getvalue())
        meta = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["figures"]), 1)


if __name__ == "__main__":
    unittest.main()
