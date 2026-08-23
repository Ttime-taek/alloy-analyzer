"""Regression coverage for mechanical and wetting provenance contracts."""

# Regression: ISSUE-003 / ISSUE-005 / ISSUE-006
# Found by /qa on 2026-08-17.
# Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from test7.analyzer import AlloyAnalyzer
from test7 import ai_cache
from test7.analyzer import _AI_REPORT_POLICY_VERSION
from test7.api_server import app
from test7.db_regression import (
    get_statistics,
    parse_alloy,
    predict_shear_from_db_with_detail,
)
from test7.prediction_contract import build_prediction_contract
from test7.models import PropertyModels
from test7.solder_db import SOLDER_DB


client = TestClient(app)


@pytest.fixture(scope="module")
def analyzer() -> AlloyAnalyzer:
    return AlloyAnalyzer(SOLDER_DB)


@pytest.mark.parametrize(
    "alloy_name",
    ["Sn3.0Ag0.5Cu", "Sn3.0Ag0.5Cu3Bi"],
)
def test_exact_shear_detail_uses_only_the_measured_alloy(alloy_name: str) -> None:
    stats = get_statistics(alloy_name)
    detail = predict_shear_from_db_with_detail(parse_alloy(alloy_name))

    assert stats is not None
    assert stats["shear"] is not None
    assert detail["value"] == pytest.approx(stats["shear"]["mean"])
    assert detail["best_dist"] == pytest.approx(0.0)
    assert detail["top"] == [
        {
            "alloy": alloy_name,
            "dist": pytest.approx(0.0),
            "shear_mpa": pytest.approx(stats["shear"]["mean"]),
            "weight_share": pytest.approx(1.0),
        }
    ]


def test_shear_best_distance_ignores_exact_rows_without_shear() -> None:
    detail = predict_shear_from_db_with_detail(parse_alloy("Sn0.3Ag2.0Cu"))

    assert detail["value"] is not None
    assert detail["best_dist"] == pytest.approx(2.6)
    assert detail["best_dist"] == pytest.approx(
        min(float(item["dist"]) for item in detail["top"])
    )


@pytest.mark.parametrize(
    "comp",
    [
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        {"Sn": 93.5, "Ag": 3.0, "Cu": 0.5, "Bi": 3.0},
    ],
)
def test_exact_mechanical_values_keep_main_aux_and_provenance_consistent(
    analyzer: AlloyAnalyzer,
    comp: dict[str, float],
) -> None:
    result = analyzer.analyze_all(comp, include_ai=False)
    props = result["props"]
    metadata = props["mechanical_property_metadata"]

    assert props["shear_strength_db_mpa"] == pytest.approx(props["shear_strength"])
    assert props["shear_metadata"] == metadata["shear_strength"]
    assert metadata["shear_strength"]["value_type"] == "legacy_measured_mean"
    assert metadata["shear_strength"]["provenance_status"] == "unconfirmed"
    assert metadata["shear_strength"]["verification_status"] == "unverified"
    assert metadata["shear_strength"]["comparison_allowed"] is False
    assert result["evidence"]["mechanical_properties"] == metadata


def test_density_is_exposed_only_for_an_exact_registered_composition(
    analyzer: AlloyAnalyzer,
) -> None:
    exact = analyzer.analyze_all(
        {"Sn": 99.455, "Cu": 0.5, "Ni": 0.03, "P": 0.015},
        include_ai=False,
    )
    nearby = analyzer.analyze_all(
        {"Sn": 99.465, "Cu": 0.49, "Ni": 0.03, "P": 0.015},
        include_ai=False,
    )

    assert exact["score"] == pytest.approx(0.0)
    assert exact["props"]["density"] == pytest.approx(7.3)
    assert nearby["score"] > 0.0
    assert nearby["best"]["name"] == exact["best"]["name"]
    assert nearby["props"]["density"] is None


