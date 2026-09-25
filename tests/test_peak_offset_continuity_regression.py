# Regression: 2026-09-25 계산 로직 점검 P2 — 권장 피크가 `20 if ΔT < 5 else 25`라 ΔT 5 ℃를
# 넘나들 때 5 ℃ 튀었다(Sn97.2Ag2.8 249.0 → Sn97.1Ag2.9 243.1).
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


def _peak(comp):
    return float(hybrid_melting_predict(comp, DB, ai_engine=None)[2])


def test_recommended_peak_is_continuous_across_5c_freezing_range() -> None:
    peaks = []
    ag = 2.70
    while ag <= 3.0 + 1e-9:
        peaks.append(_peak({"Sn": 100.0 - ag, "Ag": round(ag, 2)}))
        ag += 0.01
    steps = [abs(b - a) for a, b in zip(peaks, peaks[1:])]
    assert max(steps) < 2.0, f"peak step {max(steps):.1f} ℃"


@pytest.mark.parametrize(("dt", "offset"), [(2.0, 20.0), (4.0, 20.0), (5.0, 25.0), (12.0, 25.0)])
def test_peak_offset_matches_previous_rule_outside_transition(dt, offset) -> None:
    from test7.melting_predictor import _smoothstep01

    assert 20.0 + 5.0 * _smoothstep01(dt - 4.0) == pytest.approx(offset)
