# Regression: 2026-09-30 계산 로직 2차 점검 — 젖음 평가 온도 계단.
#  1) 자동 평가 온도(액상선+30℃)를 DB 격자(250/260/…/290℃)로 스냅해, 목표가 285℃를 넘는 순간
#     280 → 290℃로 건너뛰며 점수가 튀었다: Sn-1.56Cu 44.7 → Sn-1.59Cu 33.5.
#  2) 점수를 '그 온도의 6개 합금 min–max'로 늘여서, 고온에서 Fmax 차이가 0.1 mN뿐인데도
#     10↔100점으로 벌어졌고 평가 온도가 몇 ℃만 움직여도 점수가 20점씩 흔들렸다.
# 이제 평가 온도는 250–290℃로 클램프만 하고(사이 온도는 레코드별 온도 보간),
# 점수 정규화는 DB 전체(모든 합금 × 모든 측정 온도) 범위로 고정한다.
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

import pytest

from test7.melting_predictor import hybrid_melting_predict
from test7.models import (
    PropertyModels,
    clamp_wetting_temp_to_db_range,
    compare_default_wetting_temp_c,
    default_wetting_temp_c,
)
from test7.solder_db import SOLDER_DB

M = PropertyModels()
DB = [
    {"name": r["name"], "comp": r["comp"], "solidus": float(r["solidus"]), "liquidus": float(r["liquidus"])}
    for r in SOLDER_DB
]


def _auto_score(comp):
    s, l, _p, _d = hybrid_melting_predict(comp, DB, ai_engine=None)
    d = M._predict_wetting_details(comp, s, l)
    return d["wetting_score"], d["wetting_temp_c"]


def test_default_temperature_is_clamped_not_snapped() -> None:
    assert default_wetting_temp_c(227.0) == pytest.approx(257.0)
    assert default_wetting_temp_c(254.9) == pytest.approx(284.9)
    assert default_wetting_temp_c(255.1) == pytest.approx(285.1)
    assert default_wetting_temp_c(139.0) == pytest.approx(250.0)
    assert default_wetting_temp_c(312.0) == pytest.approx(290.0)
    assert compare_default_wetting_temp_c(221.0, 225.0) == pytest.approx(255.0)
    assert clamp_wetting_temp_to_db_range(283.0) == pytest.approx(283.0)
    with pytest.raises(ValueError):
        default_wetting_temp_c(None)


def test_grid_temperature_row_is_unchanged_and_flagged() -> None:
    d = M._predict_wetting_at_single_temp({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, 250.0)
    assert d["fmax_pred_mn"] == pytest.approx(2.32)
    assert d["t0_pred_s"] == pytest.approx(0.71)
    assert d["wetting_metadata"]["temperature_interpolated"] is False
    mid = M._predict_wetting_at_single_temp({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, 255.0)
    assert mid["wetting_metadata"]["temperature_interpolated"] is True
    assert 2.32 < mid["fmax_pred_mn"] < 2.42


def test_score_is_continuous_in_evaluation_temperature() -> None:
    for comp in ({"Sn": 98.5, "Cu": 1.5}, {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, {"Sn": 99.3, "Cu": 0.7}):
        prev = None
        for i in range(81):
            v = M._predict_wetting_at_single_temp(comp, 250.0 + 0.5 * i)["wetting_score"]
            if prev is not None:
                assert abs(v - prev) < 4.0, (comp, 250.0 + 0.5 * i)
            prev = v


def test_high_temperature_scores_are_not_stretched_apart() -> None:
    # 290℃에서 DB 합금 Fmax는 2.43–2.60 mN으로 거의 같다 → 점수도 몰려 있어야 한다.
    scores = [
        M._predict_wetting_at_single_temp(c, 290.0)["wetting_score"]
        for c in (
            {"Sn": 99.3, "Cu": 0.7},
            {"Sn": 99.5, "Cu": 0.5},
            {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        )
    ]
    assert max(scores) - min(scores) < 15.0


def test_auto_score_has_no_step_where_target_crosses_285() -> None:
    # Sn-xCu: x ≈ 1.55–1.6 %에서 액상선+30 이 285℃를 넘는다(과거 280 → 290℃ 스냅).
    prev = None
    for i in range(101):
        x = 1.3 + 0.005 * i
        v, _t = _auto_score({"Sn": 100.0 - x, "Cu": x})
        if prev is not None:
            assert abs(v - prev) < 2.0, x
        prev = v