def test_wetting_metadata_distinguishes_exact_measurement_from_idw(
    analyzer: AlloyAnalyzer,
) -> None:
    exact = analyzer.analyze_all(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, include_ai=False
    )
    predicted = analyzer.analyze_all(
        {"Sn": 93.5, "Ag": 3.0, "Cu": 0.5, "Bi": 3.0}, include_ai=False
    )

    exact_meta = exact["props"]["wetting_metadata"]
    predicted_meta = predicted["props"]["wetting_metadata"]

    assert exact["props"]["wetting_fmax_pred_mn"] == 2.32
    assert exact["props"]["wetting_t0_pred_s"] == 0.71
    assert exact["props"]["wetting_neighbors"] == [
        {
            "name": "Sn3.0Ag0.5Cu",
            "dist": pytest.approx(0.0),
            "weight": pytest.approx(1.0),
            "weight_share": pytest.approx(1.0),
        }
    ]
    assert exact_meta == {
        "source_kind": "measured_db",
        "value_type": "direct_db_record",
        "exact_match": True,
        "nearest_distance": pytest.approx(0.0),
        "provenance_status": "unconfirmed",
        "verification_status": "unverified",
        "comparison_allowed": False,
        "reason_code": "WETTING_PROVENANCE_UNCONFIRMED",
        "missing_conditions": [
            "source_identifier",
            "test_standard",
            "substrate_and_finish",
            "test_atmosphere",
            "flux_amount",
            "replicate_count",
        ],
        "neighbor_semantics": "value_contributors_v2",
        "confidence_neighbor_semantics": "distance_support_v1",
    }
    assert predicted_meta["source_kind"] == "idw_prediction"
    assert predicted_meta["value_type"] == "idw_prediction"
    assert predicted_meta["exact_match"] is False
    assert predicted_meta["nearest_distance"] == pytest.approx(5.94)
    assert predicted_meta["provenance_status"] == "unconfirmed"
    assert predicted_meta["verification_status"] == "unverified"
    assert predicted_meta["comparison_allowed"] is False
    assert predicted["props"]["wetting_fmax_pred_mn"] == pytest.approx(
        1.9420975102139408, rel=0.0, abs=1e-15
    )
    assert predicted["props"]["wetting_t0_pred_s"] == pytest.approx(
        1.0876494427841128, rel=0.0, abs=1e-15
    )

    for result, expected in ((exact, exact_meta), (predicted, predicted_meta)):
        evidence = result["evidence"]["wetting"]
        for key, value in expected.items():
            assert evidence[key] == value
    assert exact["evidence"]["wetting"]["source"] == "Measured(DB-exact)"
    assert predicted["evidence"]["wetting"]["source"] == "IDW(DB)"


