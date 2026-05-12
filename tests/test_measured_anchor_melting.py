# -*- coding: utf-8 -*-
"""실측 앵커 Sn88–Ag3.5–Cu0.5–In8 → 고상 198℃, 액상 210℃."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PARENT = ROOT.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.melting_predictor import hybrid_melting_predict


class MeasuredAnchorMeltingTest(unittest.TestCase):
    def test_anchor_nominal_matches_measured(self):
        norm = {"Sn": 88.0, "Ag": 3.5, "Cu": 0.5, "In": 8.0}
        sol, liq, peak, detail = hybrid_melting_predict(norm, [], ai_engine=None)
        self.assertAlmostEqual(sol, 198.0, places=1)
        self.assertAlmostEqual(liq, 210.0, places=1)
        self.assertEqual(detail.get("measured_anchor", {}).get("solidus"), 198.0)
        self.assertEqual(detail.get("measured_anchor", {}).get("liquidus"), 210.0)
        layers = detail.get("layers") or []
        self.assertTrue(any("measured_anchor" in str(x).lower() for x in layers))

    def test_anchor_slight_rounding_still_matches(self):
        norm = {"Sn": 87.98, "Ag": 3.52, "Cu": 0.49, "In": 8.01}
        sol, liq, _, detail = hybrid_melting_predict(norm, [], ai_engine=None)
        self.assertAlmostEqual(sol, 198.0, places=1)
        self.assertAlmostEqual(liq, 210.0, places=1)
        self.assertIsNotNone(detail.get("measured_anchor"))

    def test_db_exact_row_overrides_measured_anchor(self):
        """solder_db와 조성이 정확히 같으면 DB 실측이 기준(문서 앵커보다 우선)."""
        norm = {"Sn": 88.0, "Ag": 3.5, "Cu": 0.5, "In": 8.0}
        db_prepared = [{"name": "Lab_In8_row", "comp": dict(norm), "solidus": 200.0, "liquidus": 212.0}]
        sol, liq, _, detail = hybrid_melting_predict(norm, db_prepared, ai_engine=None)
        self.assertAlmostEqual(sol, 200.0, places=1)
        self.assertAlmostEqual(liq, 212.0, places=1)
        self.assertTrue(detail.get("db_exact_match"))
        self.assertIsNone(detail.get("measured_anchor"))
        layers = detail.get("layers") or []
        self.assertTrue(any("DB_exact" in str(x) for x in layers))


if __name__ == "__main__":
    unittest.main()
