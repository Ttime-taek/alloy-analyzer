# -*- coding: utf-8 -*-
from __future__ import annotations

from test7.prediction_contract import build_prediction_contract
from test7.prediction_validation import calibration_report


def _result(*, distance=1.0, unknown=None):
    return {
        "norm": {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0},
        "solidus": 211.5,
        "liquidus": 220.2,
        "peak": 245.2,
        "props": {"tensile_strength": 76.8, "tensile_strength_basis": "db_priority"},
        "evidence": {
            "melting": {"best_dist": distance, "forced_db": False},
            "props_db": {"best_dist": distance, "support_n": 2, "top": []},
            "unknown_elements": {"names": unknown or [], "total_pct": 0.0},
        },
        "alloy_inference": {"neighbors": []},
    }


def test_group_holdout_calibration_exposes_real_sample_and_error_metrics():
    report = calibration_report()
    liquidus = report["properties"]["liquidus_c"]["global"]
    tensile = report["properties"]["tensile_strength_mpa"]["global"]

    assert liquidus["sample_count"] >= 50
    assert liquidus["p90_absolute_error"] > 0
    assert 0.80 <= liquidus["empirical_coverage"] <= 1.0
    assert tensile["sample_count"] >= 20
    assert tensile["p90_absolute_error"] > 0
    assert tensile["mae"] <= 8.6
    assert tensile["p90_absolute_error"] <= 18.0


def test_unregistered_in_domain_composition_gets_empirical_ranges():
    contract = build_prediction_contract(_result())

    assert contract["overall_state"] == "in_domain"
    liquidus = contract["properties"]["liquidus_c"]
    assert liquidus["interval"]["level"] == 0.90
    assert liquidus["interval"]["lower"] < liquidus["point"] < liquidus["interval"]["upper"]
    assert contract["process_recommendation"]["recommended_peak_c"] == 245.2
    assert contract["process_recommendation"]["production_ready"] is False


def test_unsupported_element_refuses_process_recommendation():
    contract = build_prediction_contract(_result(unknown=["Au"]))

    assert contract["overall_state"] == "out_of_domain"
    assert contract["process_recommendation"]["allowed"] is False
    assert contract["process_recommendation"]["recommended_peak_c"] is None
    assert "UNSUPPORTED_ELEMENT_AXIS" in contract["properties"]["liquidus_c"]["reason_codes"]


def test_component_limit_and_oven_tolerance_can_refuse_an_in_domain_peak():
    contract = build_prediction_contract(
        _result(),
        {"max_component_temp_c": 247.0, "oven_tolerance_c": 5.0},
    )

    process = contract["process_recommendation"]
    assert process["safe_component_limit_c"] == 242.0
    assert process["allowed"] is False
    assert process["recommended_peak_c"] is None
    assert "PROCESS_LIMIT_EXCEEDED" in process["reason_codes"]


def test_invalid_melting_order_is_a_data_quality_error():
    result = _result()
    result["peak"] = result["liquidus"]

    contract = build_prediction_contract(result)

    assert contract["overall_state"] == "data_quality_error"
    assert contract["properties"]["liquidus_c"]["usage"] == "refused"
    assert "INVALID_MELTING_ORDER" in contract["properties"]["liquidus_c"]["reason_codes"]


def test_analysis_id_changes_when_composition_changes():
    first = build_prediction_contract(_result())["analysis_id"]
    changed = _result()
    changed["norm"] = {"Sn": 94.0, "Ag": 2.5, "Cu": 0.5, "Bi": 3.0}
    second = build_prediction_contract(changed)["analysis_id"]

    assert first.startswith("ana_")
    assert first != second


def test_analysis_id_changes_when_result_affecting_context_changes():
    result = _result()
    result["props"]["wetting_temp_c"] = 250.0
    result["props"]["wetting_temp_basis"] = "user"
    base_context = {"mode": "eng", "literature_mode": "fast"}

    original = build_prediction_contract(result, analysis_context=base_context)
    lab = build_prediction_contract(
        result,
        analysis_context={**base_context, "mode": "lab"},
    )
    deep = build_prediction_contract(
        result,
        analysis_context={**base_context, "literature_mode": "deep"},
    )
    warmer = build_prediction_contract(
        result,
        analysis_context={
            **base_context,
            "wetting_temp_c": 290.0,
            "wetting_temp_basis": "user",
        },
    )

    assert original["analysis_context"]["wetting_temp_c"] == 250.0
    assert len({
        original["analysis_id"],
        lab["analysis_id"],
        deep["analysis_id"],
        warmer["analysis_id"],
    }) == 4
