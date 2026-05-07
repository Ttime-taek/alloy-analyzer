# -*- coding: utf-8 -*-
"""미지(비핵심) 금속 첨가 시 용융 예측이 실측 앵커·L6로 오도되지 않도록 보정."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.melting_predictor import hybrid_melting_predict


class UnknownMetalsMeltingTest(unittest.TestCase):
    def test_trace_unknown_metal_skips_anchor_and_applies_blend(self):
        """Au 극미량이면 실측 앵커 해제 + 보수 블렌드."""
        norm = {"Sn": 87.95, "Ag": 3.5, "Cu": 0.5, "In": 8.0, "Au": 0.05}
        _, _, _, detail = hybrid_melting_predict(norm, [], ai_engine=None)
        self.assertIsNone(detail.get("measured_anchor"))
        self.assertGreater(detail.get("unknown_noncore_pct", 0), 0)
        self.assertTrue(detail.get("unknown_metals_melting_blend", {}).get("applied"))

    def test_unknown_blend_when_noncore_pct_high(self):
        norm = {"Sn": 82.0, "Ag": 3.5, "Cu": 0.5, "In": 8.0, "Au": 6.0}
        _, _, _, detail = hybrid_melting_predict(norm, [], ai_engine=None)
        self.assertGreaterEqual(detail.get("unknown_noncore_pct", 0), 6.0)
        self.assertTrue(detail.get("unknown_metals_melting_blend", {}).get("applied"))

    def test_unknown_blend_prefers_db_neighbor_core_scaled(self):
        """미지 금속이 있어도 BD 실측 이웃(핵심 조성 재규격화)을 블렌드 기준으로 사용."""
        db = [
            {
                "name": "FarSnAg",
                "comp": {"Sn": 96.5, "Ag": 3.5},
                "solidus": 221.0,
                "liquidus": 221.0,
            },
            {
                "name": "NearSACIn",
                "comp": {"Sn": 88.0, "Ag": 3.5, "Cu": 0.5, "In": 8.0},
                "solidus": 198.0,
                "liquidus": 210.0,
            },
        ]
        norm = {"Sn": 82.0, "Ag": 3.5, "Cu": 0.5, "In": 8.0, "Au": 6.0}
        sol, liq, _, detail = hybrid_melting_predict(norm, db, ai_engine=None)
        ub = detail.get("unknown_metals_melting_blend", {})
        self.assertTrue(ub.get("applied"))
        self.assertEqual(ub.get("baseline_source"), "db_core_neighbor")
        self.assertEqual(ub.get("db_neighbor_name"), "NearSACIn")
        self.assertEqual(ub.get("baseline_sol_liq"), (198.0, 210.0))
        self.assertLess(abs(sol - 198.0), abs(sol - 217.0))
        self.assertLess(abs(liq - 210.0), abs(liq - 221.0))


if __name__ == "__main__":
    unittest.main()
