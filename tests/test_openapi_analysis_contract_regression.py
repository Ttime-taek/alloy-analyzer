"""Regression coverage for the executable v1 Swagger contract."""
from __future__ import annotations

from fastapi.testclient import TestClient

from test7.api_server import AnalysisV1Request, app


# Regression: DX-001 — Swagger generated an invalid zero-total request example and an untyped response.
# Found by /devex-review on 2026-08-12.
# Report: .gstack/devex-reports/2026-08-12-devex-review.md
def test_v1_openapi_publishes_valid_example_and_typed_response() -> None:
    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    schema = spec["components"]["schemas"]["AnalysisV1Request"]
    example = schema["example"]

    validated = AnalysisV1Request.model_validate(example)
    assert round(sum(validated.comp.values()), 2) == 100.0
    assert "include_ai" not in schema["properties"]

    explanation_schema = spec["components"]["schemas"]["ExplanationV1Request"]
    assert "include_ai" not in explanation_schema["properties"]
    assert "include_wetting_grid" not in explanation_schema["properties"]

    response_schema = spec["paths"]["/api/v1/analyses"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/AnalysisV1Response")

    core_with_legacy_ai_flag = client.post(
        "/api/v1/analyses",
        json={**example, "include_ai": True},
    )
    explanation_with_legacy_ai_flag = client.post(
        "/api/v1/analyses/ana_example/explanations",
        json={
            "analysis_id": "ana_example",
            "comp": example["comp"],
            "include_ai": False,
            "include_wetting_grid": True,
        },
    )
    assert core_with_legacy_ai_flag.status_code == 422
    assert explanation_with_legacy_ai_flag.status_code == 422
