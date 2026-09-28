"""Regression coverage for tensile values shared by single and compare APIs."""

import pytest
from fastapi.testclient import TestClient

from test7.api_server import app


client = TestClient(app)


def test_unregistered_alloy_tensile_matches_between_single_and_compare() -> None:
    """QA: comparison must not recalculate a different tensile prediction."""
    # Found during /qa follow-up on 2026-08-17.
    composition = {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0}

    single_response = client.post("/api/v1/analyses", json={"comp": composition})
    compare_response = client.post(
        "/api/compare",
        json={
            "comp_a": composition,
            "comp_b": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
            "literature_mode": "fast",
        },
    )

    assert single_response.status_code == 200, single_response.text
    assert compare_response.status_code == 200, compare_response.text

    single = single_response.json()["result"]
    compared = compare_response.json()["a"]
    single_tensile = single["props"]["tensile_strength"]
    compared_tensile = compared["props"]["tensile_strength"]

    # Unregistered compositions now retain the composition-model estimate;
    # the nearby DB value remains a separate reference-only field.
    # [2026-09-28 계산 로직 점검 P4] melting_predictor의 L1 최근접 DB 행 블렌드가
    # 2번째 이웃까지 섞도록 바뀌면서(경계 연속성 개선) 예측 고상·액상이 미세하게 바뀌었고,
    # 이 조성의 인장강도 모델도 그 값을 입력으로 써서 0.01 MPa 수준으로 같이 움직였다.
    # 이 테스트의 핵심은 단일/비교 API 간 일치(아래 비교)이므로 절대값은 갱신만 한다.
    assert single_tensile == pytest.approx(76.6003539485307)
    assert compared_tensile == pytest.approx(single_tensile)
    assert (
        compared["prediction_contract"]["properties"]["tensile_strength_mpa"]["usage"]
        == single["prediction_contract"]["properties"]["tensile_strength_mpa"]["usage"]
    )
