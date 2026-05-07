# -*- coding: utf-8 -*-
"""reflow_tune_engine — shared/reflow_tune_rules.json 기반 검증 스냅샷 테스트."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import reflow_tune_engine as rte


class ReflowTuneEngineTest(unittest.TestCase):
    """권장값·분류가 JSON과 규약을 따르는지 확인."""

    def setUp(self):
        rte.reload_rules()

    def test_rules_load(self):
        r = rte.load_rules()
        self.assertGreaterEqual(r.get("version", 0), 1)
        self.assertIn("bases", r)
        self.assertIn("high_bi", r["bases"])

    def test_classify_78_high_bi(self):
        c = rte.classify_preset("78(Sn-0.4Ag-57.6Bi)")
        self.assertTrue(c["is_high_bi"])
        self.assertFalse(c["is_mid_bi"])

    def test_classify_73_mid_bi(self):
        c = rte.classify_preset("73(Sn-3Ag-15Bi)")
        self.assertFalse(c["is_high_bi"])
        self.assertTrue(c["is_mid_bi"])

    def test_recommend_78_bplusc(self):
        t = rte.recommend_tune_for_goal("B+C", "78(Sn-Bi)")
        self.assertEqual(t["peak_margin"], 40.0)
        self.assertEqual(t["over_liquidus_time"], 75.0)

    def test_recommend_sac_default(self):
        t = rte.recommend_tune_for_goal("없음", "AUTO")
        self.assertEqual(t["ramp_rate"], 1.5)
        self.assertEqual(t["over_liquidus_time"], 40.0)

    def test_validate_fatal_tal(self):
        v = rte.validate_profile_tune(
            {"ramp_rate": 1.5, "preheat_time": 90, "over_liquidus_time": 10,
             "cool_rate": 2.0, "peak_margin": 25},
            "73(Sn-Ag-Bi)",
        )
        self.assertTrue(any("25s" in e for e in v["errors"]))

    def test_validate_mid_bi_ok_band(self):
        v = rte.validate_profile_tune(
            {"ramp_rate": 1.5, "preheat_time": 90, "over_liquidus_time": 60,
             "cool_rate": 2.5, "peak_margin": 35},
            "73(wide)",
        )
        self.assertFalse(v["errors"])
        self.assertTrue(any("50~80s" in o for o in v["oks"]))

    def test_goal_recommend_ops_cover_non_none_goals(self):
        r = rte.load_rules()
        goals = [g for g in (r.get("tuningGoalOptions") or []) if g != "없음"]
        go = r.get("goalRecommendOps") or {}
        for g in goals:
            self.assertIn(g, go, msg=f"missing goalRecommendOps[{g!r}]")
            branch = go[g]
            self.assertIsInstance(branch, dict)
            for pk in ("high_bi", "mid_bi", "default"):
                self.assertIn(pk, branch)
                self.assertIsInstance(branch[pk], list)


if __name__ == "__main__":
    unittest.main()
