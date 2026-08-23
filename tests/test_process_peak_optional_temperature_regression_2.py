"""Regression: recommendation gates and missing temperatures must fail closed."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from test7 import api_server as api_module
from test7.ai_engine import AIEngine


client = TestClient(api_module.app)


def _report_result(*, process: dict | None = None) -> dict:
    result = {
        "norm": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        "best": {"name": "Sn3.0Ag0.5Cu", "solidus": 217.0, "liquidus": 221.0},
        "solidus": 217.0,
        "liquidus": 221.0,
        "peak": 241.0,
        "score": 0.0,
        "confidence": 100.0,
        "confidence_overall": 82.0,
        "props": {},
        "evidence": {},
        "phase": "phase",
        "imc": [],
        "risk": [],
    }
    if process is not None:
        result["prediction_contract"] = {"process_recommendation": process}
    return result


@pytest.mark.parametrize(
    "process",
    [None, {}, {"allowed": False}, {"allowed": 1}, {"allowed": "true"}],
)
def test_reports_label_raw_peak_as_reference_when_contract_does_not_allow(process) -> None:
    engine = object.__new__(AIEngine)
    result = _report_result(process=process)

    lab = engine.build_lab_report("Sn96.5Ag3Cu0.5", result, [])
    simple = engine.build_simple_eng_report("Sn96.5Ag3Cu0.5", result, [])

    assert "엔진 참고 피크 · 추천 보류: 241.00 ℃" in lab
    assert "권장 피크 온도" not in lab
    assert "엔진 참고 피크 · 추천 보류: 약 241 ℃" in simple
    assert "권장 피크 온도" not in simple


def test_reports_use_contract_recommended_peak_only_when_allowed_is_exact_true() -> None:
    engine = object.__new__(AIEngine)
    result = _report_result(
        process={"allowed": True, "recommended_peak_c": 245.2}
    )

    lab = engine.build_lab_report("Sn96.5Ag3Cu0.5", result, [])
    simple = engine.build_simple_eng_report("Sn96.5Ag3Cu0.5", result, [])

    assert "권장 피크 온도: 245.20 ℃" in lab
    assert "추천 보류" not in lab
    assert "권장 피크 온도: 약 245 ℃" in simple
    assert "추천 보류" not in simple


def test_report_missing_temperatures_render_na_not_zero() -> None:
    engine = object.__new__(AIEngine)
    result = _report_result(process={"allowed": False})
    result.update({"solidus": None, "liquidus": None, "peak": None})

    lab = engine.build_lab_report("fixture", result, [])
    simple = engine.build_simple_eng_report("fixture", result, [])

    assert "고상선 온도(최종): N/A" in lab
    assert "액상선 온도(최종): N/A" in lab
    assert "액상 구간(ΔT): N/A" in lab
    assert "엔진 참고 피크 · 추천 보류: N/A" in lab
    assert "약 0 ℃" not in simple
    assert "0.00 ℃" not in lab


def test_remote_prompt_separates_final_prediction_from_nearest_db_and_keeps_gate(
    monkeypatch,
) -> None:
    engine = object.__new__(AIEngine)
    engine.available = True
    engine._cerebras = None
    engine.usage_stats = {}
    captured: list[str] = []
    monkeypatch.setattr(engine, "_collect_literature_lines", lambda *_a, **_k: [])

    def fake_ask(prompt, parse_list=False):
        captured.append(prompt)
        return json.dumps(
            {
                "phase": "충분히 긴 상 분석 설명입니다.",
                "imc": ["Ag3Sn"],
                "roles": "충분히 긴 원소 역할 설명입니다.",
                "dopant": "규칙 기반 후보는 실험으로 검증합니다.",
                "summary": "원격 요약",
                "sources": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(engine, "ask", fake_ask)
    data = engine.get_full_analysis(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        "Sn96.5Ag3Cu0.5",
        _report_result(process={"allowed": False}),
        [],
        mode="lab",
    )

    prompt = captured[0]
    assert "[최근접 DB 참고 합금 — 최종 예측과 구분]" in prompt
    assert "[최종 예측 온도 — 엄격한 유한값, 누락은 N/A]" in prompt
    assert "고상선: 217.00 ℃" in prompt
    assert "액상선: 221.00 ℃" in prompt
    assert "엔진 참고 피크 · 추천 보류: 241.00 ℃" in prompt
    assert "allowed가 명시적으로 true가 아니면" in prompt
    assert "공정 피크 상태: 엔진 참고 피크 · 추천 보류: 241.00 ℃" in data["summary"]


@pytest.mark.parametrize(
    "value",
    [None, True, False, "", [], {}, float("nan"), float("inf"), 10**500],
)
def test_api_optional_temperature_rejects_missing_malformed_and_nonfinite(value) -> None:
    assert api_module._optional_finite_float(value) is None


def test_core_payload_preserves_missing_temperatures_and_real_zero() -> None:
    missing = api_module._core_result_payload(
        {"solidus": None, "liquidus": None, "peak": None},
        comp_input_wt_sum=100.0,
        composition_notes=[],
        prediction_contract={},
    )
    zero = api_module._core_result_payload(
        {"solidus": 0.0, "liquidus": 0.0, "peak": 0.0},
        comp_input_wt_sum=100.0,
        composition_notes=[],
        prediction_contract={},
    )

    assert (missing["solidus"], missing["liquidus"], missing["peak"]) == (
        None,
        None,
        None,
    )
    assert (zero["solidus"], zero["liquidus"], zero["peak"]) == (0.0, 0.0, 0.0)


def test_legacy_and_compare_responses_preserve_missing_temperatures(monkeypatch) -> None:
    seen_report_contracts: list[dict] = []

    class FakeEngine:
        usage_stats = {}
        status_detail = "fixture"

        def build_eng_report(self, _comp_str, result, _knn):
            seen_report_contracts.append(result.get("prediction_contract"))
            return "report"

        def build_lab_report(self, _comp_str, result, _knn):
            seen_report_contracts.append(result.get("prediction_contract"))
            return "lab report"

        def get_usage_snapshot(self):
            return {}

    class FakeAnalyzer:
        def analyze_all(self, comp, **_kwargs):
            return {
                "norm": dict(comp),
                "best": {"name": "fixture"},
                "solidus": None,
                "liquidus": None,
                "peak": None,
                "props": {},
                "imc": [],
                "risk": [],
            }

        def find_knn(self, _norm, k=3):
            return []

        def compare_wetting_temp_c(self, _a, _b, _temp):
            return 250.0, "compare_shared"

    contract = {
        "analysis_id": "ana_fixture",
        "process_recommendation": {"allowed": False},
    }
    monkeypatch.setattr(
        api_module, "_get_engine_bundle", lambda: (FakeEngine(), FakeAnalyzer())
    )
    monkeypatch.setattr(
        api_module,
        "_prediction_contract_builder",
        lambda: (lambda _result, _constraints, _context: dict(contract)),
    )

    legacy = client.post(
        "/api/analyze",
        json={"comp": {"Sn": 100.0}, "mode": "lab"},
    )
    compared = client.post(
        "/api/compare",
        json={"comp_a": {"Sn": 100.0}, "comp_b": {"Sn": 99.0, "Cu": 1.0}},
    )

    assert legacy.status_code == 200, legacy.text
    legacy_data = legacy.json()
    assert (legacy_data["solidus"], legacy_data["liquidus"], legacy_data["peak"]) == (
        None,
        None,
        None,
    )
    assert legacy_data["prediction_contract"]["process_recommendation"]["allowed"] is False
    assert all(item["process_recommendation"]["allowed"] is False for item in seen_report_contracts)

    assert compared.status_code == 200, compared.text
    for side in ("a", "b"):
        assert (
            compared.json()[side]["solidus"],
            compared.json()[side]["liquidus"],
            compared.json()[side]["peak"],
        ) == (None, None, None)
