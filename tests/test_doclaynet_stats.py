"""Pure helpers of the DocLayNet statistics tools (dev/doclaynet_facts.py, dev/doclaynet_stats.py)."""

import sys
import unittest
from pathlib import Path

DEV = Path(__file__).resolve().parents[1] / "dev"
SRC = Path(__file__).resolve().parents[1] / "tools" / "src"
for p in (DEV, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import doclaynet_facts as F  # noqa: E402
import doclaynet_stats as S  # noqa: E402


class TestAssignGt(unittest.TestCase):
    GT = [{"c": "Text", "r": [0, 0, 100, 20]}, {"c": "Picture", "r": [0, 30, 100, 130]}]

    def test_centre_wins(self):
        self.assertEqual(F.assign_gt([10, 40, 30, 50], self.GT)[:2], ("Picture", 1))

    def test_largest_overlap_when_centre_outside(self):
        cls, gi, share = F.assign_gt([90, 15, 130, 40], self.GT)
        self.assertEqual((cls, gi), ("Picture", 1))
        self.assertLess(share, 0.5)

    def test_none(self):
        self.assertEqual(F.assign_gt([200, 200, 210, 210], self.GT)[:2], ("none", -1))


class TestWidestWordGap(unittest.TestCase):
    @staticmethod
    def w(x0, x1, text, y0=100.0, y1=110.0):
        return (x0, y0, x1, y1, text)

    def test_gap_between_letter_words(self):
        words = [self.w(0, 20, "Time"), self.w(25, 40, "axis"), self.w(140, 170, "Error")]
        self.assertAlmostEqual(F.widest_word_gap(words, []), 100.0)

    def test_drawing_in_gap_hides_it(self):
        words = [self.w(0, 20, "Time"), self.w(140, 170, "Error")]
        self.assertEqual(F.widest_word_gap(words, [(60, 100, 80, 110)]), 0.0)

    def test_numbers_do_not_count(self):
        words = [self.w(0, 20, "0.5"), self.w(140, 170, "1.0")]
        self.assertEqual(F.widest_word_gap(words, []), 0.0)


class TestStatsHelpers(unittest.TestCase):
    def test_quantiles(self):
        q = S.quantiles(range(100))
        self.assertEqual((q["n"], q["p50"], q["p90"], q["max"]), (100, 50, 90, 99))
        self.assertEqual(S.quantiles([]), {"n": 0})

    def test_rect_and_axis_gap(self):
        self.assertAlmostEqual(S.rect_gap([0, 0, 10, 10], [13, 14, 20, 20]), 5.0)
        self.assertEqual(S.axis_gap([0, 0, 10, 10], [13, 14, 20, 20]), 4.0)
        self.assertEqual(S.rect_gap([0, 0, 10, 10], [5, 5, 20, 20]), 0.0)

    def test_side_of(self):
        core = [100, 100, 200, 200]
        self.assertEqual(S.side_of([50, 120, 90, 130], core), "left")
        self.assertEqual(S.side_of([120, 210, 150, 220], core), "bottom")
        self.assertEqual(S.side_of([150, 150, 160, 160], core), "overlap")

    def test_chain_gaps(self):
        core = [0, 0, 100, 100]
        rects = [[0, 110, 10, 120], [0, 130, 10, 140], [0, 150, 10, 160]]
        self.assertEqual(S.chain_gaps(core, rects), [10.0, 10.0, 10.0])
        self.assertEqual([S.rect_gap(r, core) for r in rects], [10.0, 30.0, 50.0])

    def test_components_and_mst(self):
        rects = [[0, 0, 10, 10], [14, 0, 20, 10], [50, 0, 60, 10]]
        groups = sorted(sorted(g) for g in S.components(rects, 5.0))
        self.assertEqual(groups, [[0, 1], [2]])
        self.assertEqual(sorted(S.mst_edges(rects)), [4.0, 30.0])

    def test_within(self):
        self.assertEqual(S.within([1, 2, 3, 10], (2, 5, 10)), [(2, 50.0), (5, 75.0), (10, 100.0)])


if __name__ == "__main__":
    unittest.main()
