# Regression: 2026-09-25 계산 로직 점검에서 "DB 정확 일치 절벽"으로 남겨둔 문제.
# L1(최근접 DB 행) 레이어가 단 하나의 최근접 행만 써서, 조성이 두 DB 행의 경계를
# 지날 때(1등·2등 행이 자리를 바꾸는 지점) 값이 계단으로 튀었다.
# 예: Sn100 + Ni 0.01 → 0.03 wt%에서 고상 231.8 → 227.1 ℃ (최근접 행이 "Sn100"에서
# "Sn-0.03Ni-0.015P"로 전환).
# Found by 계산 로직 점검 (Claude) on 2026-09-28
from __future__ import annotations

import pytest

from test7.melting_predictor import hybrid_melting_predict
from test7.solder_db import SOLDER_DB

DB = [
    {
        "name": row["name"],
        "comp": row["comp"],
        "solidus": float(row["solidus"]),
        "liquidus": float(row["liquidus"]),
    }
    for row in SOLDER_DB
]

MAX_STEP_C = 3.0


def _predict(comp, db=DB):
    solidus, liquidus, peak, _detail = hybrid_melting_predict(comp, db, ai_engine=None)
    return float(solidus), float(liquidus), float(peak)


def test_sn_ni_trace_scan_has_no_db_neighbor_cliff() -> None:
    prev = None
    for ni in (0.0001, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.05, 0.08, 0.1):
        s, l, _p = _predict({"Sn": 100.0 - ni, "Ni": ni})
        if prev is not None:
            ds = abs(s - prev[0])
            dl = abs(l - prev[1])
            assert ds < MAX_STEP_C, f"Ni {ni}: solidus step {ds:.1f} ℃"
            assert dl < MAX_STEP_C, f"Ni {ni}: liquidus step {dl:.1f} ℃"
        prev = (s, l)


def test_l1_blend_reduces_to_single_neighbor_when_far_from_second() -> None:
    # 2번째 이웃이 아주 멀면(수십 단위) 블렌드 영향은 무시할 수준이어야 한다.
    s, l, _p = _predict({"Sn": 100.0})
    assert s == pytest.approx(231.9, abs=0.05)
    assert l == pytest.approx(231.9, abs=0.05)


def test_random_perturbations_still_have_no_l1_neighbor_jumps() -> None:
    import random

    rng = random.Random(11)
    ranges = {
        "Ag": (0, 5), "Cu": (0, 3), "Bi": (0, 60), "In": (0, 20),
        "Sb": (0, 8), "Zn": (0, 10), "Pb": (0, 60), "Ni": (0, 0.3), "P": (0, 0.02),
    }
    worst = 0.0
    where = None
    for _ in range(300):
        k = rng.randint(1, 3)
        els = rng.sample(list(ranges), k)
        comp = {e: round(rng.uniform(*ranges[e]), 3) for e in els}
        if sum(comp.values()) > 70:
            continue
        comp["Sn"] = round(100 - sum(comp.values()), 3)
        e = rng.choice(els)
        comp2 = dict(comp)
        comp2[e] = round(comp[e] + 0.02, 3)
        comp2["Sn"] = round(comp["Sn"] - 0.02, 3)
        a = _predict(comp)
        b = _predict(comp2)
        step = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
        if step > worst:
            worst = step
            where = (comp, e)
    assert worst < 6.0, f"{worst:.1f} ℃ jump at {where}"
