#!/usr/bin/env python3
"""Self-test for score.py.

Builds small synthetic predicted + ground-truth annotation dicts in a temp dir
and asserts the resulting detection/localization/caption/error-taxonomy metrics
come out as expected. Run:

    python3 scripts/test_score.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import score  # noqa: E402


def rect(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


def make_doc(figures, page_w=1000, page_h=1000, page_num=1):
    return {
        "schemaVersion": 2,
        "project": "t", "article": "a", "exportedAt": "now",
        "pages": [{"pageNum": page_num, "width": page_w, "height": page_h}],
        "figures": figures,
    }


class PureFunctionTests(unittest.TestCase):
    def test_iou_perfect(self):
        r = rect(0, 0, 10, 10)
        self.assertAlmostEqual(score.iou(r, dict(r)), 1.0)

    def test_iou_disjoint(self):
        self.assertEqual(score.iou(rect(0, 0, 1, 1), rect(5, 5, 1, 1)), 0.0)

    def test_iou_half(self):
        # 10x10 vs 10x10 shifted by 5 in x -> inter=5*10=50, union=200-50=150
        got = score.iou(rect(0, 0, 10, 10), rect(5, 0, 10, 10))
        self.assertAlmostEqual(got, 50.0 / 150.0)

    def test_edit_distance(self):
        self.assertEqual(score.edit_distance("kitten", "sitting"), 3)
        self.assertEqual(score.edit_distance("", "abc"), 3)
        self.assertEqual(score.edit_distance("abc", "abc"), 0)

    def test_levenshtein_similarity_empty(self):
        self.assertEqual(score.levenshtein_similarity("", ""), 1.0)

    def test_token_set_f1(self):
        self.assertAlmostEqual(score.token_set_f1("a b c", "a b c"), 1.0)
        self.assertAlmostEqual(score.token_set_f1("a b", "c d"), 0.0)

    def test_label_prefix_strip(self):
        self.assertTrue(score.label_exact_match("Figure 2", "Fig. 2"))
        self.assertTrue(score.label_exact_match("Figure 2a", "Fig 2a"))
        self.assertFalse(score.label_exact_match("Figure 2", "Figure 3"))

    def test_greedy_match_prefers_higher_iou(self):
        preds = [rect(0, 0, 10, 10)]
        gts = [rect(5, 0, 10, 10), rect(0, 0, 10, 10)]  # gt[1] is perfect
        m, up, ug, _ = score.greedy_match(preds, gts, 0.5)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0][1], 1)  # matched to the perfect GT box


class ScoringScenarioTests(unittest.TestCase):
    """One combined article exercising all required scenarios.

    GT figures (page 1000x1000):
      G1 (0,0,100,100)     -> perfectly matched by P1                (TP)
      G2 (500,0,100,100)   -> mislocated by P2 (IoU in (0, 0.5))     (mislocated)
      G3 (0,500,100,100)   -> subfigure-count mismatch via P3        (TP, count)
      G4 (500,500,100,100) -> caption differs (P4)                   (TP, cap-miss)
      G5 (800,800,100,100) -> no prediction                          (FN)
    Predicted:
      P1 == G1 (perfect, matching caption)
      P2 shifted from G2 (small overlap, below 0.5)                  (mislocated pair)
      P3 == G3 but with 1 subfigure vs GT 2                          (count mismatch)
      P4 == G4 but totally different caption                         (caption miss)
      P6 (200,800,100,100) spurious, overlaps nothing               (FP)
    """

    def _build(self):
        gt_figs = [
            {"id": "g1", "label": "Figure 1", "pageNum": 1,
             "bounds": rect(0, 0, 100, 100), "caption": "Figure 1. Alpha beta gamma.",
             "subfigures": []},
            {"id": "g2", "label": "Figure 2", "pageNum": 1,
             "bounds": rect(500, 0, 100, 100), "caption": "Figure 2. Delta.",
             "subfigures": []},
            {"id": "g3", "label": "Figure 3", "pageNum": 1,
             "bounds": rect(0, 500, 100, 100), "caption": "Figure 3. Epsilon.",
             "subfigures": [
                 {"id": "g3s1", "label": "Figure 3a", "bounds": rect(0, 0, 50, 100),
                  "caption": "panel a"},
                 {"id": "g3s2", "label": "Figure 3b", "bounds": rect(50, 0, 50, 100),
                  "caption": "panel b"},
             ]},
            {"id": "g4", "label": "Figure 4", "pageNum": 1,
             "bounds": rect(500, 500, 100, 100),
             "caption": "Figure 4. The quick brown fox jumps over the lazy dog.",
             "subfigures": []},
            {"id": "g5", "label": "Figure 5", "pageNum": 1,
             "bounds": rect(800, 800, 100, 100), "caption": "Figure 5. Zeta.",
             "subfigures": []},
        ]
        pred_figs = [
            {"id": "p1", "label": "Figure 1", "pageNum": 1,
             "bounds": rect(0, 0, 100, 100), "caption": "Figure 1. Alpha beta gamma.",
             "subfigures": []},
            # Shift by 60 px: inter=40*100=4000, union=20000-4000=16000 -> IoU=0.25
            {"id": "p2", "label": "Figure 2", "pageNum": 1,
             "bounds": rect(560, 0, 100, 100), "caption": "Figure 2. Delta.",
             "subfigures": []},
            {"id": "p3", "label": "Figure 3", "pageNum": 1,
             "bounds": rect(0, 500, 100, 100), "caption": "Figure 3. Epsilon.",
             "subfigures": [
                 {"id": "p3s1", "label": "Figure 3a", "bounds": rect(0, 0, 100, 100),
                  "caption": "panel a"},
             ]},
            {"id": "p4", "label": "Figure 4", "pageNum": 1,
             "bounds": rect(500, 500, 100, 100),
             "caption": "completely unrelated wording here nothing shared",
             "subfigures": []},
            {"id": "p6", "label": "Figure 9", "pageNum": 1,
             "bounds": rect(200, 800, 100, 100), "caption": "Figure 9. Spurious.",
             "subfigures": []},
        ]
        pred = score.normalize_document(make_doc(pred_figs))
        gt = score.normalize_document(make_doc(gt_figs))
        return pred, gt

    def test_detection_counts(self):
        pred, gt = self._build()
        res = score.score_article(pred, gt, 0.5)
        d = res["detection"]["iou@0.5"]
        # TP: G1, G3, G4 (P2 mislocated does not count; P6 spurious). = 3
        self.assertEqual(d["tp"], 3)
        # FP: P2 (below threshold, unmatched) + P6 = 2
        self.assertEqual(d["fp"], 2)
        # FN: G2 (mislocated, unmatched) + G5 = 2
        self.assertEqual(d["fn"], 2)
        self.assertAlmostEqual(d["precision"], 3.0 / 5.0)
        self.assertAlmostEqual(d["recall"], 3.0 / 5.0)
        self.assertAlmostEqual(d["f1"], 0.6)

    def test_localization(self):
        pred, gt = self._build()
        res = score.score_article(pred, gt, 0.5)
        # Matched pairs G1/G3/G4 are all perfect -> mean IoU 1.0
        self.assertAlmostEqual(res["localization"]["meanIoU"], 1.0)
        self.assertEqual(res["localization"]["matchedPairs"], 3)

    def test_subfigure_count(self):
        pred, gt = self._build()
        res = score.score_article(pred, gt, 0.5)
        sc = res["subfigureCount"]
        # 3 matched figs; G3 has count mismatch (1 vs 2) -> 2/3 exact.
        self.assertEqual(sc["matchedFigures"], 3)
        self.assertAlmostEqual(sc["exactMatchRate"], 2.0 / 3.0)
        # abs errors: 0 (G1), 1 (G3), 0 (G4) -> mean 1/3
        self.assertAlmostEqual(sc["meanAbsError"], 1.0 / 3.0)

    def test_caption(self):
        pred, gt = self._build()
        res = score.score_article(pred, gt, 0.5)
        cap = res["caption"]["figures"]
        self.assertEqual(cap["count"], 3)
        # Label exact match rate should be 1.0 (G1/G3/G4 labels all match).
        self.assertAlmostEqual(res["caption"]["figureLabelExactRate"], 1.0)
        # Mean levenshtein should be below 1 because G4 caption differs badly.
        self.assertLess(cap["levenshtein"], 1.0)

    def test_error_taxonomy(self):
        pred, gt = self._build()
        res = score.score_article(pred, gt, 0.5)
        tax = res["errorTaxonomy"]
        self.assertEqual(tax["missed-figure"], 2)      # G2, G5
        self.assertEqual(tax["spurious-figure"], 2)    # P2, P6
        self.assertEqual(tax["mislocated"], 1)         # P2/G2 overlap 0.25
        self.assertEqual(tax["subfigure-count-mismatch"], 1)  # G3
        self.assertEqual(tax["caption-miss"], 1)       # G4

    def test_p2_iou_is_below_threshold(self):
        # Sanity: confirm the mislocated box sits in (0, 0.5).
        got = score.iou(rect(560, 0, 100, 100), rect(500, 0, 100, 100))
        self.assertAlmostEqual(got, 0.25)
        self.assertTrue(0 < got < 0.5)


class BoundsNormAndLegacyTests(unittest.TestCase):
    def test_boundsnorm_preferred(self):
        figs = [{"id": "f1", "label": "Figure 1", "pageNum": 1,
                 "bounds": rect(0, 0, 100, 100),
                 "boundsNorm": rect(0.5, 0.5, 0.25, 0.25),
                 "caption": "", "subfigures": []}]
        norm = score.normalize_document(make_doc(figs))
        self.assertAlmostEqual(norm[0]["norm"]["x"], 0.5)
        self.assertAlmostEqual(norm[0]["norm"]["width"], 0.25)

    def test_legacy_page_key(self):
        # Uses 'page' instead of 'pageNum', no boundsNorm, no caption.
        doc = {
            "schemaVersion": 1,
            "pages": [{"page": 3, "width": 200, "height": 400}],
            "figures": [{"id": "f1", "label": "Figure 1", "page": 3,
                         "bounds": rect(50, 100, 100, 200), "subfigures": []}],
        }
        norm = score.normalize_document(doc)
        self.assertEqual(norm[0]["pageNum"], 3)
        self.assertAlmostEqual(norm[0]["norm"]["x"], 0.25)
        self.assertAlmostEqual(norm[0]["norm"]["height"], 0.5)
        self.assertEqual(norm[0]["caption"], "")

    def test_unresolvable_figure_skipped(self):
        # No boundsNorm, no page dims -> skipped with warning.
        doc = {"figures": [{"id": "f1", "pageNum": 9,
                            "bounds": rect(0, 0, 10, 10), "subfigures": []}]}
        warnings = []
        norm = score.normalize_document(doc, warnings=warnings)
        self.assertEqual(len(norm), 0)
        self.assertEqual(len(warnings), 1)


class EndToEndFileTests(unittest.TestCase):
    def test_score_and_aggregate_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            adir = Path(tmp) / "article01"
            adir.mkdir()
            gt = make_doc([{"id": "g1", "label": "Figure 1", "pageNum": 1,
                            "bounds": rect(0, 0, 100, 100),
                            "caption": "Figure 1. X.", "subfigures": []}])
            pred = make_doc([{"id": "p1", "label": "Figure 1", "pageNum": 1,
                              "bounds": rect(0, 0, 100, 100),
                              "caption": "Figure 1. X.", "subfigures": []}])
            (adir / "ground-truth.json").write_text(json.dumps(gt))
            (adir / "annotations.json").write_text(json.dumps(pred))

            pred_figs, gt_figs, warns = score.load_article(adir)
            res = score.score_article(pred_figs, gt_figs, 0.5)
            self.assertEqual(res["detection"]["iou@0.5"]["f1"], 1.0)

            agg = score.aggregate([res])
            self.assertAlmostEqual(agg["macroF1"], 1.0)
            self.assertAlmostEqual(agg["microF1"], 1.0)

            # discover_articles sees it as having both.
            found = score.discover_articles(tmp)
            self.assertEqual(len(found), 1)
            self.assertTrue(found[0][2] and found[0][3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
