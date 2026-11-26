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
from figure_detector.caption_match import _match_caption_scored  # noqa: E402
from figure_detector.model import TextBlock  # noqa: E402

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
        # the main-text guard alone would also stop this crossing: switch it off too to test the gutter rule
        with mock.patch.object(pipe, "_column_gutters", return_value=[]), \
                mock.patch.object(pipe, "_newly_covers_main_text", return_value=None):
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
        # the main-text guard alone would also stop this crossing: switch it off too to test the gutter rule
        with mock.patch.object(pipe, "_column_gutters", return_value=[]), \
                mock.patch.object(pipe, "_newly_covers_main_text", return_value=None):
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


class TestGlyphImageLabels(unittest.TestCase):
    """Old plotting tools draw each tick digit as its own tiny image (DocLayNet 1001.3166, 1002.2663): no text, so
    no label step sees it, and Phase 2 drops each one as too small. Glyph images (<= 12 pt) within 8 pt of the box
    are taken in; farther ones (axis titles), larger images and glyphs inside a paragraph are not."""

    FRAME = pymupdf.Rect(150, 300, 450, 500)

    @classmethod
    def _page(cls) -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 200), False)
        pix.clear_with(150)
        page.insert_image(cls.FRAME, pixmap=pix)
        page.insert_text((150, 560), "Figure 1: Density of states near the Fermi energy.", fontsize=BODY)
        return page

    @staticmethod
    def _glyph(page: pymupdf.Page, rect: pymupdf.Rect) -> None:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 12, 14), False)
        pix.clear_with(0)
        page.insert_image(rect, pixmap=pix)

    def test_tick_glyphs_next_to_the_frame_are_taken(self) -> None:
        self.assertEqual(fd.collect_page_figures(self._page())[0], [self.FRAME])
        page = self._page()  # fresh page: PyMuPDF caches a page's image list after the first read
        for x in (150, 250, 350, 440):  # tick row 5 pt below the frame
            self._glyph(page, pymupdf.Rect(x, 505, x + 6, 512))
        for y in (300, 400, 490):  # tick column 7 pt left of the frame
            self._glyph(page, pymupdf.Rect(137, y, 143, y + 7))
        rects = fd.collect_page_figures(page)[0]
        self.assertEqual(rects, [pymupdf.Rect(137, 300, 450, 512)])

    def test_far_large_or_prose_glyph_images_are_left_out(self) -> None:
        page = self._page()
        self._glyph(page, pymupdf.Rect(290, 515, 296, 522))  # axis title 15 pt below: too far
        self._glyph(page, pymupdf.Rect(455, 380, 475, 395))  # 20 pt wide: not a glyph
        page.insert_textbox(pymupdf.Rect(456, 420, 560, 520), "The inline formula glyph sits in this paragraph of "
                            "body text that runs beside the figure for several lines here.", fontsize=BODY)
        self._glyph(page, pymupdf.Rect(457, 432, 463, 439))  # glyph inside the paragraph, 7 pt from the frame
        self.assertEqual(fd.collect_page_figures(page)[0], [self.FRAME])

    def test_glyph_image_touching_the_caption_is_left_out(self) -> None:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 200), False)
        pix.clear_with(150)
        page.insert_image(self.FRAME, pixmap=pix)
        page.insert_text((156, 518), "FIG. 1: Formation energy versus radius of the nanotubes.", fontsize=BODY)
        self._glyph(page, pymupdf.Rect(144, 506, 151, 513))  # marker glyph beside the caption's first line
        self.assertEqual(fd.collect_page_figures(page)[0], [self.FRAME])


class TestMainTextGuard(unittest.TestCase):
    """Two drawings stacked in the left column share the caption below; the top one runs a little into the right
    column above its body text (Surgical Atlas p248). Merging them made one rectangle that covered the right
    column's paragraphs. A plain text block of >= 40 words is body text: no merge or label step may newly cover it."""

    BODY_TEXT = ("are marked with the electrocautery and a guide pin with an eyelet is inserted through the deep "
                 "anterolateral portal and placed at the center of the anterolateral bundle foot print and drilled "
                 "to exit the opposite cortex and the skin of the thigh while the cannulated reamer follows the pin.")

    @staticmethod
    def _page(body: bool) -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=791)
        for rect, shade in ((pymupdf.Rect(100, 70, 328, 227), 170), (pymupdf.Rect(57, 255, 298, 519), 120)):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, int(rect.width), int(rect.height)), False)
            pix.clear_with(shade)
            page.insert_image(rect, pixmap=pix)
        page.insert_text((57, 548), "Fig. 15.32 Placement of the tunnel for the anterolateral bundle", fontsize=8)
        if body:
            page.insert_textbox(pymupdf.Rect(309, 243, 552, 400), TestMainTextGuard.BODY_TEXT, fontsize=BODY)
        return page

    def test_merge_stops_at_body_text(self) -> None:
        self.assertEqual(fd.collect_page_figures(self._page(False))[0], [pymupdf.Rect(57, 70, 328, 519)],
                         "without body text beside them the two drawings merge")
        page = self._page(True)
        rects = fd.collect_page_figures(page)[0]
        self.assertEqual(sorted(rects, key=lambda r: r.y0), [pymupdf.Rect(100, 70, 328, 227), pymupdf.Rect(57, 255, 298, 519)])
        words = [b for b in page.get_text("blocks") if b[0] > 300 and b[1] > 240]
        self.assertTrue(words and len(words[0][4].split()) >= 40, words)


