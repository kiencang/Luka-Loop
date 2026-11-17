"""Unit & integration tests for tools/src/extract_assets.py (dev-only; uses Python stdlib unittest)."""

from __future__ import annotations

import json
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
        self.assertEqual(len(meta["figures"]), 2)
        self.assertTrue(meta["figures"][0]["caption"].startswith("Figure 1:"))
        self.assertTrue(meta["figures"][1]["caption"].startswith("Figure 2:"))
        for fig in meta["figures"]:
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
        self.assertTrue(meta["figures"][0]["caption"].startswith("Fig. S1:"))

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


if __name__ == "__main__":
    unittest.main()
