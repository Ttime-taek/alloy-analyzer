# Regression: 2026-09-30 계산 로직 2차 점검 P1 — 물성 DB 블렌드 계단
#  - 가중치(analyzer._property_db_weight)가 거리 1·2·3에서 계단(2에서는 오히려 증가):
#    Sn-0.29Cu-xNi, Ni 0.26 → 0.28 %에서 인장 32.0 → 37.3, 전단 57.0 → 65.3 MPa.
#  - DB 보간(db_regression.predict_from_db)이 정확일치면 그 합금만, 조금만 벗어나도 가까운 5개를
#    1/(1+거리)로 섞어 값이 튐: 순수 Sn 연신 45 → 34.4 %, SAC305 항복 39.5 → 36.9 MPa.
#  - 가장 가까운 합금에 해당 물성이 없어도(Sn58Bi 전단) 그 거리로 가중치를 줘 먼 값을 과신.
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

import pytest

from test7.analyzer import AlloyAnalyzer, _property_db_weight
from test7.db_regression import predict_from_db_with_detail
from test7.solder_db import SOLDER_DB

A = AlloyAnalyzer(SOLDER_DB)
KEYS = ("tensile_strength", "yield_strength", "elongation", "shear_strength")


def _props(comp):
    return A.analyze_all(comp, include_ai=False, include_melting_ai=False)["props"]


def test_property_db_weight_is_continuous_and_monotonic() -> None:
    ds = [i * 0.001 for i in range(4001)]
    ws = [_property_db_weight(d) for d in ds]
    assert ws[0] == 1.0 and _property_db_weight(3.0) == 0.0 and _property_db_weight(5.0) == 0.0
    assert all(b <= a + 1e-12 for a, b in zip(ws, ws[1:]))
    assert max(abs(b - a) for a, b in zip(ws, ws[1:])) < 0.001
    assert _property_db_weight(None) == 0.0


@pytest.mark.parametrize(
    ("exact", "near"),
    [
        ({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, {"Sn": 96.49, "Ag": 3.01, "Cu": 0.5}),
        ({"Sn": 99.3, "Cu": 0.7}, {"Sn": 99.29, "Cu": 0.71}),
    ],
)
def test_exact_db_alloy_and_its_neighbor_agree(exact, near) -> None:
    a, b = _props(exact), _props(near)
    for k in KEYS:
        assert b[k] == pytest.approx(a[k], abs=0.5), k


def test_pure_sn_elongation_does_not_jump_with_trace_ni() -> None:
    a = _props({"Sn": 100.0})
    b = _props({"Sn": 99.99, "Ni": 0.01})
    assert b["elongation"] == pytest.approx(a["elongation"], abs=0.5)
    assert b["tensile_strength"] == pytest.approx(a["tensile_strength"], abs=0.5)


def test_weight_boundary_near_sn_cu_ni_is_continuous() -> None:
    a = _props({"Sn": 99.45, "Cu": 0.29, "Ni": 0.26})
    b = _props({"Sn": 99.43, "Cu": 0.29, "Ni": 0.28})
    assert abs(b["tensile_strength"] - a["tensile_strength"]) < 1.5
    assert abs(b["shear_strength"] - a["shear_strength"]) < 1.5


def test_blend_distance_is_per_property() -> None:
    # Sn58Bi 바로 옆: 인장은 Sn58Bi(가까움), 전단은 Sn58Bi에 값이 없어 더 먼 합금이 가장 가까운 근거.
    out = predict_from_db_with_detail({"Sn": 41.9, "Bi": 58.1})
    near = out["nearest_by_prop"]
    assert near["tensile"] < 0.5
    assert near["shear"] > near["tensile"] + 0.5