class TestTopBandLabels(unittest.TestCase):
    """Label lines in the top 10% of a page were always dropped as possible running heads, so a figure set high on
    the page lost the labels above it (Surgical Atlas p34, p370). With the document's running heads known, only the
    lines up to the lowest head are left out."""

    @staticmethod
    def _page() -> tuple[pymupdf.Page, pymupdf.Rect]:
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 38), "Chapter 2: Shoulder Surgery", fontsize=8)  # running head, y 32-40
        page.insert_image(pymupdf.Rect(72, 72, 400, 300), stream=_png_with_white_margin(656, 456, (0, 0, 656, 456)))
        page.insert_text((80, 66), "Type I", fontsize=9)  # label right above the image, inside the top 10% (y < 79)
        page.insert_text((300, 66), "Type II", fontsize=9)
        page.insert_text((72, 318), "Figure 2.1: Different types of acromion morphology.", fontsize=BODY)
        _paragraph(page, 350, 6)
        return page, pymupdf.Rect(72, 31, 200, 41)

    def test_label_above_a_high_figure_is_taken_when_running_heads_are_known(self) -> None:
        from figure_detector.pipeline import _run_page_pipeline

        page, head = self._page()
        _, alone, _ = _run_page_pipeline(page)
        self.assertEqual(len(alone), 1, alone)
        self.assertGreater(alone[0].rect.y0, 66, f"precondition: without heads the top band drops the label: {alone[0].rect}")
        _, cands, _ = _run_page_pipeline(page, running_heads=[head])
        self.assertEqual(len(cands), 1, cands)
        self.assertLessEqual(cands[0].rect.y0, 60, f"label 'Type I' must be inside the image: {cands[0].rect}")
        self.assertGreater(cands[0].rect.y0, 41, f"the running head stays outside: {cands[0].rect}")


class TestRasterTrimLeavesImageCache(unittest.TestCase):
    def test_trimming_a_large_image_does_not_change_it_for_later_readers(self) -> None:
        # Shrinking the decoded image in place changed PyMuPDF's cached copy: a second run on the same document lost
        # the image's xref (digest mismatch) and kept the white margin (found on arXiv 1506.06795 p52).
        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_image(pymupdf.Rect(72, 100, 540, 568), stream=_png_with_white_margin(2000, 2000, (400, 400, 1600, 1600)))
        page.insert_text((72, 590), "Figure 1: Response of the sensor array under load.", fontsize=BODY)
        xref = page.get_images()[0][0]
        first, _ = fd.collect_page_figures(page)
        self.assertEqual(pymupdf.Pixmap(doc, xref).width, 2000, "the document's image must keep its size")
        second, _ = fd.collect_page_figures(page)
        self.assertEqual(len(first), 1, first)
        self.assertLess(first[0].width, 300, f"precondition: the white margin is trimmed: {first[0]}")
        self.assertEqual(first, second)


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
        # the main-text guard alone would also stop this crossing: switch it off too to test the column-edge rule
        with mock.patch.object(pipe, "_column_edges", return_value=[]), \
                mock.patch.object(pipe, "_newly_covers_main_text", return_value=None):
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


class TestShortSideCaptions(unittest.TestCase):
    """One- and two-line side captions beside a figure (Surgical Atlas margin captions)."""

    FIG = pymupdf.Rect(210, 62, 540, 430)

    @staticmethod
    def _cap(x0: float, y0: float, x1: float, y1: float) -> TextBlock:
        return TextBlock(pymupdf.Rect(x0, y0, x1, y1), "Fig. 2.12 Pulling the first button", "fig_caption")

    def _match(self, cap: TextBlock) -> tuple[int | None, str]:
        idx, side, _ = _match_caption_scored(self.FIG, [cap], [cap])
        return idx, side

    def test_one_line_caption_level_with_the_figure_top_is_a_side_caption(self) -> None:
        # 9 pt high caption sharing 8 pt of height with the figure (Surgical Atlas p40): the old 10 pt floor
        # could never be met by a one-line caption.
        self.assertEqual(self._match(self._cap(45, 61, 191, 70)), (0, "side"))

    def test_two_line_caption_rising_above_the_figure_top_is_a_side_caption(self) -> None:
        # 19 pt caption starting 12 pt above the figure: 7 pt shared, above 0.35 x 19 (Surgical Atlas p280)
        self.assertEqual(self._match(self._cap(45, 50, 191, 69)), (0, "side"))

    def test_caption_wholly_above_the_figure_top_is_not_a_side_caption(self) -> None:
        self.assertEqual(self._match(self._cap(45, 50, 191, 61)), (None, ""))

    def test_side_gap_stays_at_35_pt(self) -> None:
        # A wider gap across an empty strip was tried and dropped: in two-column papers it bridged the column
        # gutter (DocLayNet 1001.2505 p2, 1001.0204 p4 split stacked panels).
        self.assertEqual(self._match(self._cap(45, 61, 150, 70)), (None, ""))


