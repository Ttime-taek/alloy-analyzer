# -*- coding: utf-8 -*-
"""SAC+Bi(무 In) 분류 경계 연속성 회귀 테스트.

이전: Bi=5% 경계에서 SAC→SnBi 전환으로 액상선이 약 +24.5℃ 점프(이진 Sn-Bi 경로가
SAC+Bi 액상선을 과대평가). 프로젝트 Anti-step 규칙(0.01% 변화로 2℃ 이상 튀면 모델 오류)
위반. 수정 후 In 거의 없는 SAC 모재는 Bi 첨가에도 SAC 경로를 유지해 연속이어야 한다.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.melting_predictor import _classify, hybrid_melting_predict


def _pred(comp):
    return hybrid_melting_predict(comp, [], ai_engine=None)


class SacBiContinuityTest(unittest.TestCase):
    def _norm(self, ag, cu, bi):
        sn = 100.0 - ag - cu - bi
        return {"Sn": sn, "Ag": ag, "Cu": cu, "Bi": bi}

    def test_no_classification_step_across_bi5(self):
        """Bi 4.9→5.1% 미세 변화에서 고상·액상 모두 2℃ 미만 변화(계단 금지)."""
        lo = self._norm(3.0, 0.5, 4.9)
        hi = self._norm(3.0, 0.5, 5.1)
        s_lo, l_lo, _, _ = _pred(lo)
        s_hi, l_hi, _, _ = _pred(hi)
        self.assertLess(abs(s_hi - s_lo), 2.0, f"solidus step {s_lo}->{s_hi}")
        self.assertLess(abs(l_hi - l_lo), 2.0, f"liquidus step {l_lo}->{l_hi}")

    def test_sac_matrix_stays_sac_with_bi(self):
        """In 거의 없는 SAC 모재는 Bi 6~12%에서도 SAC로 분류."""
        for bi in (6.0, 8.0, 10.0, 12.0):
            self.assertEqual(_classify(self._norm(3.0, 0.5, bi)), "SAC", f"Bi={bi}")

    def test_sac_bi_liquidus_not_overestimated(self):
        """SAC305+5Bi 액상선은 이진 Sn-Bi(≈242℃)가 아니라 공정 근처(<222℃)."""
        s, l, _, _ = _pred(self._norm(3.0, 0.5, 5.0))
        self.assertLess(l, 222.0, f"liquidus {l} 가 과대(이진 Sn-Bi 오류)")
        self.assertGreater(l, 205.0)

    def test_in_bearing_high_bi_still_snbi(self):
        """In 동반 고-Bi(Bi≥In)는 기존대로 SnBi 경로 유지(회귀 방지)."""
        self.assertEqual(
            _classify({"Sn": 79.7, "Ag": 3.5, "Bi": 10.0, "Cu": 0.8, "In": 6.0}),
            "SnBi",
        )

    def test_monotonic_liquidus_bi_sweep(self):
        """Bi 0→12% 증가 시 SAC 액상선은 (전반적으로) 비증가 — 큰 역전 없음."""
        prev = None
        for bi in [0.0, 1.0, 2.0, 3.0, 5.0, 7.0, 9.0, 11.0, 12.0]:
            _, l, _, _ = _pred(self._norm(3.0, 0.5, bi))
            if prev is not None:
                self.assertLess(l - prev, 2.5, f"Bi={bi} 액상선 역전 {prev}->{l}")
            prev = l


if __name__ == "__main__":
    unittest.main()
