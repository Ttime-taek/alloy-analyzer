# Regression: 2026-09-25 계산 로직 점검 "남은 과제" — weak_support(검증 거리 q90~q99
# 사이)가 in_domain과 같은 90% 범위(p90_absolute_error)를 그대로 붙여서, 도메인 밖으로
# 갈수록 실제 오차가 커지는 것을 표현하지 못하고 위험을 과소평가했다.
# distance_q90→q99 구간에서 p90 → p95(없으면 ×1.3)로 선형 확대하도록 수정.
# Found by 계산 로직 점검 (Claude) on 2026-09-28
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from test7.api_server import app
from test7.prediction_contract import _interval

client = TestClient(app)


def test_weak_support_interval_is_wider_than_plain_p90_radius() -> None:
    profile = {
        "p90_absolute_error": 4.0,
        "p95_absolute_error": 8.0,
        "distance_q90": 1.0,
        "distance_q99": 3.0,
        "interval_kind": "empirical_group_holdout_absolute_residual_90pct",
    }
    in_domain = _interval(100.0, profile, exact=False, state="in_domain", distance=0.5)
    weak_near = _interval(100.0, profile, exact=False, state="weak_support", distance=1.0)
    weak_mid = _interval(100.0, profile, exact=False, state="weak_support", distance=2.0)
    weak_far = _interval(100.0, profile, exact=False, state="weak_support", distance=3.0)

    assert (in_domain["upper"] - in_domain["lower"]) == 8.0
    # 거리 q90에서는 in_domain과 같은 폭(경계에서 연속)이어야 한다.
    assert (weak_near["upper"] - weak_near["lower"]) == 8.0
    # q99에서는 p95 기반 폭(±8 -> 총 16)까지 넓어져야 한다.
    assert (weak_far["upper"] - weak_far["lower"]) == 16.0
    # 중간 지점은 그 사이(단조 증가)여야 한다.
    width_near = weak_near["upper"] - weak_near["lower"]
    width_mid = weak_mid["upper"] - weak_mid["lower"]
    width_far = weak_far["upper"] - weak_far["lower"]
    assert width_near < width_mid < width_far
    assert weak_far["kind"].endswith("_distance_widened")


def test_weak_support_falls_back_to_1_3x_when_p95_missing() -> None:
    profile = {
        "p90_absolute_error": 4.0,
        "distance_q90": 1.0,
        "distance_q99": 3.0,
    }
    out = _interval(100.0, profile, exact=False, state="weak_support", distance=3.0)
    assert (out["upper"] - out["lower"]) == pytest.approx(4.0 * 1.3 * 2)


def test_live_weak_support_alloy_has_widened_interval() -> None:
    # Sn70Bi25Cu5: 홀드아웃 검증 거리가 q90~q99 사이라 weak_support 상태다.
    resp = client.post("/api/v1/analyses", json={"comp": {"Sn": 70, "Bi": 25, "Cu": 5}})
    assert resp.status_code == 200, resp.text
    sol = resp.json()["result"]["prediction_contract"]["properties"]["solidus_c"]
    assert sol["state"] == "weak_support"
    interval = sol["interval"]
    assert interval is not None
    assert interval["kind"].endswith("_distance_widened")
    profile = sol["validation"]
    plain_width = 2.0 * float(profile["p90_absolute_error"])
    widened_width = interval["upper"] - interval["lower"]
    assert widened_width > plain_width - 1e-6