class TestPageEdgeTab(unittest.TestCase):
    """A coloured page-number tab bleeding off the top edge was kept as a vector figure when a side caption sat
    just below it: the caption matched the tab as "below" and the real figure beside the caption lost it
    (Surgical Atlas p213, p376). Boxes that bleed off the top or bottom edge and stay in that 10% band are dropped
    before caption linking."""

    @staticmethod
    def _page() -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=791)
        page.draw_rect(pymupdf.Rect(453, 0, 513, 37), color=None, fill=(0.95, 0.88, 0.92))  # folio block
        page.draw_rect(pymupdf.Rect(513, 0, 595, 37), color=None, fill=(0.7, 0.0, 0.45))  # chapter-number block
        page.insert_text((470, 26), "365", fontsize=8)
        page.insert_text((540, 26), "25", fontsize=16, color=(1, 1, 1))
        page.insert_image(pymupdf.Rect(45, 62, 368, 427), stream=_png_with_white_margin(646, 730, (0, 0, 646, 730)))
        page.insert_text((388, 70), "Fig. 25.16 Distraction of the subtalar joint", fontsize=7)
        page.insert_text((388, 79), "with an arthrodesis spreader.", fontsize=7)
        _paragraph(page, 470, 6)
        return page

    def test_tab_is_not_a_figure_and_does_not_take_the_caption(self) -> None:
        from figure_detector import pipeline

        page = self._page()
        orig = pipeline._drop_page_edge_tabs
        pipeline._drop_page_edge_tabs = lambda rects, ctx, cfg=None: rects
        try:
            _, before, _ = pipeline._run_page_pipeline(page)
        finally:
            pipeline._drop_page_edge_tabs = orig
        self.assertTrue(
            any(c.rect.y0 < 1 for c in before), f"precondition: without the rule the tab is a figure: {before}"
        )
        _, cands, _ = pipeline._run_page_pipeline(page)
        self.assertEqual(len(cands), 1, cands)
        self.assertGreater(cands[0].rect.y0, 37, f"the tab stays out: {cands[0].rect}")
        self.assertEqual((cands[0].caption_idx, cands[0].caption_side), (0, "side"))


class TestForeignCaptionBlocksMerge(unittest.TestCase):
    """Two drawings side by side, each with its own caption (Surgical Atlas p157). A label line kept the left drawing
    from matching its caption, so it took the right drawing's caption as a sibling and the two merged into one
    image with Fig. 10.25 inside it. A caption that neither box owns, covered by their union, now blocks both the
    caption propagation and the merge."""

    @staticmethod
    def _page() -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=791)
        page.insert_image(pymupdf.Rect(46, 62, 283, 242), stream=_png_with_white_margin(474, 360, (0, 0, 474, 360)))
        page.insert_image(pymupdf.Rect(298, 62, 539, 306), stream=_png_with_white_margin(482, 488, (0, 0, 482, 488)))
        # body-like line between figure and caption (> 8 words): a short label no longer blocks the match
        page.insert_text((50, 268), "Desinsertion of the Anconeus muscle from the lateral epicondyle area", fontsize=7)
        page.insert_text((46, 287), "Fig. 10.25 Releasing the anconeus from the humerus", fontsize=7)
        page.insert_text((298, 321), "Fig. 10.26 A cortical window through the olecranon fossa", fontsize=7)
        _paragraph(page, 360, 6)
        return page

    def test_figures_with_a_caption_between_them_stay_apart(self) -> None:
        from figure_detector import captions, merge, pipeline

        orig = merge._spans_foreign_caption
        merge._spans_foreign_caption = captions._spans_foreign_caption = lambda *a, **k: False
        try:
            _, before, _ = pipeline._run_page_pipeline(self._page())
        finally:
            merge._spans_foreign_caption = captions._spans_foreign_caption = orig
        self.assertEqual(len(before), 1, f"precondition: without the rule the drawings merge: {before}")

        _, cands, _ = pipeline._run_page_pipeline(self._page())
        self.assertEqual(len(cands), 2, cands)
        left, right = sorted(cands, key=lambda c: c.rect.x0)
        self.assertLess(left.rect.x1, 290, left.rect)
        self.assertGreater(right.rect.x0, 290, right.rect)
        # never Fig. 10.26; the final orphan pass gives it its own Fig. 10.25
        self.assertEqual((left.caption_idx, left.caption_side), (0, "below"), "the left drawing must not borrow Fig. 10.26")
        self.assertEqual((right.caption_idx, right.caption_side), (1, "below"))


