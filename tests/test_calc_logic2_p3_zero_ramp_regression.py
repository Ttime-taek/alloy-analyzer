# Regression: 2026-09-30 계산 로직 2차 점검 P3 — 상태도 계층(L2)이 Cu·Ag가 0 → 조금일 때
# Sn-Ag·Sn-Cu → SAC(3원 공정 217 ℃)로 바로 바뀌어 고상선이 계단이었다
# (Sn-3.5Ag + Cu 0.05 % 221 → 214.5 ℃, Sn-0.7Cu + Ag 0.05 % 227 → 216.7 ℃; DB 절대값 레이어가
# DB 행 근처에서만 가려 주고 있었음). 0 → 0.2 %에서 두 계열을 섞는다.
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

import pytest

from test7.melting_predictor import _classify, _phase_diagram_predict_smooth


def _l2(comp):
    s, l, _c, _m = _phase_diagram_predict_smooth(comp, _classify(comp))
    return s, l


@pytest.mark.parametrize(
    ("base", "el"),
    [({"Sn": 96.5, "Ag": 3.5}, "Cu"), ({"Sn": 99.3, "Cu": 0.7}, "Ag"), ({"Sn": 99.0, "Ag": 1.0}, "Cu")],
)
def test_l2_is_continuous_as_third_element_starts(base, el) -> None:
    prev = _l2(base)
    for i in range(1, 61):
        x = i * 0.005
        c = dict(base, **{el: x})
        c["Sn"] = base["Sn"] - x
        cur = _l2(c)
        assert abs(cur[0] - prev[0]) < 1.0, (el, x)
        assert abs(cur[1] - prev[1]) < 1.0, (el, x)
        prev = cur


def test_ramp_reaches_sac_by_0_2_percent() -> None:
    s, _l = _l2({"Sn": 96.25, "Ag": 3.5, "Cu": 0.25})
    assert s == pytest.approx(217.0, abs=0.5)
