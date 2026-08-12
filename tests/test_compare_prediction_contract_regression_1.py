"""Comparison results must retain the single-analysis prediction-use contract."""

from fastapi.testclient import TestClient

from test7.api_server import app


client = TestClient(app)


def test_compare_exposes_refused_out_of_domain_state_for_each_side():
    # Regression: QA-001 — comparison hid out-of-domain/refused values behind 100% confidence.
    # Found by /qa on 2026-08-12
    # Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
    response = client.post(
        "/api/compare",
        json={
            "comp_a": {"Sn": 80.2, "Ag": 1.0, "Cu": 0.8, "In": 8.0, "Bi": 10.0},
            "comp_b": {"Sn": 80.0, "Ag": 1.0, "Cu": 1.0, "In": 8.0, "Bi": 10.0},
            "literature_mode": "fast",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    for side in ("a", "b"):
        contract = data[side]["prediction_contract"]
        assert contract["overall_state"] == "out_of_domain"
        assert contract["overall_usage"] == "refused"
        assert contract["properties"]["tensile_strength_mpa"]["state"] == "out_of_domain"
