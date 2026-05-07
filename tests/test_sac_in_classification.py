# -*- coding: utf-8 -*-
"""SAC + In 저함량 분류(Sn>80·Ag·Cu·Bi≤5·In≤8)가 other로 떨어지지 않는지."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.melting_predictor import _classify, hybrid_melting_predict


class SacInClassificationTest(unittest.TestCase):
    def test_user_in6_is_sac_not_other(self):
        """In 6% 첨가 SAC가 inp==0 조건 때문에 other→L4 과대평가되던 케이스."""
        norm = {"Sn": 89.2, "Ag": 3.5, "Bi": 0.5, "Cu": 0.8, "In": 6.0}
        self.assertEqual(_classify(norm), "SAC")

    def test_sac_in_alloy_matches_reported_dsc_band(self):
        """실측 DSC 예: 고상≈202℃ 액상≈206℃ — SAC 상태도·튜닝 계수 정합."""
        norm = {"Sn": 89.2, "Ag": 3.5, "Bi": 0.5, "Cu": 0.8, "In": 6.0}
        sol, liq, _, detail = hybrid_melting_predict(norm, [], ai_engine=None)
        self.assertEqual(detail.get("family"), "SAC")
        self.assertAlmostEqual(sol, 202.0, delta=1.2)
        self.assertAlmostEqual(liq, 206.0, delta=1.2)

    def test_sac305_without_bi_in_near_classic_sac(self):
        """Bi/In 없는 근-SAC305는 공정점 근처 유지(In 계수 변경과 무관하게 검증)."""
        from test7.melting_predictor import _phase_diagram_predict

        norm = {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}
        sol, liq, _ = _phase_diagram_predict(norm, "SAC")
        self.assertAlmostEqual(sol, 217.0, delta=1.5)
        self.assertAlmostEqual(liq, 222.0, delta=2.0)


if __name__ == "__main__":
    unittest.main()