class TestClippedDrawings(unittest.TestCase):
    """A plot draws its curve and fit line in full and shows only the part inside a clip (the plot frame). The
    drawn geometry ("ribbon") reached into the text column beside the plot, and the figure box followed it
    (DocLayNet 1001.1751 p1). Drawing boxes are now cut to their clip."""

    FRAME = pymupdf.Rect(320, 100, 520, 250)

    @classmethod
    def _page(cls) -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        for i in range(12):  # left text column, level with the plot
            page.insert_text((72, 110 + i * 13), "The measured response follows the trend here", fontsize=BODY)
        page.insert_text((320, 280), "Figure 1: Response of the sensor array under load.", fontsize=BODY)
        f = cls.FRAME
        ops = [
            "q 0 0 0 RG 1 w",
            f"{f.x0} {842 - f.y1} {f.width} {f.height} re S",  # plot frame
            # curve from far left of the frame, shown only inside it (clip = frame)
            f"q {f.x0} {842 - f.y1} {f.width} {f.height} re W n",
            f"0 0 1 RG {f.x0 - 150} {842 - 130} m {f.x0 + 60} {842 - 200} {f.x0 + 120} {842 - 240} {f.x1} {842 - 245} c S",
            "Q",
            "Q",
        ]
        xref = page.get_contents()[0]
        doc.update_stream(xref, doc.xref_stream(xref) + ("\n" + "\n".join(ops) + "\n").encode())
        return page

    def test_drawing_rect_is_cut_to_its_clip(self) -> None:
        from figure_detector.text import _clipped_drawings

        page = self._page()
        rects = [pymupdf.Rect(d["rect"]) for d in page.get_drawings()]
        self.assertTrue(any(r.x0 < 200 and r.y1 < 300 for r in rects), f"precondition: raw curve reaches left: {rects}")
        drawings = _clipped_drawings(page)
        curve = [d for d in drawings if "unclipped_rect" in d and d["rect"].y1 < 300]
        self.assertEqual(len(curve), 1, drawings)
        self.assertGreaterEqual(curve[0]["rect"].x0, self.FRAME.x0 - 0.5)
        self.assertLess(curve[0]["unclipped_rect"].x0, 200)
        frame = [d for d in drawings if "unclipped_rect" not in d]
        self.assertEqual([d["rect"] for d in frame], [self.FRAME], "the unclipped plot frame stays as drawn")

    def test_figure_box_stays_out_of_the_text_column(self) -> None:
        from figure_detector import pipeline, text

        orig = text._clipped_drawings
        text._clipped_drawings = lambda p: p.get_drawings()
        try:
            _, before, _ = pipeline._run_page_pipeline(self._page())
        finally:
            text._clipped_drawings = orig
        # The drawn curve reaches into the text column: the cluster then reads as a prose box and the figure is lost.
        self.assertFalse(
            any(c.rect.x0 > self.FRAME.x0 - 6 for c in before), f"precondition: the ribbon spoils the figure: {before}"
        )

        _, cands, _ = pipeline._run_page_pipeline(self._page())
        self.assertEqual(len(cands), 1, cands)
        self.assertGreater(cands[0].rect.x0, self.FRAME.x0 - 6, cands[0].rect)
        self.assertEqual(cands[0].caption_side, "below")



