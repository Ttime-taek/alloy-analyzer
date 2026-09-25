# Regression: 2026-09-25 계산 로직 점검 P3 — 과공정 Ag SAC 액상선이 이원 Sn-Ag 과공정 액상선을 그대로 써서
# 3원 공정 조성 Sn-3.7Ag-0.9Cu가 217/223.5 ℃, SAC387이 221.8 ℃, Sn-4.2Ag-0.7Cu가 228.2 ℃로 과대했다
# (홀드아웃 Sn3.9Ag0.6Cu +5.3, Sn-4.0Ag-0.5Cu +5.1 ℃).
# Found by 계산 로직 점검 (Claude) on 2026-09-25
from __future__ import annotations

import pytest

from test7.melting_predictor import hybrid_melting_predict
from test7.solder_db import SOLDER_DB

DB = [
    {"name": r["name"], "comp": r["comp"], "solidus": float(r["solidus"]), "liquidus": float(r["liquidus"])}
    for r in SOLDER_DB
]


def _liq(comp, db=DB):
    return float(hybrid_melting_predict(comp, db, ai_engine=None)[1])


@pytest.mark.parametrize(
    ("comp", "upper"),
    [
        ({"Sn": 95.4, "Ag": 3.7, "Cu": 0.9}, 220.5),   # 3원 공정 조성 (~217 ℃)
        ({"Sn": 95.5, "Ag": 3.8, "Cu": 0.7}, 220.0),   # SAC387 (문헌 217~218 ℃)
        ({"Sn": 95.1, "Ag": 4.2, "Cu": 0.7}, 223.0),
    ],
)
def test_hypereutectic_ag_sac_liquidus_not_overestimated(comp, upper) -> None:
    assert _liq(comp) <= upper


@pytest.mark.parametrize("name", ["Sn3.9Ag0.6Cu", "Sn-4.0Ag-0.5Cu-0.003Ni-0.0075Ge-0.0035P"])
def test_hypereutectic_ag_sac_holdout_within_3c(name) -> None:
    row = next(r for r in DB if r["name"] == name)
    train = [r for r in DB if abs(sum(abs(r["comp"].get(k, 0) - row["comp"].get(k, 0)) for k in set(r["comp"]) | set(row["comp"]))) > 0.3]
    assert _liq(row["comp"], train) == pytest.approx(row["liquidus"], abs=3.0)


def test_cu6sn5_surface_meets_ternary_eutectic() -> None:
    # Ag가 늘면 공정 Cu가 0.7 → 0.9 %로 이동. 이동을 빼면 이 조성에서 Cu6Sn5 면이 223.5 ℃로 올라왔다.
    assert _liq({"Sn": 95.4, "Ag": 3.7, "Cu": 0.9}, []) <= 220.5


def test_sac305_unchanged() -> None:
    assert _liq({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}) == pytest.approx(221.0, abs=0.5)
