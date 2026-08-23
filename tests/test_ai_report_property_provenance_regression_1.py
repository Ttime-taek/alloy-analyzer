"""Regression coverage for provenance-safe AI and local property reports."""

# Regression: ISSUE-010 — AI/local reports rendered missing mechanics as zero and
# presented legacy shear/wetting values as comparable measurements.
# Found by /qa on 2026-08-21.
# Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md

from __future__ import annotations

import json
import math

import pytest

from test7.ai_engine import AIEngine
from test7.analyzer import AlloyAnalyzer
from test7.solder_db import SOLDER_DB


def _legacy_result() -> dict:
    mechanical = {
        key: {
            "source_type": "legacy_property_db",
            "value_type": "legacy_measured_mean",
            "source_label": "DB(exact)",
            "verification_status": "unverified",
            "comparison_allowed": False,
        }
        for key in (
            "shear_strength",
            "tensile_strength",
            "yield_strength",
            "elongation",
        )
    }
    wetting = {
        "source_kind": "measured_db",
        "value_type": "direct_db_record",
        "verification_status": "unverified",
        "comparison_allowed": False,
    }
    return {
        "norm": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        "best": {"name": "Sn3.0Ag0.5Cu", "solidus": 217.0, "liquidus": 221.0},
        "solidus": 217.0,
        "liquidus": 221.0,
        "peak": 241.0,
        "score": 0.0,
        "confidence": 100.0,
        "confidence_overall": 82.09,
        "phase": "규칙 기반 상 해석",
        "imc": ["Ag3Sn", "Cu6Sn5"],
        "risk": [],
        "element_roles": "원소 역할 참고",
        "dopant_rec": "조성 규칙 기반 후보",
        "ai_summary": "로컬 요약",
        "ai_sources": [],
        "props": {
            "shear_strength": 0.0,
            "tensile_strength": None,
            "yield_strength": False,
            "elongation": {"malformed": True},
            "wetting_fmax_pred_mn": 2.32,
            "wetting_t0_pred_s": 0.71,
            "tensile_strength_db_mpa": None,
            "mechanical_property_metadata": mechanical,
            "shear_metadata": dict(mechanical["shear_strength"]),
            "wetting_metadata": wetting,
        },
        "evidence": {
            "mechanical_properties": {
                key: dict(value) for key, value in mechanical.items()
            },
            "wetting": {"source": "Measured(DB-exact)", **wetting},
        },
    }


@pytest.mark.parametrize(
    "value",
    [None, True, False, [], {}, (), math.nan, math.inf, -math.inf, 10**500],
)
def test_optional_measurement_rejects_missing_malformed_and_nonfinite(value) -> None:
    assert AIEngine._format_optional_measurement(value, 2, "MPa") == "N/A"


def test_optional_measurement_preserves_real_zero_and_strict_numeric_strings() -> None:
    assert AIEngine._format_optional_measurement(0, 2, "MPa") == "0.00 MPa"
    assert AIEngine._format_optional_measurement(" 1.25e1 ", 1, "MPa") == "12.5 MPa"
    assert AIEngine._format_optional_measurement("1_000", 1, "MPa") == "N/A"
    assert AIEngine._format_optional_measurement("nan", 1, "MPa") == "N/A"


