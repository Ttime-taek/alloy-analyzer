"""Core comparison must stay independent of optional remote AI latency."""

from fastapi.testclient import TestClient

from test7 import api_server as api_module
from test7.analyzer import AlloyAnalyzer


client = TestClient(api_module.app)


def test_compare_endpoint_disables_ai_for_both_core_analyses(monkeypatch):
    # Regression: QA-004 — uncached comparisons waited up to 36.7 s on optional AI calls.
    # Found by /qa on 2026-08-12
    # Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
    calls = []

    class FakeEngine:
        def get_usage_snapshot(self):
            return {}

    class FakeAnalyzer:
        def compare_wetting_temp_c(self, _a, _b, _temp):
            return 250.0, "compare_shared"

        def analyze_all(self, comp, **kwargs):
            calls.append(dict(kwargs))
            return {
                "norm": dict(comp),
                "best": {"name": "fixture"},
                "confidence": 50.0,
                "solidus": 180.0,
                "liquidus": 200.0,
                "peak": 225.0,
                "props": {},
                "imc": [],
                "risk": [],
            }

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
    assert len(calls) == 2
    assert all(call["include_ai"] is False for call in calls)


def test_shared_wetting_liquidus_probe_disables_melting_ai():
    analyzer = object.__new__(AlloyAnalyzer)
    analyzer.validate_input_comp = lambda _comp: None
    analyzer.normalize = lambda comp: dict(comp)
    analyzer.find_best_match = lambda _norm: ({"name": "fixture"}, 0.0, 100.0)
    seen = []

    def fake_melting(_best, _norm, *, include_ai=True):
        seen.append(include_ai)
        return 180.0, 200.0, 225.0, 0, {}

    analyzer.calc_melting_with_detail = fake_melting

    assert analyzer.liquidus_for_comp({"Sn": 100.0}) == 200.0
    assert seen == [False]

