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


if __name__ == "__main__":
    unittest.main()
