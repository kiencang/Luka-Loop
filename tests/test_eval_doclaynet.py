"""Pure-logic tests for dev/eval_doclaynet.py (stdlib only: no dataset, pyarrow or PyMuPDF needed)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("eval_doclaynet", REPO_ROOT / "dev" / "eval_doclaynet.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


class TestSplitsAndCoordinates(unittest.TestCase):
    def test_holdout_is_deterministic_document_level_and_about_20_percent(self) -> None:
        docs = [f"{1000 + i}.{i * 7 % 9999:04d}.pdf" for i in range(4000)]
        first = [ev.is_holdout(d) for d in docs]
        self.assertEqual(first, [ev.is_holdout(d) for d in docs], "membership must not change between runs")
        share = sum(first) / len(docs)
        self.assertGreater(share, 0.17)
        self.assertLess(share, 0.23)
        self.assertEqual(ev.subset_of("val", docs[0]), "val")
        self.assertEqual(ev.subset_of("test", docs[0]), "test")
        self.assertEqual(ev.subset_of("train", docs[0]), "holdout" if first[0] else "tune")

    def test_coco_boxes_are_scaled_per_axis(self) -> None:
        # 1025 x 1025 stretched image of a 612 x 792 pt page
        box = ev.coco_to_pdf([102.5, 205.0, 512.5, 102.5], 1025, 1025, 612, 792)
        for got, want in zip(box, (61.2, 158.4, 367.2, 237.6)):
            self.assertAlmostEqual(got, want, places=6)


class TestBoxMath(unittest.TestCase):
    def test_iou_and_coverage(self) -> None:
        a, b = (0, 0, 10, 10), (5, 0, 15, 10)
        self.assertAlmostEqual(ev.iou(a, b), 50 / 150)
        self.assertAlmostEqual(ev.coverage(a, b), 0.5)
        self.assertEqual(ev.iou(a, (20, 20, 30, 30)), 0.0)
        self.assertEqual(ev.area((5, 5, 1, 1)), 0.0, "inverted boxes have no area")

    def test_lenient_match_accepts_axis_label_growth_but_not_huge_boxes(self) -> None:
        gt = (100, 100, 200, 200)
        grown = (80, 95, 205, 215)  # covers GT fully, 1.5x its area, IoU 0.67
        self.assertTrue(ev.is_lenient_match(grown, gt))
        wide = (60, 60, 240, 230)  # covers GT fully but 3.06x its area, IoU 0.33
        self.assertFalse(ev.is_strict_match(wide, gt))
        self.assertFalse(ev.is_lenient_match(wide, gt))
        loose = (90, 90, 230, 230)  # covers GT, 1.96x area, IoU 0.51 -> strict too
        self.assertTrue(ev.is_strict_match(loose, gt))

    def test_greedy_match_is_one_to_one(self) -> None:
        preds = [(0, 0, 10, 10), (0, 0, 10, 10)]
        gts = [(0, 0, 10, 10)]
        self.assertEqual(len(ev.greedy_match(preds, gts, ev.is_strict_match)), 1)


class TestEvaluatePage(unittest.TestCase):
    def test_true_positive_and_missed(self) -> None:
        r = ev.evaluate_page([(10, 10, 100, 100)], [(10, 10, 100, 100), (300, 300, 400, 400)], [])
        self.assertEqual((r["tp_strict"], r["tp_lenient"]), (1, 1))
        self.assertEqual(r["gt_outcomes"], {"1": "missed"})
        self.assertEqual(r["pred_outcomes"], {})

    def test_merge_of_two_pictures(self) -> None:
        gts = [(0, 0, 100, 100), (110, 0, 210, 100)]
        r = ev.evaluate_page([(0, 0, 210, 100)], gts, [])
        self.assertEqual(r["tp_lenient"], 0)
        self.assertEqual(r["pred_outcomes"], {"0": "merge"})
        self.assertEqual(r["gt_outcomes"], {"0": "merged", "1": "merged"})

    def test_split_and_fragment(self) -> None:
        gt = [(0, 0, 200, 100)]
        r = ev.evaluate_page([(0, 0, 95, 100), (105, 0, 200, 100)], gt, [])
        self.assertEqual(r["gt_outcomes"], {"0": "split"})
        self.assertEqual(r["pred_outcomes"], {"0": "fragment", "1": "fragment"})

    def test_partial_when_one_prediction_is_too_small(self) -> None:
        r = ev.evaluate_page([(0, 0, 40, 40)], [(0, 0, 200, 200)], [])
        self.assertEqual(r["gt_outcomes"], {"0": "partial"})
        self.assertEqual(r["pred_outcomes"], {"0": "fragment"})

    def test_false_positives_are_attributed_to_the_annotated_class(self) -> None:
        others = [("Table", (0, 0, 300, 100)), ("Formula", (0, 200, 300, 230))]
        preds = [(10, 10, 290, 90), (20, 202, 200, 228), (400, 400, 450, 450)]
        r = ev.evaluate_page(preds, [], others)
        self.assertEqual(r["pred_outcomes"], {"0": "fp_Table", "1": "fp_Formula", "2": "fp_unlabeled"})

    def test_summary_precision_recall(self) -> None:
        page = {
            "preds": [(0, 0, 10, 10), (50, 50, 60, 60)],
            "gts": [(0, 0, 10, 10)],
            "eval": ev.evaluate_page([(0, 0, 10, 10), (50, 50, 60, 60)], [(0, 0, 10, 10)], []),
            "pred_meta": [{"source": "vector", "captioned": True}, {"source": "raster", "captioned": False}],
            "seconds": 0.2,
        }
        s = ev.summarize([page, {"error": "boom", "seconds": 0.0}])
        self.assertEqual(s["pages"], 2)
        self.assertEqual(s["page_errors"], 1)
        self.assertEqual(s["lenient"], {"precision": 0.5, "recall": 1.0, "f1": 0.6667})
        self.assertEqual(s["precision_by_source"]["vector+caption"]["tp"], 1)
        self.assertEqual(s["precision_by_source"]["raster"]["tp"], 0)
        self.assertEqual(s["matched_iou_mean"], 1.0)


if __name__ == "__main__":
    unittest.main()