class TestOrphanCaptionPair(unittest.TestCase):
    """A side caption level with the figure's bottom but 110 pt away stayed unlinked (Surgical Atlas p109). When a
    page has exactly one uncaptioned figure and one unclaimed caption left, a final pass links them, unless the gap
    exceeds 150 pt or the caption sits next to a figure that already has its own caption (an earlier mislink,
    Surgical Atlas p150, p213). Boxes never change."""

    @staticmethod
    def _page(cap_xy: tuple[float, float], fig: tuple[float, float, float, float]) -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=791)
        page.insert_image(pymupdf.Rect(45, 62, 283, 300), stream=_png_with_white_margin(476, 476, (0, 0, 476, 476)))
        page.insert_text((45, 314), "Fig. 5.1 Schematic representation of microfracture", fontsize=7)
        page.insert_image(pymupdf.Rect(*fig), stream=_png_with_white_margin(480, 360, (0, 0, 480, 360)))
        page.insert_text(cap_xy, "Fig. 5.3 Microfracture of the humeral head", fontsize=7)
        _paragraph(page, 640, 5)
        return page

    def _run(self, cap_xy, fig, pair: bool = True):
        from figure_detector import pipeline

        orig = pipeline._pair_last_orphan_caption
        if not pair:
            pipeline._pair_last_orphan_caption = lambda *a, **k: None
        try:
            _, cands, _ = pipeline._run_page_pipeline(self._page(cap_xy, fig))
        finally:
            pipeline._pair_last_orphan_caption = orig
        return sorted(cands, key=lambda c: c.rect.x0)

    def test_far_side_caption_is_linked(self) -> None:
        fig = (300, 420, 540, 600)
        before = self._run((45, 598), fig, pair=False)
        self.assertEqual([c.caption_idx for c in before], [0, None], f"precondition: the side caption is too far: {before}")
        after = self._run((45, 598), fig)
        self.assertEqual([c.rect for c in after], [c.rect for c in before], "boxes never change")
        self.assertEqual([(c.caption_idx, c.caption_side) for c in after], [(0, "below"), (1, "side")])

    def test_long_caption_stays_unlinked(self) -> None:
        # A "caption" longer than the cap is body text opening with "Figures 5 (a)..." (DocLayNet 1001.1179 p5).
        from dataclasses import replace

        from figure_detector import pipeline
        from figure_detector.model import DEFAULT_CONFIG

        cfg = replace(DEFAULT_CONFIG, orphan_pair_max_caption_lines=0)
        _, cands, _ = pipeline._run_page_pipeline(self._page((45, 598), (300, 420, 540, 600)), cfg=cfg)
        self.assertEqual([c.caption_idx for c in sorted(cands, key=lambda c: c.rect.x0)], [0, None])

    def test_too_far_stays_unlinked(self) -> None:
        cands = self._run((288, 120), (300, 300, 540, 480))  # 178 pt from the figure
        self.assertEqual([c.caption_idx for c in cands], [0, None])

    def test_caption_beside_a_captioned_figure_stays_unlinked(self) -> None:
        cands = self._run((290, 200), (300, 300, 540, 480))  # 7 pt from Fig. 5.1's figure, 98 pt from the free one
        self.assertEqual([c.caption_idx for c in cands], [0, None])


class TestLabelBetweenFigureAndCaption(unittest.TestCase):
    """Text between a figure and its caption blocks the link only when it reads like body text.

    Surgical Atlas p345: a short label under the photo hid the caption below it. The block counts
    visual rows, not PDF lines, so ``−t [GeV²]`` split into four lines is still one row (DocLayNet 1001.1952 p11).
    """

    FIG = pymupdf.Rect(100, 100, 400, 300)
    CAP = TextBlock(pymupdf.Rect(100, 345, 400, 360), "Fig. 3 Dye injected under the nipple", "fig_caption")

    def _match(self, text: str, rows: int = 0) -> int | None:
        label = TextBlock(pymupdf.Rect(150, 305, 350, 337), text, "text", rows=rows)
        idx, _, _ = _match_caption_scored(self.FIG, [self.CAP], [self.CAP, label])
        return idx

    def test_short_two_row_label_does_not_block(self) -> None:
        self.assertEqual(self._match("Areola marked\nwith blue dye here"), 0)

    def test_long_text_still_blocks(self) -> None:
        self.assertIsNone(self._match("The surgeon then marks the areola with blue dye before the first cut"))

    def test_short_table_caption_still_blocks(self) -> None:
        # DocLayNet 1504.02490 p8: "TABLE VI" heading between Fig. 3's caption and the table
        label = TextBlock(pymupdf.Rect(150, 305, 350, 337), "TABLE VI\nQUEUE RANKING STRATEGY COMPARISON", "tab_caption")
        idx, _, _ = _match_caption_scored(self.FIG, [self.CAP], [self.CAP, label])
        self.assertIsNone(idx)

    def test_four_rows_still_block(self) -> None:
        self.assertIsNone(self._match("Areola\nmarked\nwith\nblue dye", rows=4))

    def test_lines_on_one_baseline_count_as_one_row(self) -> None:
        from figure_detector.text import _count_visual_rows

        # "−t", "[GeV", superscript "2", "]": four PDF lines on one band
        rects = [pymupdf.Rect(10, 50, 20, 60), pymupdf.Rect(22, 50, 45, 60), pymupdf.Rect(46, 48, 50, 54),
                 pymupdf.Rect(51, 50, 54, 60)]
        self.assertEqual(_count_visual_rows(rects), 1)
        self.assertEqual(_count_visual_rows(rects + [pymupdf.Rect(10, 70, 40, 80)]), 2)

