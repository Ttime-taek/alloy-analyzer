"""Regression coverage for the executable v1 Swagger contract."""
from __future__ import annotations

from fastapi.testclient import TestClient

from test7.api_server import AnalysisV1Request, app


# Regression: DX-001 — Swagger generated an invalid zero-total request example and an untyped response.
# Found by /devex-review on 2026-08-12.
# Report: .gstack/devex-reports/2026-08-12-devex-review.md
def test_v1_openapi_publishes_valid_example_and_typed_response() -> None:
    spec = TestClient(app).get("/openapi.json").json()
    schema = spec["components"]["schemas"]["AnalysisV1Request"]
    example = schema["example"]

    validated = AnalysisV1Request.model_validate(example)
    assert round(sum(validated.comp.values()), 2) == 100.0

    response_schema = spec["paths"]["/api/v1/analyses"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/AnalysisV1Response")
