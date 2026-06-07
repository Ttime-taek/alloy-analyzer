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
    use_db = db_best_dist <= 3.0
    db_w = min(0.85, 1.0 / (1.0 + db_best_dist / 2.0)) if use_db else 0.0
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
            out[ko] = float(mv) * mdl_w + float(dv) * db_w
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
