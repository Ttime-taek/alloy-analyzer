# -*- coding: utf-8 -*-
"""강도(인장·항복·전단·연신) 예측 회귀 — MODEL·DB 블렌드."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.analyzer import AlloyAnalyzer
from test7.db_regression import parse_alloy, predict_from_db_with_detail
from test7.models import PropertyModels
from test7.solder_db import SOLDER_DB
from test7.strength_literature_refs import nearest_strength_literature


def _blend_props(norm, mdl_props, db_out):
    """analyzer.analyze_all 과 동일한 물성 DB 블렌드."""
    db_pred = (db_out.get("pred") if isinstance(db_out, dict) else None) or {}
    db_top = (db_out.get("top") if isinstance(db_out, dict) else None) or []
    db_best_dist = float((db_top[0] or {}).get("dist", 999)) if db_top else 999.0
    db_exact_hit = db_best_dist <= 1e-4
    use_db = db_best_dist <= 3.0
    db_w = 1.0 if db_exact_hit else (min(0.85, 1.0 / (1.0 + db_best_dist / 2.0)) if use_db else 0.0)
    mdl_w = 1.0 - db_w
    out = dict(mdl_props)
    for ko, kd in [
        ("tensile_strength", "tensile"),
        ("yield_strength", "yield_strength"),
        ("elongation", "elongation"),
        ("shear_strength", "shear"),
    ]:
        dv, mv = db_pred.get(kd), out.get(ko)
        if dv is not None and mv is not None and db_w > 0:
            out[ko] = float(dv) if db_exact_hit else (float(mv) * mdl_w + float(dv) * db_w)
    return out


class StrengthPredictionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = AlloyAnalyzer(SOLDER_DB)
        cls.models = PropertyModels()

    def _predict(self, comp):
        norm = self.analyzer.normalize(comp)
        sol, liq, _, _, _ = self.analyzer.calc_melting_with_detail(None, norm)
        mdl = self.models.predict_all(norm, sol, liq)
        db_out = predict_from_db_with_detail(norm)
        return _blend_props(norm, mdl, db_out), mdl, norm, sol, liq

    def test_sac305_db_blend_near_measured(self):
        comp = parse_alloy("Sn3.0Ag0.5Cu")
        blend, _, _, _, _ = self._predict(comp)
        self.assertAlmostEqual(blend["tensile_strength"], 48.0, delta=2.0)
        self.assertAlmostEqual(blend["shear_strength"], 82.0, delta=5.0)

    def test_exact_db_match_uses_db_values_without_blending(self):
        """DB 정확 일치 조성은 물성도 모델 혼합 없이 DB 값이 그대로 나와야 한다."""
        comp = parse_alloy("Sn3.0Ag0.5Cu")
        r = self.analyzer.analyze_all(comp)
        db_out = predict_from_db_with_detail(comp)
        db_pred = db_out.get("pred") or {}
        self.assertIn(r["props"].get("tensile_strength_basis"), {"db_priority", "db_idw", "db_blend", "db_exact"})
        self.assertAlmostEqual(r["props"].get("tensile_strength_db_mpa", 0), r["props"].get("tensile_strength", 0), delta=1e-6)
        self.assertAlmostEqual(float(db_pred.get("yield_strength", 0)), r["props"].get("yield_strength", 0), delta=1e-6)
        self.assertIn(r["props"].get("yield_strength_basis"), {None, "db_blend"})
        self.assertLess(r["confidence"], 95.0)
        self.assertLess(r["confidence_overall"], 90.0)

    def test_sac_bi3_shear_not_overestimated(self):
        """SAC+3Bi 전단: 이전 MODEL은 인장×1.55로 ~110 MPa 과대."""
        comp = parse_alloy("Sn3.0Ag0.5Cu3Bi")
        blend, mdl, _, _, _ = self._predict(comp)
        self.assertLess(mdl["shear_strength"], 35.0)
        self.assertAlmostEqual(blend["shear_strength"], 28.0, delta=3.0)

    def test_sac_bi_no_hard_step_at_5pct(self):
        """Bi 4.9→5.1% 전단 계단(anti-step) 금지."""
        base = {"Sn": 93.5, "Ag": 3.0, "Cu": 0.5}
        _, m1, _, s1, l1 = self._predict({**base, "Bi": 4.9})
        _, m2, _, s2, l2 = self._predict({**base, "Bi": 5.1})
        self.assertLess(abs(m2["shear_strength"] - m1["shear_strength"]), 5.0)
        self.assertLess(abs(m2["tensile_strength"] - m1["tensile_strength"]), 5.0)

    def test_yield_le_tensile_all_db_alloys(self):
        from test7.solder_properties import unique_alloy_names

        for alloy in unique_alloy_names():
            comp = parse_alloy(alloy)
            _, mdl, _, _, _ = self._predict(comp)
            self.assertLessEqual(
                mdl["yield_strength"],
                mdl["tensile_strength"] + 0.01,
                msg=alloy,
            )

    def test_sac305_model_near_literature(self):
        """MODEL-only SAC305 인장: 문헌 41 MPa 부근 (과대 +11 MPa 제거)."""
        comp = parse_alloy("Sn3.0Ag0.5Cu")
        _, mdl, norm, _, _ = self._predict(comp)
        self.assertGreater(mdl["tensile_strength"], 44.0)
        self.assertLess(mdl["tensile_strength"], 52.0)
        lit = nearest_strength_literature(norm)
        self.assertIsNotNone(lit)
        self.assertAlmostEqual(lit["tensile_mpa"], 40.95, delta=5.0)

    def test_sncu_model_near_literature(self):
        comp = parse_alloy("Sn0.7Cu")
        _, mdl, norm, _, _ = self._predict(comp)
        self.assertGreater(mdl["tensile_strength"], 36.0)
        self.assertLess(mdl["tensile_strength"], 42.0)
        lit = nearest_strength_literature(norm)
        self.assertIsNotNone(lit)

    def test_sn1ag25bi0p7cu_tensile_not_sn57bi_curve(self):
        """Sn1Ag25Bi0.7Cu: Bi≥20 저Sn 곡선(A=80) 오적용 시 UTS ~95 MPa 과대."""
        comp = parse_alloy("Sn1Ag25Bi0.7Cu")
        blend, mdl, norm, _, _ = self._predict(comp)
        self.assertGreater(mdl["tensile_strength"], 52.0)
        self.assertLess(mdl["tensile_strength"], 82.0)
        self.assertLess(blend["tensile_strength"], 82.0)
        lit = nearest_strength_literature(norm)
        self.assertIsNone(lit)

    def test_far_properties_db_keeps_the_composition_model_tensile(self):
        """물성 DB가 먼 조성은 DB를 덮어쓰지 않고 모델값을 유지해야 한다."""
        comp = {"Sn": 96.1, "Ag": 1.1, "Cu": 0.7, "Bi": 1.8, "Ni": 0.3}
        blend, mdl, _, _, _ = self._predict(comp)
        self.assertAlmostEqual(blend["shear_strength"], mdl["shear_strength"], delta=0.01)
        r = self.analyzer.analyze_all(comp)
        self.assertEqual(r["props"].get("tensile_strength_basis"), "model_prediction")
        self.assertEqual(r["props"].get("shear_strength_basis"), None)
        self.assertAlmostEqual(
            r["props"].get("tensile_strength"),
            r["props"].get("tensile_strength_model_mpa"),
            delta=1e-6,
        )
        self.assertNotAlmostEqual(
            r["props"].get("tensile_strength"),
            r["props"].get("tensile_strength_db_mpa"),
            delta=0.5,
        )
        self.assertAlmostEqual(r["props"].get("tensile_strength"), mdl["tensile_strength"], delta=0.5)
        self.assertAlmostEqual(r["props"].get("shear_strength"), mdl["shear_strength"], delta=0.5)
        self.assertGreater(r["props"].get("tensile_strength_model_mpa", 0), 65.0)
        self.assertEqual(r.get("evidence", {}).get("props", {}).get("tensile_strength"), "MODEL")
        neighbors = r["props"].get("shear_neighbors") or []
        self.assertTrue(any("Bi" in str(n.get("alloy", "")) for n in neighbors))

    def test_high_bi_keeps_model_and_shear(self):
        """고Bi 조성은 먼 DB를 덮어쓰지 않고 모델/문헌 경로를 유지해야 한다."""
        comp = parse_alloy("Sn57Bi42Ag1")
        r = self.analyzer.analyze_all(comp)
        self.assertGreater(r["props"].get("tensile_strength", 0), 60.0)
        self.assertLess(r["props"].get("tensile_strength", 0), 105.0)
        self.assertGreater(r["props"].get("shear_strength", 0), 20.0)
        self.assertLess(r["props"].get("shear_strength", 0), 40.0)
        self.assertEqual(r["props"].get("tensile_strength_basis"), "model_prediction")
        self.assertEqual(r["props"].get("shear_strength_basis"), None)
        self.assertAlmostEqual(
            r["props"].get("tensile_strength", 0),
            r["props"].get("tensile_strength_model_mpa", 0),
            delta=1e-6,
        )
        self.assertNotAlmostEqual(
            r["props"].get("tensile_strength", 0),
            r["props"].get("tensile_strength_db_mpa", 0),
            delta=0.5,
        )

    def test_high_bi_anchor_near_literature(self):
        """고Bi 대표 앵커 Sn57.6Bi0.4Ag는 문헌/내부 실측 범위에 붙어야 한다."""
        comp = parse_alloy("Sn57.6Bi0.4Ag")
        r = self.analyzer.analyze_all(comp)
        self.assertGreater(r["props"].get("tensile_strength", 0), 100.0)
        self.assertLess(r["props"].get("tensile_strength", 0), 120.0)
        self.assertGreater(r["props"].get("shear_strength", 0), 30.0)
        self.assertLess(r["props"].get("shear_strength", 0), 42.0)
        lit = nearest_strength_literature(comp)
        self.assertIsNotNone(lit)
        self.assertAlmostEqual(float(lit["tensile_mpa"]), 58.7, delta=1e-6)
        self.assertEqual(lit["refs"][0]["doi"], "10.3390/met9040462")

    def test_pure_snbi58_not_overestimated(self):
        """Ag가 거의 없는 Sn58Bi는 과거 고Bi A=80 곡선 과대평가를 피해야 한다."""
        comp = parse_alloy("Sn58Bi")
        r = self.analyzer.analyze_all(comp)
        self.assertGreater(r["props"].get("tensile_strength", 0), 75.0)
        self.assertLess(r["props"].get("tensile_strength", 0), 90.0)
        self.assertGreater(r["props"].get("shear_strength", 0), 28.0)
        self.assertLess(r["props"].get("shear_strength", 0), 40.0)

    def test_final_yield_never_exceeds_tensile(self):
        """최종 analyzer 출력에서는 항복강도가 인장강도를 넘지 않아야 한다."""
        for comp in (
            {"Sn": 100.0},
            {"Sn": 42.0, "In": 1.0, "Cu": 1.0, "Zn": 1.0},
        ):
            r = self.analyzer.analyze_all(comp)
            self.assertLessEqual(
                float(r["props"].get("yield_strength", 0)),
                float(r["props"].get("tensile_strength", 0)),
            )

    def test_sac305_shear_uses_db_blend(self):
        comp = parse_alloy("Sn3.0Ag0.5Cu")
        r = self.analyzer.analyze_all(comp)
        self.assertAlmostEqual(r["props"]["shear_strength"], 82.0, delta=5.0)
        self.assertIn(r["props"].get("shear_strength_basis"), {"db_blend", "db_idw", "db_exact"})

    def test_ni_micro_addition_smooth(self):
        """Ni 미량 첨가는 인장·전단이 연속 증가(계단 없음)."""
        base = {"Sn": 96.45, "Ag": 3.0, "Cu": 0.5, "Ni": 0.0}
        _, m0, _, _, _ = self._predict(base)
        _, m1, _, _, _ = self._predict({**base, "Ni": 0.05})
        self.assertLess(m1["tensile_strength"] - m0["tensile_strength"], 4.0)
        self.assertGreater(m1["tensile_strength"] - m0["tensile_strength"], 0.0)
        self.assertLess(m1["shear_strength"] - m0["shear_strength"], 5.0)


if __name__ == "__main__":
    unittest.main()
