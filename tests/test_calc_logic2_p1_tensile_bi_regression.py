# Regression: 2026-09-30 계산 로직 2차 점검 P1 — 인장강도 조성 모델의 Bi 항이 if/elif 분기
# (Sn 50 %, Bi 12·20 %, Ag 0.3·0.5 %)마다 다른 곡선을 골라 경계에서 튀었다.
#   Sn49.9Bi50.1 → Sn50.1Bi49.9: 85.6 → 71.1 MPa (Ag 0.4 %면 110.9 → 72.7)
#   Sn88.01Bi11.99 → Sn88Bi12: 63.4 → 77.6 MPa
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

import pytest

from test7.models import PropertyModels

M = PropertyModels()


def _tensile(comp):
    return M.predict_tensile_strength(comp, 139.0, 150.0)


def _max_step(comps):
    vals = [_tensile(c) for c in comps]
    return max(abs(b - a) for a, b in zip(vals, vals[1:]))


@pytest.mark.parametrize(
    ("label", "comps"),
    [
        ("Sn 40→60 %, Bi 나머지", [{"Sn": 40 + i * 0.01, "Bi": 60 - i * 0.01} for i in range(2001)]),
        ("Sn 40→60 %, Ag 0.4", [{"Sn": 40 + i * 0.01, "Bi": 59.6 - i * 0.01, "Ag": 0.4} for i in range(2001)]),
        ("Bi 8→25 %, Ag 0", [{"Sn": 92 - i * 0.01, "Bi": 8 + i * 0.01} for i in range(1701)]),
        ("Ag 0→1 %, Bi 3·Cu 0.5", [{"Sn": 96.5 - i * 0.001, "Ag": i * 0.001, "Cu": 0.5, "Bi": 3.0} for i in range(1001)]),
        ("Ag 0→1 %, Sn42Bi58", [{"Sn": 42 - i * 0.001, "Ag": i * 0.001, "Bi": 58.0} for i in range(1001)]),
        ("Bi 15→25 %, Sn < 50 (Pb 40)", [{"Sn": 45 - i * 0.01, "Pb": 40.0, "Bi": 15 + i * 0.01} for i in range(1001)]),
    ],
)
def test_tensile_bi_term_has_no_steps(label, comps) -> None:
    assert _max_step(comps) < 0.5, label


@pytest.mark.parametrize(
    ("comp", "expected"),
    [
        # 경계에서 먼 조성(DB 합금 포함)은 이전 분기식과 같은 값이어야 한다.
        ({"Sn": 42, "Bi": 58}, 87.61424693850952),
        ({"Sn": 42, "Bi": 57.6, "Ag": 0.4}, 114.12917305147289),
        ({"Sn": 42, "Bi": 57.8, "Ag": 0.2}, 88.42992925585523),
        ({"Sn": 93.5, "Ag": 3, "Cu": 0.5, "Bi": 3}, 77.19624258381921),
        ({"Sn": 96.2, "Ag": 0.3, "Cu": 0.5, "Bi": 3}, 49.50760793853347),
        ({"Sn": 82, "Ag": 3, "Bi": 15}, 75.05651337213484),
        ({"Sn": 74, "Ag": 1, "Bi": 25}, 69.05210300455008),
        ({"Sn": 93, "Ag": 3.5, "Bi": 0.5, "In": 3}, 57.20529810497251),
    ],
)
def test_values_away_from_boundaries_unchanged(comp, expected) -> None:
    assert M.predict_tensile_strength(comp, 139.0, 139.0) == pytest.approx(expected, abs=1e-9)
