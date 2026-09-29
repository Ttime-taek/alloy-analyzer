# Regression: 2026-09-30 계산 로직 2차 점검 P1 — 젖음 IDW가 1/거리(멱 1)에 Cu 0.55–0.72 %만
# 바닥 0.035를 둬서, 정확일치 행 값으로 수렴하지 않았다: Sn0.7Cu 젖음 점수 10.0 →
# Cu +0.01 %에 15.2, +0.1 %에 27.6.
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

import pytest

from test7.models import PropertyModels

M = PropertyModels()


@pytest.mark.parametrize(
    ("exact", "near"),
    [
        ({"Sn": 99.3, "Cu": 0.7}, {"Sn": 99.29, "Cu": 0.71}),
        ({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, {"Sn": 96.49, "Ag": 3.01, "Cu": 0.5}),
        ({"Sn": 99.0, "Ag": 0.3, "Cu": 0.7}, {"Sn": 98.99, "Ag": 0.3, "Cu": 0.71}),
    ],
)
@pytest.mark.parametrize("temp", [250, 270, 290])
def test_wetting_exact_row_and_neighbor_agree(exact, near, temp) -> None:
    a = M._predict_wetting_at_single_temp(exact, temp)
    b = M._predict_wetting_at_single_temp(near, temp)
    assert b["wetting_score"] == pytest.approx(a["wetting_score"], abs=0.5)
    assert b["fmax_pred_mn"] == pytest.approx(a["fmax_pred_mn"], abs=0.02)


def test_wetting_scan_across_old_cu_window_edges_is_smooth() -> None:
    for base in ({}, {"Ag": 0.3}, {"Ag": 1.0}):
        prev = None
        for i in range(0, 401):
            cu = 0.4 + i * 0.001
            comp = dict(base, Cu=cu)
            comp["Sn"] = 100.0 - sum(comp.values())
            s = M._predict_wetting_at_single_temp(comp, 260)["wetting_score"]
            if prev is not None:
                assert abs(s - prev) < 0.5, (base, cu)
            prev = s


def test_idw_weight_ignores_cu_window() -> None:
    assert PropertyModels._idw_comp_weight(0.3, {"Cu": 0.6}) == PropertyModels._idw_comp_weight(0.3, {"Cu": 0.3})