def test_provenance_requires_allowlisted_identity_basis_and_consistent_copies() -> None:
    result = _legacy_result()
    assert "검증 보류" in AIEngine._mechanical_report_provenance(
        result, "tensile_strength"
    )
    assert "측정 DB(시험조건 미확인)" in AIEngine._wetting_report_provenance(
        result
    )

    verified_mechanical = {
        "source_type": "verified_property_db",
        "value_type": "verified_measured_mean",
        "source_identifier": "mechanical-series-42",
        "comparison_basis": "same-specimen-and-method",
        "verification_status": "verified",
        "comparison_allowed": True,
    }
    result["props"]["mechanical_property_metadata"]["tensile_strength"] = dict(
        verified_mechanical
    )
    result["evidence"]["mechanical_properties"]["tensile_strength"] = dict(
        verified_mechanical
    )
    assert AIEngine._mechanical_report_provenance(
        result, "tensile_strength"
    ).endswith("검증됨")

    # A stale/conflicting evidence copy must close the gate again.
    result["evidence"]["mechanical_properties"]["tensile_strength"][
        "comparison_basis"
    ] = "different-method"
    assert "검증 보류" in AIEngine._mechanical_report_provenance(
        result, "tensile_strength"
    )

    malformed = dict(verified_mechanical)
    malformed["source_type"] = {"malformed": True}
    assert AIEngine._mechanical_metadata_signature(malformed) is None

    result["props"]["mechanical_property_metadata"] = []
    result["evidence"]["mechanical_properties"]["tensile_strength"] = dict(
        verified_mechanical
    )
    assert "검증 보류" in AIEngine._mechanical_report_provenance(
        result, "tensile_strength"
    )


def test_wetting_report_verification_requires_matching_basis_and_temperature() -> None:
    # Regression: /qa ISSUE-014 — future verified wetting metadata could be labeled
    # verified even when the result temperature was absent or conflicted.
    # Found by /qa on 2026-08-21.
    result = _legacy_result()
    verified = {
        "source_kind": "measured_db",
        "value_type": "direct_db_record",
        "source_identifier": "wetting-series-7",
        "comparison_basis": "compare_shared",
        "verification_status": "verified",
        "comparison_allowed": True,
    }
    result["props"]["wetting_metadata"] = dict(verified)
    result["props"]["wetting_temp_basis"] = "compare_shared"
    result["props"]["wetting_temp_c"] = 250.0
    result["evidence"]["wetting"] = {**verified, "temperature_c": 250.0}

    assert AIEngine._wetting_report_provenance(result).endswith("검증됨")

    result["evidence"]["wetting"]["temperature_c"] = 290.0
    assert "검증 보류" in AIEngine._wetting_report_provenance(result)

    del result["evidence"]["wetting"]["temperature_c"]
    assert "검증 보류" in AIEngine._wetting_report_provenance(result)


def test_lab_and_simple_reports_render_reference_only_values_safely() -> None:
    engine = object.__new__(AIEngine)
    result = _legacy_result()
    result["props"]["tensile_strength_db_mpa"] = 19.0

    lab = engine.build_lab_report("Sn96.5Ag3Cu0.5", result, [])
    simple = engine.build_simple_eng_report("Sn96.5Ag3Cu0.5", result, [])

    assert "조성·융점·젖음 근거 신뢰도" in lab
    assert "종합 신뢰도" not in lab
    assert "전단강도: 0.00 MPa" in lab
    assert "인장강도: N/A" in lab
    assert "항복강도: N/A" in lab
    assert "연신율: N/A" in lab
    assert "물성 DB 인장: 19.00 MPa [보조 DB 추정 · 원출처·시험조건 미확인 · 검증 보류]" in lab
    assert "물성 DB 인장: 19.00 MPa [모델 예측" not in lab
    assert "젖음 Fmax: 2.32 mN [측정 DB(시험조건 미확인)" in lab
    assert "IDW·측정 DB" not in lab
    assert "정량 비교·추천 제외" in lab
    assert "실험 승인 전 생산 권장 아님" in lab

    assert "조성·융점·젖음 근거 신뢰도" in simple
    assert "전단: 0 MPa" in simple
    assert "인장: N/A" in simple
    assert "항복: N/A" in simple
    assert "연신: N/A" in simple
    assert "원출처·시험조건 검증 전 참고 전용" in simple


def test_exact_analyzer_report_calls_wetting_a_measurement_not_idw() -> None:
    analyzer = AlloyAnalyzer(SOLDER_DB)
    result = analyzer.analyze_all(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, include_ai=False
    )
    report = analyzer.ai.build_lab_report("Sn96.5Ag3Cu0.5", result, [])

    assert "젖음 Fmax: 2.32 mN [측정 DB(시험조건 미확인)" in report
    assert "IDW·측정 DB" not in report
    assert "기계물성 검증률이 아님" in report


