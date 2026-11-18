"""Unit & integration tests for tools/src/extract_assets.py (dev-only; uses Python stdlib unittest)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "tools" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import extract_assets as ea  # noqa: E402
import html_packager_core as hpc  # noqa: E402
import path_guards as pg  # noqa: E402


class TestExtractAssetsTextAndClassification(unittest.TestCase):
    def test_clean_text_normalizes_whitespace_and_ligatures(self) -> None:
        raw = "  eﬀect\ncoeﬃcient\tshuﬄe  ﬁle\r\nﬂow  "
        self.assertEqual(ea._clean_text(raw), "effect coefficient shuffle file flow")

    def test_caption_classification_cases(self) -> None:
        cases = [
            ("Figure 1: Overview", "fig_caption"),
            ("Fig.1a. Overview", "fig_caption"),
            ("Fig. S1: Supplementary arch", "fig_caption"),
            ("Figure A.2 — Pipeline", "fig_caption"),
            ("Supplementary Figure 3: Detail", "fig_caption"),
            ("Extended Data Fig. 4. Results", "fig_caption"),
            ("Appendix Figure A1: Layout", "fig_caption"),
            ("Figure II: Comparison", "fig_caption"),
            ("Figure 1 Overview of architecture", "fig_caption"),
            ("Figure 1: Shows that our model improves accuracy.", "fig_caption"),
            ("Hình 1: Mô hình tổng quan", "fig_caption"),
            ("Sơ đồ 2.1: Quy trình xử lý", "fig_caption"),
            ("Biểu đồ 3. Kết quả thực nghiệm", "fig_caption"),
            ("Table 1: Summary", "tab_caption"),
            ("Table S2. Metrics", "tab_caption"),
            ("Tab. 3 — Ablation", "tab_caption"),
            ("Bảng 1: Số liệu đo", "tab_caption"),
            ("Bảng II: Tham số", "tab_caption"),
            # Prose traps that must remain regular text
            ("Figures in the report indicate growth.", "text"),
            ("Figure values are shown below.", "text"),
            ("Figure 1 shows that our model improves accuracy.", "text"),
            ("Figure 1b illustrates the flow.", "text"),
            ("Table 2 summarizes the evaluation results.", "text"),
            ("Table variables represent inputs.", "text"),
            ("Hình vẽ minh họa bên dưới mô tả quy trình.", "text"),
            ("Bảng dưới đây liệt kê các tham số.", "text"),
            ("Figure in section 2", "text"),
            ("Figure In section 2", "text"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(ea._classify_text_block(text), expected)


class TestExtractAssetsPdfExtraction(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="luka_py_unit_"))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_flowchart_connectors_xy_axes_tables_and_prose_rejection(self) -> None:
        pdf_path = self.tmp_dir / "flowchart_axes_tables.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page(width=595, height=842)
            # 12-box flowchart connected solely by horizontal/vertical lines (96 words)
            for i in range(12):
                row, col = divmod(i, 3)
                x0, y0 = 60 + col * 160, 80 + row * 70
                box = pymupdf.Rect(x0, y0, x0 + 140, y0 + 50)
                page.draw_rect(box, color=(0, 0, 0), width=1.0)
                if col < 2:
                    page.draw_line((x0 + 140, y0 + 25), (x0 + 160, y0 + 25), color=(0, 0, 0), width=1.0)
                if row < 3:
                    page.draw_line((x0 + 70, y0 + 50), (x0 + 70, y0 + 70), color=(0, 0, 0), width=1.0)
                page.insert_textbox(box, f"Node {i+1} stage step alpha beta gamma delta", fontsize=8)
            page.insert_text((60, 375), "Figure 1: Flowchart connected by straight lines", fontsize=10)

            # Pure vector X/Y axis bar chart
            page.draw_line((80, 420), (80, 540), color=(0, 0, 0), width=1.2)
            page.draw_line((80, 540), (300, 540), color=(0, 0, 0), width=1.2)
            page.draw_rect(pymupdf.Rect(110, 480, 140, 540), color=(0, 0, 0), fill=(0.2, 0.5, 0.8))
            page.draw_rect(pymupdf.Rect(160, 440, 190, 540), color=(0, 0, 0), fill=(0.2, 0.5, 0.8))
            page.insert_text((80, 562), "Figure 2: Vector bar chart with X/Y axes", fontsize=10)

            # Underline + full-width divider rule (must be ignored)
            page.insert_text((80, 610), "Regular underlined heading", fontsize=11)
            page.draw_line((80, 613), (260, 613), color=(0, 0, 0), width=0.8)
            page.draw_line((60, 640), (520, 640), color=(0, 0, 0), width=1.0)

            # Page 2: real 3x2 tables (captioned + uncaptioned) & prose callout box (all must be rejected)
            p2 = doc.new_page(width=595, height=842)
            p2.insert_text((60, 65), "Table 1: Experimental metrics across baselines", fontsize=10)
            for row in range(3):
                for col in range(2):
                    cell = pymupdf.Rect(60 + col * 140, 80 + row * 35, 200 + col * 140, 115 + row * 35)
                    p2.draw_rect(cell, color=(0, 0, 0), width=0.8)
                    p2.insert_textbox(cell, f"Metric row {row} col {col} value 12.3", fontsize=9)

            for row in range(3):
                for col in range(2):
                    cell = pymupdf.Rect(60 + col * 140, 220 + row * 35, 200 + col * 140, 255 + row * 35)
                    p2.draw_rect(cell, color=(0, 0, 0), width=0.8)
                    p2.insert_textbox(cell, f"Uncaptioned row {row} col {col} value 45.6", fontsize=9)

            p2.draw_rect(pymupdf.Rect(60, 360, 520, 530), color=(0.2, 0.2, 0.2), width=1.2)
            p2.insert_textbox(
                pymupdf.Rect(75, 370, 505, 440),
                "This is a standard prose paragraph explaining methodology details in complete sentences with enough words to exceed twelve words easily.",
                fontsize=10,
            )
            p2.insert_textbox(
                pymupdf.Rect(75, 450, 505, 520),
                "Here is a second long prose paragraph inside the same framed box so it must be rejected as text prose rather than a diagram.",
                fontsize=10,
            )
            doc.save(pdf_path)

        out_dir = self.tmp_dir / "out"
        ea.extract_images(pdf_path, out_dir, dpi=150, write_meta=True)
        meta = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["dpi"], 150)
        self.assertEqual(len(meta["figures"]), 2)
        self.assertTrue(meta["figures"][0]["caption"].startswith("Figure 1:"))
        self.assertTrue(meta["figures"][1]["caption"].startswith("Figure 2:"))
        for fig in meta["figures"]:
            self.assertEqual(fig["source"], "vector")
            self.assertGreater(fig["drawings"], 0)
            self.assertEqual(fig["placement"], "figure")
            self.assertEqual(len(fig["box"]), 4)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in fig["box"]))
            self.assertLess(fig["box"][0], fig["box"][2])
            self.assertLess(fig["box"][1], fig["box"][3])
            self.assertTrue((out_dir / fig["file"]).is_file())

    def test_cropbox_offset_and_64pt_caption_gap(self) -> None:
        pdf_path = self.tmp_dir / "cropbox_gap.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.set_cropbox(pymupdf.Rect(50, 50, 550, 750))
            page.draw_rect(pymupdf.Rect(100, 100, 300, 220), color=(0, 0, 1), fill=(0.9, 0.95, 1.0))
            # Place caption ~58pt below bottom edge (beyond old 50pt, within 64pt)
            page.insert_text((100, 286), "Fig. S1: Cropped page with subpanel gap", fontsize=10)
            doc.save(pdf_path)

        out_dir = self.tmp_dir / "out_crop"
        ea.extract_images(pdf_path, out_dir, dpi=150, write_meta=True)
        meta = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["figures"]), 1)
        fig = meta["figures"][0]
        self.assertTrue(fig["caption"].startswith("Fig. S1:"))
        self.assertEqual(fig["box"], [0.2, 0.143, 0.6, 0.314])
        self.assertEqual(fig["source"], "vector")
        self.assertEqual(fig["placement"], "figure")

    def test_raster_hybrid_and_table_cell_manifest_classification(self) -> None:
        pdf_path = self.tmp_dir / "sources_and_table.pdf"
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 60), False)
        pix.clear_with(180)
        with pymupdf.open() as doc:
            p = doc.new_page(width=600, height=800)
            # 1. Framed raster image -> must still be "raster" (drawings=0)
            r1 = pymupdf.Rect(50, 50, 170, 130)
            p.insert_image(r1, pixmap=pix)
            p.draw_rect(r1, color=(0, 0, 0), width=1.0)
            p.insert_text((50, 146), "Figure 1: Framed plain bitmap photo", fontsize=10)

            # 2. Bitmap overlaid with multiple vector arrows/boxes -> "hybrid"
            r2 = pymupdf.Rect(50, 180, 230, 280)
            p.insert_image(r2, pixmap=pix)
            p.draw_rect(pymupdf.Rect(70, 200, 110, 230), color=(1, 0, 0), width=1.2)
            p.draw_line((110, 215), (170, 240), color=(1, 0, 0), width=1.2)
            p.insert_text((50, 296), "Figure 2: Bitmap with vector overlays", fontsize=10)

            # 3. Table with middle-aligned text beside two small row images
            p.insert_text((50, 360), "Table 1: Visual rows", fontsize=10)
            p.insert_image(pymupdf.Rect(50, 380, 110, 440), pixmap=pix)
            p.insert_text((140, 412), "Row alpha sample metric 0.91", fontsize=9)
            p.insert_image(pymupdf.Rect(50, 455, 110, 515), pixmap=pix)
            p.insert_text((140, 487), "Row beta sample metric 0.87", fontsize=9)
            doc.save(pdf_path)

        out_dir = self.tmp_dir / "out_cls"
        ea.extract_images(pdf_path, out_dir, dpi=150, write_meta=True)
        meta = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["figures"]), 4)
        self.assertEqual(meta["figures"][0]["source"], "raster")
        self.assertEqual(meta["figures"][0]["drawings"], 0)
        self.assertEqual(meta["figures"][0]["placement"], "figure")
        self.assertEqual(meta["figures"][1]["source"], "hybrid")
        self.assertGreaterEqual(meta["figures"][1]["drawings"], 2)
        self.assertEqual(meta["figures"][2]["placement"], "table_cell")
        self.assertIn("Row alpha", meta["figures"][2]["context"])
        self.assertEqual(meta["figures"][3]["placement"], "table_cell")
        self.assertIn("Row beta", meta["figures"][3]["context"])

    def test_scanned_page_flag(self) -> None:
        pdf_path = self.tmp_dir / "scanned.pdf"
        # Create a 100x100 RGB pixmap and insert full-page to mimic scanned PDF
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
        pix.clear_with(240)
        with pymupdf.open() as doc:
            page = doc.new_page(width=595, height=842)
            page.insert_image(page.rect, pixmap=pix)
            doc.save(pdf_path)

        out_dir = self.tmp_dir / "out_scan"
        ea.extract_images(pdf_path, out_dir, dpi=120, write_meta=True)
        meta = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["figures"], [])
        self.assertEqual(meta["scanned_pages"], [1])

    def test_validation_and_utf8_cli_output(self) -> None:
        with self.assertRaises(FileNotFoundError):
            ea.extract_images(self.tmp_dir / "does_not_exist.pdf", self.tmp_dir / "o")

        enc_pdf = self.tmp_dir / "locked.pdf"
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), "Secret")
            doc.save(enc_pdf, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="5678")
        with self.assertRaisesRegex(RuntimeError, "password-protected"):
            ea.extract_images(enc_pdf, self.tmp_dir / "enc_out")

        valid_pdf = self.tmp_dir / "Tài liệu UTF8.pdf"
        with pymupdf.open() as doc:
            p = doc.new_page(width=595, height=842)
            p.draw_rect(pymupdf.Rect(80, 80, 240, 180), color=(0, 0, 0))
            doc.save(valid_pdf)
        with self.assertRaises(ValueError):
            ea.extract_images(valid_pdf, self.tmp_dir / "bad_dpi", dpi=10)

        out_utf8 = self.tmp_dir / "Thư mục đầu ra"
        proc = subprocess.run(
            [sys.executable, str(SRC_DIR / "extract_assets.py"), str(valid_pdf), "--out-dir", str(out_utf8), "--meta"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Thư mục đầu ra", proc.stdout)

        proc_bad_dpi = subprocess.run(
            [sys.executable, str(SRC_DIR / "extract_assets.py"), str(valid_pdf), "--out-dir", str(out_utf8), "--dpi", "10"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(proc_bad_dpi.returncode, 0)

    def test_subpanel_labels_stacked_captions_and_single_code_box(self) -> None:
        pdf_path = self.tmp_dir / "stacked_subpanel_codebox.pdf"
        with pymupdf.open() as doc:
            p = doc.new_page(width=595, height=842)
            # 1. Shaded single-rectangle code/callout block with 9 words (<20) -> must be rejected
            code_r = pymupdf.Rect(60, 50, 520, 100)
            p.draw_rect(code_r, color=(0.5, 0.5, 0.5), fill=(0.95, 0.96, 0.98), width=0.8)
            p.insert_textbox(pymupdf.Rect(70, 58, 510, 95), "pattern = ^[ZONE]+$ threshold = 0.85 active true false", fontsize=9)

            # 2. Stacked figures: Fig 1 caption sits just 10pt above Fig 2, while Fig 2 has a 6-word subpanel label before Fig 2 caption
            p.draw_rect(pymupdf.Rect(80, 140, 480, 230), color=(0, 0, 0), fill=(0.9, 0.95, 1.0))
            p.insert_text((80, 248), "Figure 1: Upper diagram caption directly above next panel.", fontsize=10)

            p.draw_rect(pymupdf.Rect(80, 260, 260, 360), color=(0, 0, 0), fill=(0.95, 0.9, 0.9))
            p.draw_rect(pymupdf.Rect(290, 260, 480, 360), color=(0, 0, 0), fill=(0.9, 0.95, 0.9))
            p.insert_text((100, 374), "(a) Left condition view   (b) Right condition view", fontsize=9)
            p.insert_text((80, 392), "Figure 2: Stacked multi-panel figure comparing left and right views below sublabels.", fontsize=10)
            doc.save(pdf_path)

        out_dir = self.tmp_dir / "out_subpanel"
        ea.extract_images(pdf_path, out_dir, dpi=150, write_meta=True)
        meta = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["figures"]), 2)
        self.assertTrue(meta["figures"][0]["caption"].startswith("Figure 1:"))
        self.assertTrue(meta["figures"][1]["caption"].startswith("Figure 2:"))


class TestExtractAssetsFallbackAndOptimizer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="luka_py_img_"))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @staticmethod
    def _make_noisy_rgb_pixmap(w: int, h: int, seed: int = 42) -> pymupdf.Pixmap:
        import random
        rng = random.Random(seed)
        raw = rng.randbytes(w * h * 3)
        return pymupdf.Pixmap(pymupdf.csRGB, w, h, raw, False)

    @staticmethod
    def _make_alpha_pixmap(w: int, h: int) -> pymupdf.Pixmap:
        # Premultiplied RGBA bytes: transparent background + one visible semi-transparent block
        buf = bytearray(w * h * 4)
        for y in range(10, min(h, 30)):
            for x in range(10, min(w, 30)):
                idx = (y * w + x) * 4
                buf[idx : idx + 4] = bytes((5, 9, 14, 120))
        return pymupdf.Pixmap(pymupdf.csRGB, w, h, bytes(buf), True)

    def test_render_pages_filtering_validation_and_cli(self) -> None:
        pdf_path = self.tmp_dir / "multi.pdf"
        with pymupdf.open() as doc:
            for pno in range(1, 5):
                p = doc.new_page(width=400, height=600)
                p.insert_text((60, 120), f"Page {pno}", fontsize=20)
            doc.save(pdf_path)

        out_pages = self.tmp_dir / "pages"
        saved = ea.render_pages(pdf_path, out_pages, scale=1.5, pages="[1, 3-4]")
        self.assertEqual([p.name for p in saved], ["page_1.png", "page_3.png", "page_4.png"])
        self.assertFalse((out_pages / "page_2.png").exists())
        # Page width 400 * 1.5 = 600 -> clamped to minimum 800px
        rendered_p1 = pymupdf.Pixmap(str(out_pages / "page_1.png"))
        self.assertEqual(rendered_p1.width, 800)

        for bad in ("0", "99", "3-1", "abc"):
            with self.assertRaises(ValueError):
                ea.render_pages(pdf_path, out_pages, scale=1.5, pages=bad)

        enc_pdf = self.tmp_dir / "locked_render.pdf"
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), "Locked")
            doc.save(enc_pdf, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="opw")
        with self.assertRaisesRegex(RuntimeError, "password-protected"):
            ea.render_pages(enc_pdf, out_pages)

        cli_pages = self.tmp_dir / "cli_pages"
        proc = subprocess.run(
            [
                sys.executable,
                str(SRC_DIR / "extract_assets.py"),
                "--mode",
                "render-pages",
                str(pdf_path),
                "--out-dir",
                str(cli_pages),
                "--scale",
                "1.2",
                "--pages",
                "2",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((cli_pages / "page_2.png").is_file())
        self.assertFalse((cli_pages / "page_1.png").exists())

    def test_crop_from_json_trim_overwrite_and_validation(self) -> None:
        # 200x200 white canvas with a dark square inside [60..120, 70..130]
        raw = bytearray([255] * (200 * 200 * 3))
        for y in range(70, 130):
            for x in range(60, 120):
                idx = (y * 200 + x) * 3
                raw[idx : idx + 3] = bytes((20, 40, 60))
        src_png = self.tmp_dir / "canvas.png"
        src_png.write_bytes(pymupdf.Pixmap(pymupdf.csRGB, 200, 200, bytes(raw), False).tobytes("png"))

        # Transparent canvas with ink square at [20..50, 20..50]
        a_raw = bytearray(120 * 120 * 4)
        for y in range(20, 50):
            for x in range(20, 50):
                idx = (y * 120 + x) * 4
                a_raw[idx : idx + 4] = bytes((10, 20, 30, 200))
        alpha_png = self.tmp_dir / "alpha_canvas.png"
        alpha_png.write_bytes(pymupdf.Pixmap(pymupdf.csRGB, 120, 120, bytes(a_raw), True).tobytes("png"))

        crops_dir = self.tmp_dir / "crops"
        spec = self.tmp_dir / "crop_spec.json"
        spec.write_text(
            json.dumps(
                [
                    {"page_png": str(src_png), "box": [0.1, 0.1, 0.9, 0.9], "out_name": "trimmed.png", "auto_trim": True},
                    {"page_png": str(src_png), "box": [0.1, 0.1, 0.9, 0.9], "out_name": "raw.png", "auto_trim": False},
                    {"page_png": str(alpha_png), "box": [0.0, 0.0, 1.0, 1.0], "out_name": "alpha_trim.png", "auto_trim": True},
                ]
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(SRC_DIR / "extract_assets.py"),
                "--mode",
                "crop-json",
                "--spec",
                str(spec),
                "--out-dir",
                str(crops_dir),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        p_raw = pymupdf.Pixmap(str(crops_dir / "raw.png"))
        p_trim = pymupdf.Pixmap(str(crops_dir / "trimmed.png"))
        p_alpha = pymupdf.Pixmap(str(crops_dir / "alpha_trim.png"))
        self.assertEqual((p_raw.width, p_raw.height), (160, 160))
        self.assertLess(p_trim.width, 100)
        self.assertLess(p_trim.height, 100)
        self.assertLess(p_alpha.width, 60)
        self.assertTrue(p_alpha.alpha)

        # In-place overwrite without file lock
        ov_spec = self.tmp_dir / "ov.json"
        ov_spec.write_text(
            json.dumps([{"page_png": str(crops_dir / "raw.png"), "box": [0.1, 0.1, 0.9, 0.9], "out_name": "raw.png", "auto_trim": False}]),
            encoding="utf-8",
        )
        ea.crop_from_json(ov_spec, crops_dir)
        self.assertEqual(pymupdf.Pixmap(str(crops_dir / "raw.png")).width, 128)

        # Bad path / box rejections
        bad_name = self.tmp_dir / "bad_name.json"
        bad_name.write_text(json.dumps([{"page_png": str(src_png), "box": [0.1, 0.1, 0.9, 0.9], "out_name": "../x.png"}]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Path traversal blocked"):
            ea.crop_from_json(bad_name, crops_dir)

        bad_box = self.tmp_dir / "bad_box.json"
        bad_box.write_text(json.dumps([{"page_png": str(src_png), "box": [0.6, 0.1, 0.5, 0.9], "out_name": "x.png"}]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid crop box"):
            ea.crop_from_json(bad_box, crops_dir)

    def test_optimize_images_batch_modes_and_cli(self) -> None:
        # 1. Rich noisy photo PNG (300x200) -> resized to 200 & compressed to JPEG
        photo_png = self.tmp_dir / "photo.png"
        photo_png.write_bytes(self._make_noisy_rgb_pixmap(300, 200).tobytes("png"))

        # 2. Transparent RGBA diagram (260x80) -> resized to 200 & kept as PNG with alpha
        alpha_png = self.tmp_dir / "alpha.png"
        alpha_png.write_bytes(self._make_alpha_pixmap(260, 80).tobytes("png"))

        # 3. Simple solid low-color grayscale PNG (60x60) -> kept untouched (out_file=None)
        gray_png = self.tmp_dir / "gray.png"
        gp = pymupdf.Pixmap(pymupdf.csGRAY, pymupdf.IRect(0, 0, 60, 60), False)
        gp.clear_with(220)
        gray_png.write_bytes(gp.tobytes("png"))

        # 4. Opaque CMYK JPEG (260x100) -> converted to RGB safely
        cmyk_jpg = self.tmp_dir / "cmyk.jpg"
        cmyk_buf = bytes([40, 120, 200, 10] * (260 * 100))
        cmyk_pix = pymupdf.Pixmap(pymupdf.csCMYK, 260, 100, cmyk_buf, False)
        cmyk_jpg.write_bytes(pymupdf.Pixmap(pymupdf.csRGB, cmyk_pix).tobytes("jpeg", jpg_quality=95))

        # 5. Opaque noisy RGBA PNG (240x160, alpha=255) -> alpha ignored, compressed to JPEG
        import random
        rng = random.Random(7)
        rgba_raw = bytearray(240 * 160 * 4)
        for i in range(0, len(rgba_raw), 4):
            rgba_raw[i] = rng.randrange(256)
            rgba_raw[i + 1] = rng.randrange(256)
            rgba_raw[i + 2] = rng.randrange(256)
            rgba_raw[i + 3] = 255
        opaque_rgba = self.tmp_dir / "opaque_rgba.png"
        opaque_rgba.write_bytes(pymupdf.Pixmap(pymupdf.csRGB, 240, 160, bytes(rgba_raw), True).tobytes("png"))

        # 6. Wide low-color diagram PNG (600x400 with alternating 2-color vertical stripes) -> resized PNG
        diag_raw = bytearray(600 * 400 * 3)
        for y in range(400):
            row_off = y * 600 * 3
            for x in range(600):
                c = 20 if ((x + y) % 2 == 0) else 235
                diag_raw[row_off + x * 3 : row_off + x * 3 + 3] = bytes((c, c, 240))
        wide_diag = self.tmp_dir / "wide_diag.png"
        wide_diag.write_bytes(pymupdf.Pixmap(pymupdf.csRGB, 600, 400, bytes(diag_raw), False).tobytes("png"))

        spec_path = self.tmp_dir / "opt_spec.json"
        spec_path.write_text(
            json.dumps(
                {
                    "items": [
                        {"path": str(photo_png)},
                        {"path": str(alpha_png)},
                        {"path": str(gray_png)},
                        {"path": str(cmyk_jpg)},
                        {"path": str(opaque_rgba)},
                        {"path": str(wide_diag)},
                    ]
                }
            ),
            encoding="utf-8",
        )
        out_dir = self.tmp_dir / "opt_out"
        out_json = self.tmp_dir / "opt_res.json"

        proc = subprocess.run(
            [
                sys.executable,
                str(SRC_DIR / "extract_assets.py"),
                "--mode",
                "optimize-images",
                "--spec",
                str(spec_path),
                "--out-dir",
                str(out_dir),
                "--out-json",
                str(out_json),
                "--quality",
                "90",
                "--max-width",
                "200",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        res = json.loads(out_json.read_text(encoding="utf-8"))["results"]
        self.assertEqual(len(res), 6)

        # Photo PNG -> JPEG resized to 200px
        self.assertEqual(res[0]["mime"], "image/jpeg")
        self.assertIsNotNone(res[0]["out_file"])
        self.assertEqual(pymupdf.Pixmap(res[0]["out_file"]).width, 200)
        self.assertLess(res[0]["final_len"], res[0]["orig_len"])

        # Transparent PNG -> kept PNG (cannot convert transparent to JPEG)
        self.assertEqual(res[1]["mime"], "image/png")

        # Tiny grayscale PNG -> untouched (out_file is None)
        self.assertEqual(res[2]["mime"], "image/png")
        self.assertIsNone(res[2]["out_file"])

        # CMYK JPEG -> processed safely as JPEG without error
        self.assertEqual(res[3]["mime"], "image/jpeg")

        # Opaque RGBA rich photo -> stripped alpha & compressed to JPEG
        self.assertEqual(res[4]["mime"], "image/jpeg")
        self.assertLess(res[4]["final_len"], res[4]["orig_len"])

        # Wide 2-color diagram PNG -> resized down to 200px & kept lossless PNG
        self.assertEqual(res[5]["mime"], "image/png")
        self.assertIsNotNone(res[5]["out_file"])
        self.assertEqual(pymupdf.Pixmap(res[5]["out_file"]).width, 200)
        self.assertLess(res[5]["final_len"], res[5]["orig_len"])


class TestPathGuardsModule(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_ctx = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp_ctx.name)

    def tearDown(self) -> None:
        self._tmp_ctx.cleanup()

    def test_unc_and_non_fs_paths_blocked(self) -> None:
        for bad in (r"\\server\share\a.pdf", "//host/share/b.png", r"FileSystem::\\srv\s"):
            with self.assertRaisesRegex(ValueError, "Refusing UNC"):
                pg.assert_local_no_unc_path(bad, "-PdfPath")
        with self.assertRaisesRegex(ValueError, "non-filesystem"):
            pg.assert_safe_output_path(r"HKLM:\Software\Test", "OutDir", is_directory=True)

    def test_reparse_junction_detected_and_blocked(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows junction test requires win32")
        target = self.tmp_dir / "real_target"
        target.mkdir()
        (target / "secret.png").write_bytes(b"png")
        junc = self.tmp_dir / "junc_dir"
        res = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junc), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            self.skipTest(f"mklink /J unavailable: {res.stderr}")
        self.assertTrue(pg.is_reparse_point(junc))
        with self.assertRaisesRegex(ValueError, "symlink/junction"):
            pg.assert_safe_output_path(junc / "out.html", "OutHtmlPath", is_directory=False)
        with self.assertRaisesRegex(ValueError, "symlink/junction"):
            pg.resolve_safe_sub_image_path(self.tmp_dir, "junc_dir/secret.png")

    def test_crop_roots_and_safe_clean_dir(self) -> None:
        allowed_dir = self.tmp_dir / "work" / "pages"
        allowed_dir.mkdir(parents=True)
        img = allowed_dir / "p1.png"
        img.write_bytes(b"png")
        outside = self.tmp_dir / "outside.png"
        outside.write_bytes(b"png")

        roots = [allowed_dir]
        self.assertEqual(pg.resolve_safe_crop_input_file(str(img), roots), img.resolve())
        with self.assertRaisesRegex(ValueError, "outside allowed directories"):
            pg.resolve_safe_crop_input_file(str(outside), roots)
        with self.assertRaisesRegex(ValueError, "Path traversal blocked"):
            pg.resolve_safe_crop_out_file(allowed_dir, "../escape.png")

        work_dir = self.tmp_dir / "work"
        (work_dir / "sub").mkdir(parents=True, exist_ok=True)
        (work_dir / "sub" / "a.txt").write_text("x", encoding="utf-8")
        pg.safe_clean_dir(str(work_dir), repo_root=self.tmp_dir)
        self.assertFalse(work_dir.exists())

        with self.assertRaisesRegex(ValueError, "Refusing to clean unsafe directory"):
            pg.safe_clean_dir(str(self.tmp_dir / "other_named_dir"), repo_root=self.tmp_dir)


class TestHtmlPackagerCoreAndTranscript(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_ctx = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp_ctx.name)

    def tearDown(self) -> None:
        self._tmp_ctx.cleanup()

    def test_find_latest_pdf_in_transcript_and_compacted_manifest(self) -> None:
        p1 = self.tmp_dir / "first.pdf"
        p2 = self.tmp_dir / "tài_liệu_việt.pdf"
        p1.write_bytes(b"%PDF-1.4\n")
        p2.write_bytes(b"%PDF-1.4\n")

        transcript = self.tmp_dir / "transcript.jsonl"
        lines = [
            json.dumps({"type": "ASSISTANT", "media": [{"uri": str(p1), "mime_type": "application/pdf"}]}),
            json.dumps({"type": "USER_INPUT", "media": [{"uri": str(p1), "mime_type": "application/pdf"}]}),
            json.dumps({"type": "USER_INPUT", "media": [{"uri": p2.as_uri(), "mime_type": "application/pdf"}]}),
        ]
        transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
        resolved = hpc.find_latest_pdf_in_transcript(transcript)
        self.assertEqual(resolved, p2.resolve())

        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        meta = {
            "pdf": "sample.pdf",
            "figures": [
                {
                    "file": "fig_1.png",
                    "caption": "One two three four five six seven",
                    "context": None,
                }
            ],
        }
        with redirect_stdout(buf):
            hpc.emit_compacted_manifest_stdout(meta, self.tmp_dir / "manifest.json", max_words=3, max_bytes=4096)
        out_text = buf.getvalue()
        self.assertIn("=== MANIFEST JSON START ===", out_text)
        self.assertIn("One two three...", out_text)

        buf2 = StringIO()
        with redirect_stdout(buf2):
            hpc.emit_compacted_manifest_stdout(meta, self.tmp_dir / "manifest.json", max_words=3, max_bytes=10)
        self.assertIn("Manifest too large for stdout", buf2.getvalue())

    def test_embed_images_in_memory_qa_and_collision_numbering(self) -> None:
        work_dir = self.tmp_dir / "work"
        assets_dir = work_dir / "assets"
        out_dir = self.tmp_dir / "output"
        assets_dir.mkdir(parents=True)
        out_dir.mkdir(parents=True)

        # Create sample PNG and JPEG assets
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 60), False)
        pix.clear_with(200)
        (assets_dir / "fig1.png").write_bytes(pix.tobytes("png"))

        draft = work_dir / "draft.html"
        draft.write_text(
            "<!DOCTYPE html><html lang='vi'><head><meta charset='UTF-8'><title>Test</title></head>"
            "<body><h1 id='top'>Tiêu đề</h1><a href='#top'>Top</a>"
            "<figure><img src='assets/fig1.png' alt='Hình minh họa'></figure>"
            "<div class='table-wrapper'><table><tr><th>Cột</th></tr></table></div></body></html>",
            encoding="utf-8",
        )

        existing = out_dir / "paper_vi.html"
        existing.write_text("old", encoding="utf-8")

        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        prev_cwd = os.getcwd()
        os.chdir(self.tmp_dir)
        try:
            with redirect_stdout(buf):
                res_html, res_pdf = hpc.embed_images_and_package(
                    html_path=draft,
                    optimize_image_bytes_fn=ea._optimize_image_bytes,
                    out_html_path=str(existing),
                    clean_dir="work",
                )
        finally:
            os.chdir(prev_cwd)
        log = buf.getvalue()
        self.assertEqual(res_html.name, "paper_vi_2.html")
        self.assertIsNone(res_pdf)
        self.assertFalse(work_dir.exists())
        self.assertIn("Output collision avoided; auto-numbered ->", log)
        self.assertIn("Injected reader shell -> CSS, Toolbar, Script", log)
        self.assertIn("[QA PASS] Base64 images: 1 | Tables wrapped: 1/1", log)
        packaged = res_html.read_text(encoding="utf-8")
        self.assertIn("data:image/", packaged)
        self.assertIn('data-reader-shell="toolbar"', packaged)


if __name__ == "__main__":
    unittest.main()
