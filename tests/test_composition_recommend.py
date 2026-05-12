# -*- coding: utf-8 -*-
"""composition_recommend: 목표 융점 격자 탐색."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.ai_engine import AIEngine
from test7.analyzer import AlloyAnalyzer
from test7.composition_recommend import (
    MeltTarget,
    estimate_grid_points,
    list_db_compositions_matching_melt_target,
    merge_db_registered_into_recommend_candidates,
    recommend_compositions,
    _db_close_names_for_predicted_melt,
    _melt_target_l1_score,
    _plastic_range_c,
)
from test7.solder_db import SOLDER_DB


class CompositionRecommendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = AlloyAnalyzer(SOLDER_DB, ai_engine=AIEngine())

    def test_melt_target_l1_score_solidus_only(self):
        t = MeltTarget(solidus_c=138.0, solidus_tolerance_c=1.0)
        self.assertEqual(_melt_target_l1_score(140.0, 999.0, t), 2.0)

    def test_melt_target_l1_score_both_axes(self):
        t = MeltTarget(solidus_c=138.0, liquidus_c=200.0)
        self.assertEqual(_melt_target_l1_score(140.0, 198.0, t), 4.0)

    def test_melt_target_l1_score_rank_any_axis_min(self):
        t = MeltTarget(solidus_c=138.0, liquidus_c=200.0, rank_match_any_axis=True)
        self.assertEqual(_melt_target_l1_score(140.0, 198.0, t), 2.0)
        self.assertEqual(_melt_target_l1_score(138.0, 250.0, t), 0.0)

    def test_plastic_range_non_negative(self):
        self.assertEqual(_plastic_range_c(138.0, 200.0), 62.0)
        self.assertEqual(_plastic_range_c(200.0, 138.0), 0.0)

    def test_melt_sort_tie_breaker_plastic_range_then_match_score(self):
        rows = [
            {"penalty": 10.0, "plastic_range_c": 5.0, "match_score": 0.9},
            {"penalty": 10.0, "plastic_range_c": 3.0, "match_score": 0.5},
            {"penalty": 8.0, "plastic_range_c": 100.0, "match_score": 0.1},
        ]
        rows.sort(
            key=lambda r: (
                float(r["penalty"]),
                float(r["plastic_range_c"]),
                float(r["match_score"]),
            )
        )
        self.assertEqual(rows[0]["penalty"], 8.0)
        self.assertEqual(rows[1]["plastic_range_c"], 3.0)
        self.assertEqual(rows[2]["plastic_range_c"], 5.0)

    def test_estimate_grid_points(self):
        n = estimate_grid_points(
            [{"element": "Bi", "min": 0, "max": 10, "step": 1.0}]
        )
        self.assertEqual(n, 11)

    def test_grid_exceeds_max_raises(self):
        with self.assertRaises(ValueError) as ctx:
            recommend_compositions(
                self.analyzer,
                fixed_comp={"Ag": 1.0, "Cu": 0.71},
                free_axes=[{"element": "Bi", "min": 0, "max": 99, "step": 0.1}],
                balance_element="Sn",
                target=MeltTarget(solidus_c=138.0, solidus_tolerance_c=5.0),
                max_grid_points=50,
            )
        self.assertIn("격자", str(ctx.exception))

    def test_recommend_bi_sweep_near_138_solidus(self):
        """Sn-1Ag-0.71Cu 대역에서 Bi 스윕 시 고상선이 ~138℃ 부근 후보가 상위에 온다."""
        target = MeltTarget(solidus_c=138.0, solidus_tolerance_c=2.0)
        rows, meta = recommend_compositions(
            self.analyzer,
            fixed_comp={"Ag": 1.0, "Cu": 0.71},
            free_axes=[{"element": "Bi", "min": 22.0, "max": 28.0, "step": 1.0}],
            balance_element="Sn",
            target=target,
            max_results=5,
            max_grid_points=50_000,
        )
        self.assertGreaterEqual(len(rows), 1)
        self.assertIn("disclaimer", meta)
        self.assertGreater(meta.get("grid_points_evaluated", 0), 0)
        penalties = [float(r["penalty"]) for r in rows]
        self.assertEqual(penalties, sorted(penalties))
        best = rows[0]
        self.assertLess(abs(float(best["solidus"]) - 138.0), 6.0)

    def test_db_close_names_merges_comp_and_liquidus_neighbors(self):
        """예측 액상 ~200℃일 때 액상 근접 DB(Sn-In-SAC 등)가 조성 최근접 뒤에 붙는다."""
        s = _db_close_names_for_predicted_melt(
            SOLDER_DB, 138.0, 200.0, "Sn1Ag25Bi0.7Cu", max_labels=10
        )
        self.assertIn("Sn1Ag25Bi0.7Cu", s)
        self.assertIn("Sn3.5Ag0.5Bi8.0In", s)
        self.assertIn("Sn3.5Ag0.5Bi6.0In", s)

    def test_list_db_matches_liquidus_band_includes_200c_neighbors(self):
        """액상 200±3℃ 밴드에 Sn1Ag0.8Cu8In10Bi 등 여러 DB 행이 포함된다."""
        tgt = MeltTarget(liquidus_c=200.0, liquidus_tolerance_c=3.0)
        rows, meta = list_db_compositions_matching_melt_target(
            self.analyzer, tgt, match_any_specified_axis=False, max_rows=100
        )
        self.assertGreaterEqual(meta.get("db_temperature_match_count", 0), 1)
        names = [r["name"] for r in rows]
        self.assertIn("Sn1Ag0.8Cu8In10Bi", names)

    def test_db_band_min_50_includes_dual_target_near_solidus(self):
        """요청 허용이 좁아도 기본 최소 밴드(50℃)로 AND 시 Sn1Ag0.8Cu8In10Bi(159/200)가 포함된다."""
        tgt = MeltTarget(
            solidus_c=138.0,
            solidus_tolerance_c=2.0,
            liquidus_c=200.0,
            liquidus_tolerance_c=1.0,
        )
        rows, meta = list_db_compositions_matching_melt_target(
            self.analyzer, tgt, match_any_specified_axis=False, max_rows=300
        )
        self.assertEqual(meta.get("db_min_axis_band_tolerance_c"), 50.0)
        self.assertEqual(meta.get("db_band_effective_solidus_tolerance_c"), 50.0)
        self.assertEqual(meta.get("db_band_effective_liquidus_tolerance_c"), 50.0)
        names = [r["name"] for r in rows]
        self.assertIn("Sn1Ag0.8Cu8In10Bi", names)

    def test_list_db_match_any_axis(self):
        """OR 모드: 두 축을 모두 좁게 잡았을 때, 한 축만 맞는 행은 any에만 포함된다."""
        tgt = MeltTarget(
            solidus_c=138.0,
            solidus_tolerance_c=0.35,
            liquidus_c=250.0,
            liquidus_tolerance_c=0.35,
        )
        rows_any, meta_any = list_db_compositions_matching_melt_target(
            self.analyzer,
            tgt,
            match_any_specified_axis=True,
            max_rows=200,
            min_axis_band_tolerance_c=0.0,
        )
        rows_all, meta_all = list_db_compositions_matching_melt_target(
            self.analyzer,
            tgt,
            match_any_specified_axis=False,
            max_rows=200,
            min_axis_band_tolerance_c=0.0,
        )
        self.assertGreater(meta_any["db_temperature_match_count"], meta_all["db_temperature_match_count"])

    def test_merge_db_registered_includes_anchor_and_sorts_by_melt_fit(self):
        """동일 목표로 list_db 행을 격자 결과와 병합하면 Sn1Ag0.8Cu8In10Bi가 후보에 포함되고 DB 출처로 표시된다. 정렬은 융점 적합도(penalty) 우선이다."""
        tgt = MeltTarget(
            solidus_c=138.0,
            solidus_tolerance_c=2.0,
            liquidus_c=200.0,
            liquidus_tolerance_c=1.0,
        )
        db_raw, _ = list_db_compositions_matching_melt_target(
            self.analyzer, tgt, match_any_specified_axis=True, max_rows=100
        )
        self.assertTrue(any(r.get("name") == "Sn1Ag0.8Cu8In10Bi" for r in db_raw))
        grid, _ = recommend_compositions(
            self.analyzer,
            fixed_comp={"Ag": 1.0, "Cu": 0.71},
            free_axes=[{"element": "Bi", "min": 22.0, "max": 28.0, "step": 1.0}],
            balance_element="Sn",
            target=tgt,
            max_results=50,
            max_grid_points=50_000,
            unbounded_sorted_return=True,
        )
        merged, m = merge_db_registered_into_recommend_candidates(
            self.analyzer,
            grid,
            db_raw,
            tgt,
            max_results=30,
            max_db_registered_in_merged=0,
        )
        self.assertGreater(m.get("melt_candidates_db_registered_total", 0), 0)
        hit = next(
            (r for r in merged if r.get("registered_name") == "Sn1Ag0.8Cu8In10Bi"),
            None,
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit["melt_row_source"], "solder_db_registered")
        self.assertEqual(float(hit["solidus"]), 159.0)
        self.assertEqual(float(hit["liquidus"]), 200.0)
        penalties = [float(r["penalty"]) for r in merged]
        self.assertEqual(penalties, sorted(penalties), "병합 목록은 penalty 비감소 순이어야 한다")

    def test_merge_db_cap_leaves_room_for_grid_candidates(self):
        """DB 병합 상한을 두면 표에 predicted_grid 행이 남는다(밴드 일치 DB가 많아도)."""
        tgt = MeltTarget(
            solidus_c=138.0,
            solidus_tolerance_c=50.0,
            liquidus_c=200.0,
            liquidus_tolerance_c=50.0,
        )
        db_raw, _ = list_db_compositions_matching_melt_target(
            self.analyzer, tgt, match_any_specified_axis=True, max_rows=200
        )
        self.assertGreater(len(db_raw), 5, "테스트 전제: OR 밴드로 다수의 DB 행이 있어야 함")
        grid, _ = recommend_compositions(
            self.analyzer,
            fixed_comp={"Ag": 1.0, "Cu": 0.71},
            free_axes=[{"element": "Bi", "min": 22.0, "max": 28.0, "step": 1.0}],
            balance_element="Sn",
            target=tgt,
            max_results=50,
            max_grid_points=50_000,
            unbounded_sorted_return=True,
        )
        self.assertGreater(len(grid), 0, "격자 후보가 있어야 함")
        merged_capped, mc = merge_db_registered_into_recommend_candidates(
            self.analyzer,
            grid,
            db_raw,
            tgt,
            max_results=200,
            max_db_registered_in_merged=5,
        )
        self.assertLessEqual(mc.get("melt_candidates_db_registered_in_merged", 999), 5)
        sources = {r.get("melt_row_source") for r in merged_capped}
        self.assertIn("predicted_grid", sources)
        self.assertIn("solder_db_registered", sources)


if __name__ == "__main__":
    unittest.main()
