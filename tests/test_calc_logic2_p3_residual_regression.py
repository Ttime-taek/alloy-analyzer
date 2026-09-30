# Regression: 2026-09-30 계산 로직 2차 점검 P3 — 실측이 1개뿐이고 상태도·이웃과 다른 DB 행 주변의 '바늘'.
# 최근접 DB 실측 절대값(L1)의 가중이 거리 0.1~0.5 안에서만 커서, 그 조성에서만 실측이 나오고
# ±0.2~0.5 % 옆은 곧바로 상태도 값으로 돌아갔다.
#   Sn-xSb 고상:          4.5 % 234.7 → 5.0 % 223.0 → 5.5 % 235.7 ℃
#   Sn-xIn-1Cu-1Zn 액상:  41.8 % 150.6 → 42 % 121.0 → 42.2 % 148.0 ℃
# 이제 실측 − 사전값(잔차)을 주변으로 매끈하게 퍼뜨린다(한쪽에만 있는 원소 방향으로는 덜 퍼짐).
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

import pytest

from test7.melting_predictor import MELTING_ENGINE_VERSION, _element_mismatch_penalty, hybrid_melting_predict
from test7.prediction_validation import _cluster_indices
from test7.solder_db import SOLDER_DB

DB = [
    {"name": r["name"], "comp": r["comp"], "solidus": float(r["solidus"]), "liquidus": float(r["liquidus"])}
    for r in SOLDER_DB
]


def _p(comp, db=DB):
    s, l, _peak, _d = hybrid_melting_predict(comp, db, ai_engine=None)
    return float(s), float(l)


def test_engine_version() -> None:
    assert MELTING_ENGINE_VERSION == "15"


def test_measured_points_are_reproduced_exactly() -> None:
    assert _p({"Sn": 95.0, "Sb": 5.0}) == (223.0, 238.0)
    assert _p({"Sn": 56.0, "In": 42.0, "Cu": 1.0, "Zn": 1.0}) == (119.0, 121.0)


def test_sn_sb_measurement_influences_its_neighborhood_smoothly() -> None:
    xs = [4.0 + i * 0.05 for i in range(41)]
    sol = [_p({"Sn": 100 - x, "Sb": x})[0] for x in xs]
    assert max(abs(b - a) for a, b in zip(sol, sol[1:])) < 2.5
    # 0.2 % 옆(4.8 %)은 실측(223) 쪽에 가깝고, 1 % 떨어지면 상태도 쪽으로 돌아간다.
    assert _p({"Sn": 95.2, "Sb": 4.8})[0] < 226.0
    assert _p({"Sn": 94.0, "Sb": 6.0})[0] > 228.0


def test_sn_in_cu_zn_needle_is_widened() -> None:
    xs = [40.0 + i * 0.05 for i in range(81)]
    liq = [_p({"Sn": 98 - x, "In": x, "Cu": 1.0, "Zn": 1.0})[1] for x in xs]
    assert max(abs(b - a) for a, b in zip(liq, liq[1:])) < 5.0
    assert _p({"Sn": 56.2, "In": 41.8, "Cu": 1.0, "Zn": 1.0})[1] < 130.0
    assert _p({"Sn": 55.8, "In": 42.2, "Cu": 1.0, "Zn": 1.0})[1] < 130.0


def test_residual_does_not_bleed_across_an_alloying_element() -> None:
    # Sn3.0Cu0.5Ni 액상 394 ℃(Ni 때문)가 Ni 없는 Sn-3Cu로 번지면 안 된다.
    assert _element_mismatch_penalty({"Sn": 97, "Cu": 3}, {"Sn": 96.5, "Cu": 3, "Ni": 0.5}) == pytest.approx(1.0)
    assert _element_mismatch_penalty({"Sn": 99, "Ag": 1}, {"Sn": 98.985, "Ag": 1, "P": 0.015}) == pytest.approx(0.0, abs=0.01)
    _s, l = _p({"Sn": 96.999, "Cu": 3.0, "P": 0.001})
    assert l == pytest.approx(312.0, abs=3.0)


def test_group_holdout_accuracy_not_worse_than_before_p3() -> None:
    # P3 이전(엔진 v13, DB 80행): 고상 MAE 1.22 / p90 3.4, 액상 MAE 4.41 / p90 6.8 ℃.
    groups = _cluster_indices(DB)
    se, le = [], []
    for g in groups:
        train = [DB[i] for i in range(len(DB)) if i not in g]
        for i in g:
            s, l = _p(DB[i]["comp"], train)
            se.append(abs(s - DB[i]["solidus"]))
            le.append(abs(l - DB[i]["liquidus"]))

    def p90(x):
        x = sorted(x)
        return x[int(0.9 * (len(x) - 1))]

    assert sum(se) / len(se) <= 1.30 and p90(se) <= 3.4
    assert sum(le) / len(le) <= 4.41 and p90(le) <= 4.5
