"""Regression coverage for the legacy analysis cost boundary."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server as api_mod


class _FakeEngine:
    usage_stats: dict[str, int] = {}
    status_detail = ""

    @staticmethod
    def build_eng_report(_comp_str, _result, _knn):
        return "local report"

    @staticmethod
    def build_lab_report(_comp_str, _result, _knn):
        return "local lab report"

    @staticmethod
    def get_usage_snapshot():
        return {}


class _FakeAnalyzer:
    def __init__(self) -> None:
        self.include_ai_calls: list[bool] = []

    def analyze_all(self, comp, **kwargs):
        self.include_ai_calls.append(bool(kwargs.get("include_ai")))
        return {
            "norm": dict(comp),
            "best": {"name": "test-alloy"},
            "score": 0.0,
            "confidence": 100.0,
            "confidence_overall": 100.0,
            "solidus": 217.0,
            "liquidus": 219.0,
            "peak": 244.0,
            "phase": "local",
            "imc": [],
            "risk": [],
            "props": {},
            "melting_stage": 1,
            "melting_detail": {},
            "evidence": {},
            "ai_summary": "",
            "ai_sources": [],
            "ai_cited_sources": [],
            "retrieved_candidates": [],
            "ai_used_this_request": False,
            "ai_source": "local",
            "element_roles": "",
            "dopant_rec": "",
            "alloy_inference": {},
        }

    @staticmethod
    def find_knn(_norm, k=3):
        return []


# Regression: SECURITY-001 — legacy analysis triggered paid AI unless explicitly disabled.
# Found by /cso on 2026-08-12.
# Report: .gstack/security-reports/2026-08-12-155000.json
def test_legacy_analyze_requires_explicit_ai_opt_in() -> None:
    analyzer = _FakeAnalyzer()
    client = TestClient(api_mod.app)
    payload = {"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}}

    with patch.object(
        api_mod,
        "_get_engine_bundle",
        return_value=(_FakeEngine(), analyzer),
    ):
        default_response = client.post("/api/analyze", json=payload)
        opt_in_response = client.post(
            "/api/analyze",
            json={**payload, "include_ai": True},
        )

    assert default_response.status_code == 200, default_response.text
    assert opt_in_response.status_code == 200, opt_in_response.text
    assert analyzer.include_ai_calls == [False, True]
