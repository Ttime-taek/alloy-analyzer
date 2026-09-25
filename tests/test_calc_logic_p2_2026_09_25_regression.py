# Regression: 2026-09-25 계산 로직 점검 P2 — 저Ag·고Cu SAC 액상선이 Sn-Ag 액상선 + Cu 9 ℃/%로만
# 계산돼 Cu6Sn5 초정 영역을 크게 밑돌았다(Sn-0.3Ag-xCu: Cu 2.0 → 270, 2.5 → 248 ℃로 역전;
# Sn0.3Ag2.0Cu 홀드아웃 −25 ℃).
# Found by 계산 로직 점검 (Claude) on 2026-09-25
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


def _predict(comp, db=DB):
    solidus, liquidus, peak, _detail = hybrid_melting_predict(comp, db, ai_engine=None)
    return float(solidus), float(liquidus), float(peak)


@pytest.mark.parametrize("db", [DB, []], ids=["with_db", "no_db"])
def test_low_ag_high_cu_sac_liquidus_is_monotonic_in_cu(db) -> None:
    prev = None
    for cu in (0.8, 1.0, 1.5, 2.0, 2.5, 3.0):
        _s, liq, _p = _predict({"Sn": 99.7 - cu, "Ag": 0.3, "Cu": cu}, db)
        if prev is not None:
            assert liq >= prev - 0.5, f"Cu {cu}: liquidus {liq} fell below {prev}"
        prev = liq


def test_low_ag_high_cu_sac_follows_sn_cu_liquidus() -> None:
    # Ag 0.3 %는 Cu6Sn5 액상면을 거의 낮추지 않는다(Sn-3Cu 이원 약 312 ℃).
    _s, liq, _p = _predict({"Sn": 96.7, "Ag": 0.3, "Cu": 3.0})
    _s2, liq_bin, _p2 = _predict({"Sn": 97.0, "Cu": 3.0})
    assert liq == pytest.approx(liq_bin, abs=8.0)


def test_sn03ag2cu_holdout_liquidus_close_to_db() -> None:
    row = next(r for r in DB if r["name"] == "Sn0.3Ag2.0Cu")
    train = [r for r in DB if r is not row]
    _s, liq, _p = _predict(row["comp"], train)
    assert liq == pytest.approx(row["liquidus"], abs=8.0)


@pytest.mark.parametrize(
    ("comp", "liquidus"),
    [
        ({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, 221.0),   # SAC305 (DB)
        ({"Sn": 95.8, "Ag": 3.5, "Cu": 0.7}, 218.0),   # (DB)
    ],
)
def test_regular_sac_liquidus_unchanged(comp, liquidus) -> None:
    _s, liq, _p = _predict(comp)
    assert liq == pytest.approx(liquidus, abs=0.5)
