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

    assert single_tensile == pytest.approx(78.0)
    assert compared_tensile == pytest.approx(single_tensile)
    assert (
        compared["prediction_contract"]["properties"]["tensile_strength_mpa"]["usage"]
        == single["prediction_contract"]["properties"]["tensile_strength_mpa"]["usage"]
    )
