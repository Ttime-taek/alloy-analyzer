"""Analysis APIs must preserve source provenance already collected by the engine."""

from fastapi.testclient import TestClient

from test7 import api_server as api_module


client = TestClient(api_module.app)


def _fixture_result(comp: dict[str, float]) -> dict:
    return {
        "norm": dict(comp),
        "best": {"name": "fixture"},
        "confidence": 75.0,
        "solidus": 180.0,
        "liquidus": 200.0,
        "peak": 225.0,
        "props": {},
        "imc": [],
        "risk": [],
        "evidence": {
            "standards_refs": [
                {
                    "family": "IPC",
                    "id": "J-STD-006",
                    "note": "fixture standard",
                    "url": "https://www.ipc.org/ipc-standards",
                }
            ]
        },
        "ai_sources": ["https://doi.org/10.1000/fixture"],
        "ai_cited_sources": [],
        "retrieved_candidates": ["https://doi.org/10.1000/fixture"],
    }


def test_core_payload_keeps_retrieved_source_candidates_without_remote_ai():
    # Regression: the v1 core endpoint discarded deterministic literature candidates.
    result = _fixture_result({"Sn": 100.0})

    payload = api_module._core_result_payload(
        result,
        comp_input_wt_sum=100.0,
        composition_notes=[],
        prediction_contract={"analysis_id": "ana_fixture"},
    )

    assert payload["ai_used_this_request"] is False
    assert payload["ai_cited_sources"] == []
    assert payload["retrieved_candidates"] == ["https://doi.org/10.1000/fixture"]
    # Legacy clients still read this field when no AI citation exists.
    assert payload["ai_sources"] == ["https://doi.org/10.1000/fixture"]


def test_compare_response_keeps_evidence_and_sources_for_each_side(monkeypatch):
    # Regression: /api/compare dropped evidence and all source fields from both sides.
    class FakeEngine:
        def get_usage_snapshot(self):
            return {}

    class FakeAnalyzer:
        def compare_wetting_temp_c(self, _a, _b, _temp):
            return 250.0, "compare_shared"

        def analyze_all(self, comp, **_kwargs):
            return _fixture_result(dict(comp))

    monkeypatch.setattr(api_module, "_get_engine_bundle", lambda: (FakeEngine(), FakeAnalyzer()))
    monkeypatch.setattr(
        api_module,
        "_prediction_contract_builder",
        lambda: (lambda _result, _constraints: {"overall_state": "in_domain"}),
    )

    response = client.post(
        "/api/compare",
        json={"comp_a": {"Sn": 100.0}, "comp_b": {"Sn": 99.0, "Cu": 1.0}},
    )

    assert response.status_code == 200, response.text
    for side in ("a", "b"):
        result = response.json()[side]
        assert result["evidence"]["standards_refs"][0]["url"].startswith("https://")
        assert result["retrieved_candidates"] == ["https://doi.org/10.1000/fixture"]
        assert result["ai_cited_sources"] == []
        assert result["ai_sources"] == ["https://doi.org/10.1000/fixture"]
