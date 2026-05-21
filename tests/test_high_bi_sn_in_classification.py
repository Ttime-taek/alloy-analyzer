# -*- coding: utf-8 -*-
"""고Bi(Bi>5)+In 동시 첨가 시 SnBi 분류 및 other 과대평가 방지."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.melting_predictor import _classify, hybrid_melting_predict


class HighBiWithInClassificationTest(unittest.TestCase):
    def test_bi10_in6_sn_bi_not_other(self):
        """Bi≥In 이면 SAC(bi≤5)도 SnBi(inp==0 전용)도 아니게 되던 조성을 SnBi로 본다."""
        norm = {"Sn": 79.7, "Ag": 3.5, "Bi": 10.0, "Cu": 0.8, "In": 6.0}
        self.assertEqual(_classify(norm), "SnBi")

    def test_high_bi_in_melting_not_near_250c(self):
        """other+L4 지배 시 ~250℃ 근처로 치솟던 구간을 제거 — 고상·액상이 저융대역으로 귀속."""
        norm = {"Sn": 79.7, "Ag": 3.5, "Bi": 10.0, "Cu": 0.8, "In": 6.0}
        sol, liq, _, detail = hybrid_melting_predict(norm, [], ai_engine=None)
        self.assertEqual(detail.get("family"), "SnBi")
        self.assertLess(sol, 200.0)
        self.assertLess(liq, 230.0)
        self.assertGreater(sol, 110.0)

    def test_grid_candidate_sn_bi_14_in_11_not_l4_250c(self):
        """목표 융점 탐색 격자 후보 Sn73.2 Ag0.8 Cu1 Bi14 In11 — 과거 other+L4 ~228/250 방지."""
        norm = {"Sn": 73.2, "Ag": 0.8, "Cu": 1.0, "Bi": 14.0, "In": 11.0}
        self.assertEqual(_classify(norm), "SnBi")
        from test7.analyzer import AlloyAnalyzer
        from test7.ai_engine import AIEngine
        from test7.solder_db import SOLDER_DB

        a = AlloyAnalyzer(SOLDER_DB, ai_engine=AIEngine())
        a._sync_db_prepared()
        nn = a.normalize(norm)
        sol, liq, _, detail = hybrid_melting_predict(nn, a.db_prepared, ai_engine=a.melting_ai)
        self.assertEqual(detail.get("family"), "SnBi")
        self.assertLess(sol, 175.0, "고상이 SnBi L2 근처로 내려와야 함 (과거 ~228℃는 오류)")
        self.assertLess(liq, 215.0, "액상이 저융대로 — DB 인접 159/200 및 L2와 정합")
        self.assertGreater(sol, 125.0)


if __name__ == "__main__":
    unittest.main()