def test_remote_analysis_prompt_and_output_preserve_property_trust_boundary(
    monkeypatch,
) -> None:
    engine = object.__new__(AIEngine)
    engine.available = True
    engine._cerebras = None
    engine.usage_stats = {}
    monkeypatch.setattr(engine, "_collect_literature_lines", lambda *_a, **_k: [])
    captured: list[str] = []

    def fake_ask(prompt, parse_list=False):
        captured.append(prompt)
        return json.dumps(
            {
                "phase": "충분히 긴 검증용 상 분석 설명이며 입력 조성의 규칙만 서술합니다.",
                "imc": ["Ag3Sn"],
                "roles": "충분히 긴 원소 역할 설명이며 미검증 물성을 사용하지 않습니다.",
                "dopant": "규칙 기반 후보를 시험합니다.",
                "summary": "원격 AI 요약입니다.",
                "sources": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(engine, "ask", fake_ask)
    result = _legacy_result()
    data = engine.get_full_analysis(
        result["norm"],
        "Sn96.5Ag3Cu0.5",
        result,
        [],
        mode="lab",
    )

    prompt = captured[0]
    assert "[PROPERTY_PROVENANCE_SAFETY" in prompt
    assert "검증되지 않은 물성으로 대소·순위·승자·개선률" in prompt
    assert "첨가제·공정·생산 적용을 추천하지 말라" in prompt
    assert "원출처·시험조건 검증 전까지 참고 전용" in data["summary"]
    assert "실험 승인이 필요" in data["dopant"]


def test_polish_prompt_and_output_keep_property_safety(monkeypatch) -> None:
    engine = object.__new__(AIEngine)
    engine.available = True
    engine.usage_stats = {}
    captured: list[str] = []

    def fake_ask(prompt, parse_list=False):
        captured.append(prompt)
        return json.dumps(
            {
                "phase": "충분히 긴 검증용 상 분석 설명입니다.",
                "imc": ["Ag3Sn"],
                "roles": "충분히 긴 원소 역할 설명입니다.",
                "dopant": "탐색 후보입니다.",
                "summary": "다듬은 요약입니다.",
                "sources": [],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(engine, "ask", fake_ask)
    data = engine._polish_rule_draft_with_ai(
        {
            "phase": "상 초안",
            "imc": ["Ag3Sn"],
            "roles": "역할 초안",
            "dopant": "첨가 초안",
            "summary": "요약 초안",
        },
        "lab",
        "Sn96.5Ag3Cu0.5",
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
    )

    assert data is not None
    assert "[PROPERTY_PROVENANCE_SAFETY" in captured[0]
    assert "승자·개선률을 새로 만들지 말라" in captured[0]
    assert "정량 비교·우열·개선률·추천 근거에서 제외" in data["summary"]
    assert "실험 승인이 필요" in data["dopant"]


def test_remote_property_numbers_and_recommendations_are_removed_not_just_warned() -> None:
    data = {
        "phase": "액상선 141℃라고 단정합니다. β-Sn 상이 관찰될 수 있습니다.",
        "roles": "Bi는 인장강도를 20 MPa 높입니다. Bi는 미세조직에 영향을 줍니다.",
        "summary": "액상선 141℃, 권장 피크 166℃입니다. 정성적 상 해석은 참고할 수 있습니다.",
        "dopant": "Bi 1% 첨가를 권장합니다.",
    }

    AIEngine._enforce_ai_property_safety(data)

    assert "141" not in data["phase"]
    assert "20 MPa" not in data["roles"]
    assert "166" not in data["summary"]
    assert "권장 피크" not in data["summary"]
    assert "정성적 상 해석" in data["summary"]
    assert "생산 추천이 아닙니다" in data["dopant"]
    assert "실험 승인이 필요" in data["dopant"]
    assert "Bi 1%" not in data["dopant"]