class TestBulletLinesAreNotLabels(unittest.TestCase):
    """A list bullet next to a figure is running text, not a figure label (Surgical Atlas p144: "-" bullets set at
    40 pt beside a photo pulled the box over the list to its right)."""

    def test_bullets(self) -> None:
        from figure_detector.pipeline import _is_bullet_line

        for ws in (["–"], ["•", "Keep", "the", "arm"], ["▪", "Portal"], ["-"], ["-", "•"]):
            self.assertTrue(_is_bullet_line(ws), ws)
        # a hyphen leading a line may be a minus sign; numbers and letters are not bullets
        for ws in ([], ["-", "0.5"], ["1.", "Step"], ["(a)"], ["a)"], ["Guide", "pin"]):
            self.assertFalse(_is_bullet_line(ws), ws)


class TestSandwichedCaptionMirror(unittest.TestCase):
    """A caption between two stacked figures goes to the upper one when the lower figure wins only narrowly and has
    its own caption under it (Surgical Atlas p150: Fig. 10.11 went to the drawing below, Fig. 10.13 was orphaned)."""

    @staticmethod
    def _caps(gap_upper: float) -> list[int | None]:
        from figure_detector import pipeline

        doc = pymupdf.open()
        page = doc.new_page(width=595, height=791)
        page.insert_image(pymupdf.Rect(100, 60, 400, 260), stream=_png_with_white_margin(600, 400, (0, 0, 600, 400)))
        page.insert_text((100, 267 + gap_upper), "Fig. 1 Lateral portal view of the joint", fontsize=7)
        top = 279 + gap_upper
        page.insert_image(pymupdf.Rect(100, top, 400, top + 180), stream=_png_with_white_margin(600, 360, (0, 0, 600, 360)))
        page.insert_text((100, top + 220), "Fig. 2 Medial portal view of the joint", fontsize=7)
        _paragraph(page, 640, 5)
        _, cands, _ = pipeline._run_page_pipeline(page)
        return [c.caption_idx for c in sorted(cands, key=lambda c: c.rect.y0)]

    def test_upper_figure_keeps_the_caption_under_it(self) -> None:
        # upper gap 39 pt (score 39), lower gap 10 pt above it (score 28), lower's own caption 32 pt below
        self.assertEqual(self._caps(40), [0, 1])

    def test_clear_winner_is_kept(self) -> None:
        # upper gap 69 pt is past the 64 pt reach: the lower figure keeps Fig. 1 as before
        self.assertEqual(self._caps(70), [None, 0])


class TestMaximizeCaptions(unittest.TestCase):
    """The page's only uncaptioned figure takes a neighbour's caption when that neighbour can take the only orphan
    caption instead (Surgical Atlas p213). Boxes never change."""

    @staticmethod
    def _run(side_gap: float, swap: bool = True):
        from figure_detector import pipeline

        doc = pymupdf.open()
        page = doc.new_page(width=595, height=791)
        page.insert_image(pymupdf.Rect(200, 100, 300, 300), stream=_png_with_white_margin(200, 400, (0, 0, 200, 400)))
        orphan = "Fig. 1 Portal placement"
        page.insert_text((190 - pymupdf.get_text_length(orphan, fontsize=7), 106), orphan, fontsize=7)
        given = "Fig. 2 Arthroscopic view of the lesion"
        x1 = 200 + pymupdf.get_text_length(given, fontsize=7)
        page.insert_text((200, 321), given, fontsize=7)  # 13 pt under the left figure
        page.insert_image(pymupdf.Rect(x1 + side_gap, 314, x1 + side_gap + 200, 454),
                          stream=_png_with_white_margin(400, 280, (0, 0, 400, 280)))
        _paragraph(page, 640, 5)
        orig = pipeline._maximize_captions
        if not swap:
            pipeline._maximize_captions = lambda *a, **k: None
        try:
            _, cands, _ = pipeline._run_page_pipeline(page)
        finally:
            pipeline._maximize_captions = orig
        return sorted(cands, key=lambda c: c.rect.x0)

    def test_neighbour_hands_over_its_caption(self) -> None:
        before = self._run(5, swap=False)
        self.assertEqual([c.caption_idx for c in before], [1, None], f"precondition: below beats side: {before}")
        after = self._run(5)
        self.assertEqual([c.rect for c in after], [c.rect for c in before], "boxes never change")
        self.assertEqual([(c.caption_idx, c.caption_side) for c in after], [(0, "side"), (1, "side")])

    def test_caption_nearer_to_its_holder_stays(self) -> None:
        # Fig. 2 is 20 pt from the uncaptioned figure but 13 pt from the figure holding it
        self.assertEqual([c.caption_idx for c in self._run(20)], [1, None])