def test_compare_api_preserves_property_provenance_metadata() -> None:
    response = client.post(
        "/api/compare",
        json={
            "comp_a": {"Sn": 93.5, "Ag": 3.0, "Cu": 0.5, "Bi": 3.0},
            "comp_b": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
            "literature_mode": "fast",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["a"]["props"]["shear_metadata"]["comparison_allowed"] is False
    assert data["b"]["props"]["shear_metadata"]["verification_status"] == "unverified"
    assert data["a"]["evidence"]["mechanical_properties"] == (
        data["a"]["props"]["mechanical_property_metadata"]
    )
    assert data["a"]["evidence"]["wetting"]["source_kind"] == "idw_prediction"
    assert data["b"]["evidence"]["wetting"]["source_kind"] == "measured_db"


def test_prediction_contract_keeps_exact_distance_separate_from_provenance() -> None:
    response = client.post(
        "/api/v1/analyses",
        json={"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}},
    )

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    tensile = result["prediction_contract"]["properties"]["tensile_strength_mpa"]

    assert tensile["state"] == "exact_match"
    assert tensile["usage"] == "reference"
    assert tensile["provenance_status"] == "unconfirmed"
    assert tensile["verification_status"] == "unverified"
    assert tensile["comparison_allowed"] is False
    assert "MECHANICAL_PROVENANCE_UNVERIFIED" in tensile["reason_codes"]
    assert tensile["evidence"]["provenance"] == (
        result["props"]["mechanical_property_metadata"]["tensile_strength"]
    )


def test_prediction_contract_fails_closed_when_tensile_provenance_is_missing() -> None:
    # Regression: /qa ISSUE-010 — a v1.2 contract omitted the comparison gate when
    # callers supplied legacy analysis results without mechanical metadata.
    # Found by /qa on 2026-08-21.
    result = {
        "norm": {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0},
        "solidus": 211.5,
        "liquidus": 220.2,
        "peak": 245.2,
        "props": {"tensile_strength": 76.8, "tensile_strength_basis": "db_priority"},
        "evidence": {
            "melting": {"best_dist": 1.0, "forced_db": False},
            "props_db": {"best_dist": 1.0, "support_n": 2, "top": []},
            "unknown_elements": {"names": [], "total_pct": 0.0},
        },
        "alloy_inference": {"neighbors": []},
    }

    tensile = build_prediction_contract(result)["properties"]["tensile_strength_mpa"]

    assert tensile["provenance_status"] == "unknown"
    assert tensile["verification_status"] == "unverified"
    assert tensile["comparison_allowed"] is False
    assert tensile["evidence"]["provenance"] == {}
    assert "MECHANICAL_PROVENANCE_UNVERIFIED" in tensile["reason_codes"]


def test_prediction_contract_requires_a_coherent_verified_tensile_identity(
    analyzer: AlloyAnalyzer,
) -> None:
    # Regression: /qa ISSUE-011 — crossed source/value pairs or conflicting aliases
    # could otherwise turn an untrusted mechanical value into a comparable one.
    # Found by /qa on 2026-08-21.
    result = analyzer.analyze_all(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, include_ai=False
    )
    meta = result["props"]["mechanical_property_metadata"]["tensile_strength"]
    meta.update(
        {
            "source_type": "verified_property_db",
            "value_type": "verified_measured_mean",
            "verification_status": "verified",
            "comparison_allowed": True,
            "source_identifier": "series-42",
            "comparison_basis": "same-specimen-and-method",
        }
    )
    result["evidence"]["mechanical_properties"]["tensile_strength"] = dict(meta)
    assert (
        build_prediction_contract(result)["properties"]["tensile_strength_mpa"][
            "comparison_allowed"
        ]
        is True
    )

    meta.update({"source_type": "literature", "value_type": "measured"})
    assert (
        build_prediction_contract(result)["properties"]["tensile_strength_mpa"][
            "comparison_allowed"
        ]
        is False
    )

    meta.update(
        {
            "source_type": "verified_property_db",
            "value_type": "verified_measured_mean",
        }
    )
    meta.pop("source_id", None)
    result["evidence"]["mechanical_properties"]["tensile_strength"] = dict(meta)
    assert (
        build_prediction_contract(result)["properties"]["tensile_strength_mpa"][
            "comparison_allowed"
        ]
        is True
    )

    meta["source_id"] = None
    result["evidence"]["mechanical_properties"]["tensile_strength"] = dict(meta)
    assert (
        build_prediction_contract(result)["properties"]["tensile_strength_mpa"][
            "comparison_allowed"
        ]
        is False
    )

    meta.update(
        {
            "source_type": "verified_property_db",
            "value_type": "verified_measured_mean",
            "source_id": "conflicting-series",
        }
    )
    result["evidence"]["mechanical_properties"]["tensile_strength"] = dict(meta)
    assert (
        build_prediction_contract(result)["properties"]["tensile_strength_mpa"][
            "comparison_allowed"
        ]
        is False
    )


def test_prediction_contract_rejects_boolean_and_overflow_numeric_payloads(
    analyzer: AlloyAnalyzer,
) -> None:
    # Regression: /qa ISSUE-012 — bool became 0/1 and huge integers could raise
    # OverflowError at the public contract boundary.
    # Found by /qa on 2026-08-21.
    result = analyzer.analyze_all(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, include_ai=False
    )
    result["solidus"] = 10**1000
    result["props"]["tensile_strength"] = False

    properties = build_prediction_contract(result)["properties"]

    assert properties["solidus_c"]["point"] is None
    assert properties["tensile_strength_mpa"]["point"] is None


def test_property_model_failures_and_missing_liquidus_remain_unavailable() -> None:
    models = PropertyModels()
    comp = {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}

    unavailable = models.predict_all(comp, None, None)
    assert unavailable["tensile_strength"] is None
    assert unavailable["yield_strength"] is None
    assert unavailable["elongation"] is None
    assert unavailable["shear_strength"] is None
    assert unavailable["wetting_score"] is None
    assert "wetting_temp_c" not in unavailable

    explicit_temperature = models.predict_all(
        comp, None, None, wetting_temp_c=250.0, wetting_temp_basis="user"
    )
    assert explicit_temperature["wetting_temp_c"] == pytest.approx(250.0)
    assert explicit_temperature["wetting_fmax_pred_mn"] == pytest.approx(2.32)
    assert explicit_temperature["wetting_t0_pred_s"] == pytest.approx(0.71)


def test_partial_wetting_details_do_not_turn_missing_fields_into_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = PropertyModels()
    monkeypatch.setattr(
        models,
        "_predict_wetting_details",
        lambda *args, **kwargs: {
            "wetting_score": None,
            "wetting_temp_c": 250.0,
            "fmax_pred_mn": None,
            "t0_pred_s": None,
        },
    )

    props = models.predict_all(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, 217.0, 221.0
    )
    assert props["wetting_score"] is None
    assert props["wetting_temp_c"] == pytest.approx(250.0)
    assert props["wetting_fmax_pred_mn"] is None
    assert props["wetting_t0_pred_s"] is None


def test_compare_wetting_temperature_refuses_a_missing_liquidus(
    analyzer: AlloyAnalyzer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        analyzer,
        "calc_melting_with_detail",
        lambda *args, **kwargs: (None, None, None, 5, {}),
    )

    with pytest.raises(ValueError, match="액상선"):
        analyzer.liquidus_for_comp({"Sn": 100.0})


def test_unregistered_far_composition_keeps_model_tensile_not_remote_db(
    analyzer: AlloyAnalyzer,
) -> None:
    result = analyzer.analyze_all({"Sn": 50.0, "In": 50.0}, include_ai=False)
    props = result["props"]

    assert result["evidence"]["props_db"]["best_dist"] > 3.0
    assert props["tensile_strength_basis"] == "model_prediction"
    assert props["tensile_strength"] == pytest.approx(
        props["tensile_strength_model_mpa"]
    )
    assert props["tensile_strength"] != pytest.approx(
        props["tensile_strength_db_mpa"]
    )


def test_unsourced_literature_proxy_does_not_modify_high_bi_prediction(
    analyzer: AlloyAnalyzer,
) -> None:
    result = analyzer.analyze_all(
        {"Sn": 73.3, "Ag": 1.0, "Cu": 0.7, "Bi": 25.0}, include_ai=False
    )

    assert result["props"].get("tensile_strength_lit_mpa") is None
    assert not str(result["evidence"]["props"]["yield_strength"]).startswith("LIT")


def test_prediction_contract_rejects_truthy_string_forced_db() -> None:
    result = {
        "norm": {"Sn": 100.0},
        "solidus": 232.0,
        "liquidus": 232.1,
        "peak": 257.1,
        "props": {"tensile_strength": 15.0},
        "evidence": {
            "melting": {"best_dist": 999.0, "forced_db": "false"},
            "props_db": {"best_dist": 999.0},
            "unknown_elements": {"names": []},
        },
    }

    contract = build_prediction_contract(result)
    assert contract["properties"]["solidus_c"]["state"] != "exact_match"
    assert contract["process_recommendation"]["allowed"] is False


def test_prediction_contract_never_compares_a_missing_tensile_value(
    analyzer: AlloyAnalyzer,
) -> None:
    result = analyzer.analyze_all(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, include_ai=False
    )
    verified = {
        "source_type": "verified_property_db",
        "value_type": "verified_measured_mean",
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "series-42",
        "comparison_basis": "ASTM-E8-same-condition",
    }
    result["props"]["tensile_strength"] = None
    result["props"]["mechanical_property_metadata"]["tensile_strength"] = dict(verified)
    result["evidence"]["mechanical_properties"]["tensile_strength"] = dict(verified)

    tensile = build_prediction_contract(result)["properties"]["tensile_strength_mpa"]
    assert tensile["point"] is None
    assert tensile["state"] == "unavailable"
    assert tensile["comparison_allowed"] is False


def test_ai_cache_key_invalidates_older_report_safety_policy(
    analyzer: AlloyAnalyzer, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}
    original_make_key = ai_cache.make_key

    def capture_key(*args, **kwargs):
        captured["extra"] = str(kwargs.get("extra") or "")
        return original_make_key(*args, **kwargs)

    monkeypatch.setattr(ai_cache, "make_key", capture_key)
    analyzer.analyze_all(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, include_ai=False
    )

    assert f"report_policy={_AI_REPORT_POLICY_VERSION}" in captured["extra"]
