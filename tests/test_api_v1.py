# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi.testclient import TestClient

from test7 import api_server as api_module
from test7.api_server import app


client = TestClient(app)


def test_v1_exact_db_value_keeps_registered_159_200_and_no_remote_ai():
    response = client.post(
        "/api/v1/analyses",
        json={
            "comp": {"Sn": 80.2, "Ag": 1.0, "Cu": 0.8, "In": 8.0, "Bi": 10.0},
            "mode": "eng",
            "literature_mode": "fast",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["result"]["solidus"] == 159.0
    assert data["result"]["liquidus"] == 200.0
    assert data["result"]["ai_mode"] == "not_requested"
    assert data["result"]["ai_used_this_request"] is False
    assert data["prediction_contract"]["melting_state"] == "exact_match"
    assert data["prediction_contract"]["overall_state"] == "out_of_domain"
    assert data["prediction_contract"]["properties"]["tensile_strength_mpa"]["state"] == "out_of_domain"
    assert data["prediction_contract"]["properties"]["liquidus_c"]["point"] == 200.0
    assert data["prediction_contract"]["process_recommendation"]["allowed"] is True


def test_v1_unregistered_composition_returns_range_and_process_policy():
    response = client.post(
        "/api/v1/analyses",
        json={"comp": {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0}},
    )

    assert response.status_code == 200, response.text
    contract = response.json()["prediction_contract"]
    interval = contract["properties"]["liquidus_c"]["interval"]
    assert contract["overall_state"] == "in_domain"
    assert interval["level"] == 0.9
    assert interval["lower"] < interval["upper"]
    assert contract["process_recommendation"]["production_ready"] is False


def test_v1_unknown_axis_refuses_peak_recommendation():
    response = client.post(
        "/api/v1/analyses",
        json={"comp": {"Sn": 98.9, "Ag": 0.5, "Cu": 0.5, "Au": 0.1}},
    )

    assert response.status_code == 200, response.text
    process = response.json()["prediction_contract"]["process_recommendation"]
    assert process["allowed"] is False
    assert process["recommended_peak_c"] is None


def test_v1_process_constraints_are_enforced_not_just_echoed():
    response = client.post(
        "/api/v1/analyses",
        json={
            "comp": {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0},
            "process_constraints": {
                "max_component_temp_c": 247.0,
                "oven_tolerance_c": 5.0,
            },
        },
    )

    assert response.status_code == 200, response.text
    process = response.json()["prediction_contract"]["process_recommendation"]
    assert process["safe_component_limit_c"] == 242.0
    assert process["allowed"] is False
    assert "PROCESS_LIMIT_EXCEEDED" in process["reason_codes"]


def test_v1_structured_error_for_bad_sum():
    response = client.post(
        "/api/v1/analyses",
        json={"comp": {"Sn": 90.0, "Ag": 3.0}},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "COMPOSITION_SUM_INVALID"


def test_explanation_rejects_path_body_analysis_id_mismatch_before_ai_call():
    response = client.post(
        "/api/v1/analyses/ana_path/explanations",
        json={
            "analysis_id": "ana_body_value",
            "comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ANALYSIS_ID_MISMATCH"


def test_v1_capabilities_and_models_publish_validation_contract():
    capabilities = client.get("/api/v1/capabilities")
    models = client.get("/api/v1/models")

    assert capabilities.status_code == 200
    assert capabilities.json()["unregistered_composition_prediction"] is True
    assert models.status_code == 200
    assert models.json()["validation"]["properties"]["liquidus_c"]["global"]["sample_count"] > 0


def test_analysis_id_binds_wetting_temperature_and_rejects_mismatched_explanation():
    composition = {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}
    at_250 = client.post(
        "/api/v1/analyses",
        json={"comp": composition, "wetting_temp_c": 250},
    )
    at_290 = client.post(
        "/api/v1/analyses",
        json={"comp": composition, "wetting_temp_c": 290},
    )

    assert at_250.status_code == 200, at_250.text
    assert at_290.status_code == 200, at_290.text
    analysis_250 = at_250.json()["analysis_id"]
    assert analysis_250 != at_290.json()["analysis_id"]

    mismatched = client.post(
        f"/api/v1/analyses/{analysis_250}/explanations",
        json={
            "analysis_id": analysis_250,
            "comp": composition,
            "wetting_temp_c": 290,
        },
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["detail"]["code"] == "ANALYSIS_BINDING_INVALID"


def test_explanation_keeps_melting_ai_disabled_and_only_enables_text_ai(monkeypatch):
    calls = []

    class FakeEngine:
        status_detail = "local test"

        def build_eng_report(self, _comp_str, _result, _knn):
            return "report"

        def get_usage_snapshot(self):
            return {}

    class FakeAnalyzer:
        def analyze_all(self, comp, **kwargs):
            calls.append(dict(kwargs))
            return {
                "norm": dict(comp),
                "ai_summary": "explanation",
                "ai_source": "local",
                "ai_used_this_request": False,
            }

        def find_knn(self, _norm, k=3):
            return []

    monkeypatch.setattr(
        api_module,
        "_get_engine_bundle",
        lambda: (FakeEngine(), FakeAnalyzer()),
    )
    monkeypatch.setattr(
        api_module,
        "_prediction_contract_builder",
        lambda: (lambda _result, _constraints, _context: {"analysis_id": "ana_expected_value"}),
    )
    monkeypatch.setattr(api_module, "_consume_explanation_quota", lambda _key: (True, 0))

    response = client.post(
        "/api/v1/analyses/ana_expected_value/explanations",
        json={
            "analysis_id": "ana_expected_value",
            "comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        },
    )

    assert response.status_code == 200, response.text
    assert calls[0]["include_ai"] is False
    assert calls[1]["include_ai"] is True
    assert calls[1]["include_melting_ai"] is False


def test_explanation_quota_returns_retry_after_when_window_is_full(monkeypatch):
    key = "pytest-rate-limit"
    monkeypatch.setattr(api_module, "_EXPLANATION_RATE_LIMIT", 2)
    monkeypatch.setattr(api_module, "_EXPLANATION_RATE_WINDOW_SEC", 60)
    with api_module._explanation_rate_lock:
        api_module._explanation_requests.pop(key, None)

    assert api_module._consume_explanation_quota(key) == (True, 0)
    assert api_module._consume_explanation_quota(key) == (True, 0)
    allowed, retry_after = api_module._consume_explanation_quota(key)

    assert allowed is False
    assert 1 <= retry_after <= 60