class TestTickRowLabels(unittest.TestCase):
    """PyMuPDF joins a horizontal row of tick values into one text block; at 12+ words it counted as prose, so the
    "never swallow prose" guard kept it (and the axis title under it) out of the figure (DocLayNet 1001.0805 p5,
    1001.2227 p2, 1101.1893 p17). A row of numbers or words of <= 4 characters, 1-2 rows, under 25 words and within
    5 pt of the box is not prose."""

    @staticmethod
    def _page(row_baseline: float) -> pymupdf.Page:
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=791)
        page.draw_rect(pymupdf.Rect(100, 100, 400, 300), color=(0, 0, 0), width=0.8)
        for k, col in enumerate(((1, 0, 0), (0, 0, 1), (0, 0.6, 0))):
            page.draw_polyline([pymupdf.Point(100 + i * 10, 290 - k * 40 - 60 * abs(i / 30 - 0.5) * (k + 1))
                                for i in range(31)], color=col, width=1)
        for i in range(13):
            page.draw_line((100 + i * 25, 300), (100 + i * 25, 296), color=(0, 0, 0), width=0.6)
        page.insert_text((94, row_baseline), "      ".join(f"{1.6 + 0.2 * i:.1f}" for i in range(13)), fontsize=8)
        page.insert_text((230, row_baseline + 16), "Energy (GeV)", fontsize=9)
        page.insert_text((100, 350), "Fig. 1 Beam asymmetry as a function of the photon energy", fontsize=9)
        _paragraph(page, 420, 6)
        return page

    def _box(self, row_baseline: float, **cfg) -> pymupdf.Rect:
        from dataclasses import replace

        from figure_detector import pipeline
        from figure_detector.model import DEFAULT_CONFIG

        _, cands, _ = pipeline._run_page_pipeline(self._page(row_baseline), cfg=replace(DEFAULT_CONFIG, **cfg))
        self.assertEqual(len(cands), 1)
        return cands[0].rect

    def test_tick_row_and_axis_title_are_attached(self) -> None:
        self.assertLessEqual(self._box(310, label_row_max_gap=-1).y1, 301, "precondition: the row counts as prose")
        self.assertGreaterEqual(self._box(310).y1, 328)  # tick row (1 pt below) and the axis title under it

    def test_row_farther_than_5pt_stays_prose(self) -> None:
        self.assertLessEqual(self._box(316).y1, 301)  # row 7 pt below the plot

    def test_label_row_shapes(self) -> None:
        from figure_detector.pipeline import _is_label_row

        def tb(text: str, rows: int = 1) -> TextBlock:
            return TextBlock(pymupdf.Rect(0, 0, 300, 10), text, "text", rows=rows)

        for text in ("1.6 1.8 2.0 2.2 2.4 2.6 2.8 3.0 3.2 3.4 3.6 3.8 4.0",
                     "Bi Bi Bi Bi Pb Pb Pb Pb Zn Zn Zn Zn Nb Nb Nb Nb",
                     "M=1 N=1 K=L M=1 N=1 K=L M=1 N=1 K=L M=1 N=1 K=L",
                     "10 -9 10 -8 10⁻⁷ 0.001 1e+02 -0.25 5×10³ 45% 12.5° (0.5) 1,000"):
            self.assertTrue(_is_label_row(tb(text)), text)
        for text, rows in (("The measured response follows the expected trend across all sampled operating points", 1),
                           ("1.6 1.8 2.0 2.2 2.4 2.6 2.8 3.0 3.2 3.4 3.6 3.8 4.0", 3),
                           (" ".join(["0.5"] * 25), 1),
                           ("minimum distance of the orbit from the cluster centre", 1)):
            self.assertFalse(_is_label_row(tb(text, rows)), text)


class TestSMaskAndPdfBombLimits(unittest.TestCase):
    """Guard against oversized/mismatched SMask decompression bombs and PDF page-tree / figure-count bombs."""

    def test_oversized_smask_is_rejected_from_xref_headers_without_decoding(self) -> None:
        from unittest import mock

        import figure_detector.raster as raster

        # Create a PDF containing a small RGBA image (creates an Image XObject + SMask XObject).
        rgba = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 80), True)
        rgba.clear_with(255)
        rgba.set_rect(pymupdf.IRect(20, 20, 60, 60), (20, 80, 180, 255))
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=400)
        page.insert_image(pymupdf.Rect(50, 50, 250, 250), stream=rgba.tobytes("png"))
        page.insert_text((50, 270), "Figure 1: Sample with soft mask.", fontsize=BODY)
        buf = doc.tobytes()
        doc.close()

        # 1. Valid matching SMask is accepted and decoded normally.
        with pymupdf.open(stream=buf, filetype="pdf") as clean_doc:
            info = clean_doc[0].get_image_info(xrefs=True)[0]
            sm_xref = int(clean_doc.xref_get_key(info["xref"], "SMask")[1].split()[0])
            self.assertTrue(raster._smask_matches_size(clean_doc, sm_xref, 80, 80, 60_000_000))

        # 2. Tamper the SMask xref header to advertise a 50,000 x 50,000 bomb: Pixmap(doc, sm_xref) must never run.
        with pymupdf.open(stream=buf, filetype="pdf") as bomb_doc:
            info = bomb_doc[0].get_image_info(xrefs=True)[0]
            img_xref = info["xref"]
            sm_xref = int(bomb_doc.xref_get_key(img_xref, "SMask")[1].split()[0])
            bomb_doc.xref_set_key(sm_xref, "Width", "50000")
            bomb_doc.xref_set_key(sm_xref, "Height", "50000")
            self.assertFalse(raster._smask_matches_size(bomb_doc, sm_xref, 80, 80, 60_000_000))

            real_pixmap = pymupdf.Pixmap

            def guarded_pixmap(*args, **kwargs):
                if len(args) >= 2 and args[1] == sm_xref:
                    raise AssertionError("Pixmap must not decode oversized/mismatched SMask xref")
                return real_pixmap(*args, **kwargs)

            fd._ensure_pymupdf()
            with mock.patch.object(raster.pymupdf, "Pixmap", side_effect=guarded_pixmap):
                rects, _ = fd.collect_page_figures(bomb_doc[0])
            self.assertEqual(len(rects), 1)

    def test_page_limit_and_figure_limit_fail_fast_and_allow_dev_zero_override(self) -> None:
        import shutil
        import tempfile
        from unittest import mock

        import figure_detector.extract as ext
        import image_ops as iops

        self.assertEqual(iops.MAX_PDF_PAGES, 300)
        self.assertEqual(iops.MAX_EXTRACTED_FIGURES, 1000)

        tmp = Path(tempfile.mkdtemp(prefix="luka_bomb_"))
        self.addCleanup(shutil.rmtree, tmp, True)

        # Build a 301-page PDF; page 301 has one small raster figure.
        over_pdf = tmp / "p301.pdf"
        doc = pymupdf.open()
        for _ in range(300):
            doc.new_page(width=200, height=200)
        last = doc.new_page(width=300, height=300)
        last.insert_image(pymupdf.Rect(40, 40, 200, 200), stream=_png_with_white_margin(160, 160, (10, 10, 150, 150)))
        last.insert_text((40, 220), "Figure 1: Tail image.", fontsize=BODY)
        doc.save(over_pdf)
        doc.close()

        # 1. Default 300-page limit rejects 301-page PDF before scanning running heads or creating out_dir.
        out_301 = tmp / "out_301"
        with mock.patch.object(ext, "page_edge_lines", side_effect=AssertionError("must reject before scanning pages")):
            with self.assertRaisesRegex(ValueError, "301 pages, exceeding the 300-page safety limit"):
                ext.extract_images(over_pdf, out_301)
        self.assertFalse(out_301.exists(), "rejected PDF must not create output directory")

        pages_301 = tmp / "pages_301"
        with self.assertRaisesRegex(ValueError, "301 pages, exceeding the 300-page safety limit"):
            iops.render_pages(over_pdf, pages_301, pages="1")
        self.assertFalse(pages_301.exists(), "rejected render_pages must not create output directory")

        # Boundary: exactly 300 pages is accepted.
        ok_300 = tmp / "p300.pdf"
        with pymupdf.open(over_pdf) as d:
            d.delete_page(300)
            d.save(ok_300)
        self.assertEqual(ext.extract_images(ok_300, tmp / "out_300"), [])

        # Dev override: max_pages=0 allows > 300-page books.
        dev_saved = ext.extract_images(over_pdf, tmp / "out_dev", dpi=72, max_pages=0)
        self.assertEqual(len(dev_saved), 1)
        self.assertEqual(len(iops.render_pages(over_pdf, tmp / "pages_dev", scale=1.0, pages="301", max_pages=0)), 1)

        # 2. Figure-count limit aborts cleanly, removes partial PNGs & empty created dir, and skips manifest.json.
        many_figs_pdf = tmp / "four_figs.pdf"
        doc2 = pymupdf.open()
        img_bytes = _png_with_white_margin(160, 160, (10, 10, 150, 150))
        for p_idx in range(4):
            pg = doc2.new_page(width=300, height=300)
            pg.insert_image(pymupdf.Rect(40, 40, 200, 200), stream=img_bytes)
            pg.insert_text((40, 220), f"Figure {p_idx + 1}: Repeated image.", fontsize=BODY)
        doc2.save(many_figs_pdf)
        doc2.close()

        capped_out = tmp / "capped_figs"
        with self.assertRaisesRegex(ValueError, "3-figure extraction safety limit"):
            ext.extract_images(many_figs_pdf, capped_out, dpi=72, write_meta=True, max_figures=3)
        self.assertFalse(capped_out.exists(), "partial PNGs and newly created empty directory must be cleaned up")

        # Dev override: max_figures=0 extracts all 4 figures.
        unlimited_out = tmp / "unlimited_figs"
        self.assertEqual(len(ext.extract_images(many_figs_pdf, unlimited_out, dpi=72, max_figures=0)), 4)


if __name__ == "__main__":
    unittest.main()
