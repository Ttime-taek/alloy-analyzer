"""Regression coverage for provenance-safe desktop property displays."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from test7.analyzer import AlloyAnalyzer
from test7.gui import (
    AlloyGUI,
    _RADAR_PROPERTY_AXES,
    _mechanical_pair_comparison_allowed,
    _mechanical_provenance_text,
    _optional_finite_float,
    _reflow_property_info,
    _wetting_pair_comparison_allowed,
    _wetting_source_label,
)
from test7.solder_db import SOLDER_DB


# Regression: ISSUE-007 — desktop comparison ranked unverified raw properties.
# Found by /qa on 2026-08-21.
# Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-17.md


class _TextCapture:
    def __init__(self):
        self.chunks = []

    def config(self, **_kwargs):
        return None

    def tag_remove(self, *_args):
        return None

    def delete(self, *_args):
        self.chunks = []

    def insert(self, _index, text, *_tags):
        self.chunks.append(str(text))

    def see(self, *_args):
        return None

    @property
    def text(self):
        return "".join(self.chunks)


@pytest.fixture(scope="module")
def analyzer() -> AlloyAnalyzer:
    return AlloyAnalyzer(SOLDER_DB)


def _report_gui(analyzer: AlloyAnalyzer, goal: str = "균형") -> AlloyGUI:
    gui = AlloyGUI.__new__(AlloyGUI)
    gui.analyzer = analyzer
    gui.ai = None
    gui.reco_goal = SimpleNamespace(get=lambda: goal)
    gui.wetting_temp_mode = SimpleNamespace(get=lambda: "AUTO(Liq+30)")
    return gui


def test_compare_report_blocks_unverified_deltas_winners_and_recommendations(
    analyzer: AlloyAnalyzer,
) -> None:
    gui = _report_gui(analyzer)
    comp_a = {"Sn": 93.5, "Ag": 3.0, "Cu": 0.5, "Bi": 3.0}
    comp_b = {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}
    result_a = analyzer.analyze_all(comp_a, include_ai=False)
    result_b = analyzer.analyze_all(comp_b, include_ai=False)
    gui.comp = comp_a
    gui.compare_comp = comp_b
    gui._apply_compare_shared_wetting(result_a, result_b)

    report = gui._build_compare_report(comp_a, comp_b, result_a, result_b)

    assert "전단강도 (A DB 평균 / B DB 평균) (MPa)\t28.00 MPa\t84.50 MPa\t검증 보류" in report
    assert "인장강도 (A DB 평균 / B DB 평균) (MPa)\t78.00 MPa\t48.50 MPa\t검증 보류" in report
    assert "28.00 MPa ▲" not in report
    assert "84.50 MPa ▲" not in report
    assert "+56.50 MPa" not in report
    assert "A IDW 예측(검증 보류) / B 측정 DB(시험조건 미확인)" in report
    assert "\t1.94 mN\t2.32 mN\t비교 보류" in report
    assert "시험조건·출처 미확인 물성과 비교 보류 젖음값은 추천 점수에서 제외" in report
    assert "강도열세" not in report
    assert "Fmax열세" not in report
    assert "Δ인장" not in report
    assert "Δ전단" not in report
    assert "ΔFmax" not in report


def test_compare_report_renders_missing_as_na_but_preserves_real_zero(
    analyzer: AlloyAnalyzer,
) -> None:
    gui = _report_gui(analyzer)
    unverified = {
        "comparison_allowed": False,
        "verification_status": "unverified",
        "source_type": "legacy_property_db",
        "value_type": "legacy_measured_mean",
    }
    result_a = {
        "norm": {"Sn": 100.0},
        "props": {
            "tensile_strength": None,
            "mechanical_property_metadata": {"tensile_strength": unverified},
        },
        "evidence": {},
    }
    result_b = {
        "norm": {"Sn": 100.0},
        "props": {
            "tensile_strength": 0.0,
            "mechanical_property_metadata": {"tensile_strength": unverified},
        },
        "evidence": {},
    }

    report = gui._build_compare_report(
        result_a["norm"], result_b["norm"], result_a, result_b
    )

    assert "인장강도 (A DB 평균 / B DB 평균) (MPa)\tN/A\t0.00 MPa\t검증 보류" in report
    assert "None MPa" not in report


def test_report_labels_mixed_sources_and_never_compares_raw_db_row(
    analyzer: AlloyAnalyzer,
) -> None:
    gui = _report_gui(analyzer)
    idw_meta = {
        "comparison_allowed": False,
        "verification_status": "unverified",
        "source_type": "legacy_property_db",
        "value_type": "idw_prediction",
    }
    model_meta = {
        "comparison_allowed": False,
        "verification_status": "unverified",
        "source_type": "model",
        "value_type": "model_prediction",
    }
    result_a = {
        "norm": {"Sn": 100.0},
        "props": {
            "tensile_strength": 10.0,
            "tensile_strength_db_mpa": 1.0,
            "mechanical_property_metadata": {"tensile_strength": idw_meta},
        },
        "evidence": {},
    }
    result_b = {
        "norm": {"Sn": 100.0},
        "props": {
            "tensile_strength": 10.0,
            "tensile_strength_db_mpa": 2.0,
            "mechanical_property_metadata": {"tensile_strength": model_meta},
        },
        "evidence": {},
    }

    report = gui._build_compare_report(
        result_a["norm"], result_b["norm"], result_a, result_b
    )

    assert "인장강도 (A DB IDW 예측 / B 모델 예측) (MPa)" in report
    assert "물성 DB 인장 참고값 (MPa)\t1.00 MPa\t2.00 MPa\t검증 보류" in report


def test_wetting_override_updates_value_metadata_and_evidence_together() -> None:
    gui = AlloyGUI.__new__(AlloyGUI)
    result = {
        "props": {"wetting_fmax_pred_mn": 9.9},
        "evidence": {"wetting": {"source": "stale", "source_kind": "idw_prediction"}},
    }
    details = {
        "wetting_temp_c": 250.0,
        "fmax_pred_mn": 0.0,
        "t0_pred_s": 0.0,
        "neighbors": [{"name": "SAC305", "dist": 0.0}],
        "wetting_temp_basis": "compare_shared",
        "wetting_temp_target_c": 250.0,
        "wetting_metadata": {
            "source_kind": "measured_db",
            "value_type": "direct_db_record",
            "provenance_status": "unconfirmed",
            "verification_status": "unverified",
            "comparison_allowed": False,
        },
    }

    gui._apply_wetting_props_from_details(result, details)

    assert result["props"]["wetting_fmax_pred_mn"] == 0.0
    assert result["props"]["wetting_t0_pred_s"] == 0.0
    assert result["props"]["wetting_metadata"] == details["wetting_metadata"]
    assert result["evidence"]["wetting"]["source_kind"] == "measured_db"
    assert result["evidence"]["wetting"]["source"] == "Measured(DB-exact)"
    assert result["evidence"]["wetting"]["temperature_basis"] == "compare_shared"
    assert _wetting_source_label(result["props"], result["evidence"]) == (
        "측정 DB(시험조건 미확인)"
    )


def test_wetting_comparison_requires_matching_verified_basis() -> None:
    metadata = {
        "source_kind": "measured_db",
        "value_type": "direct_db_record",
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "wetting-series-7",
        "comparison_basis": "compare_shared",
    }
    props_a = {
        "wetting_fmax_pred_mn": 2.0,
        "wetting_t0_pred_s": 1.0,
        "wetting_temp_c": 250.0,
        "wetting_temp_basis": "compare_shared",
        "wetting_metadata": metadata,
    }
    props_b = deepcopy(props_a)

    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is True
    assert _wetting_source_label(props_a, {}) == "측정 DB"

    props_b["wetting_temp_basis"] = "user"
    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is False

    props_b = deepcopy(props_a)
    props_b["wetting_metadata"]["verification_status"] = "unverified"
    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is False

    props_b = deepcopy(props_a)
    props_b["wetting_t0_pred_s"] = None
    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is False

    props_b = deepcopy(props_a)
    props_a["wetting_metadata"] = {
        "verification_status": "verified",
        "comparison_allowed": True,
    }
    props_b["wetting_metadata"] = deepcopy(props_a["wetting_metadata"])
    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is False


@pytest.mark.parametrize(
    "source_field,basis_field",
    [
        ("source_identifier", "comparison_basis"),
        ("source_id", "basis"),
        ("test_series_id", "test_standard"),
        ("dataset_id", "test_method"),
    ],
)
def test_wetting_comparison_requires_matching_source_identifier_and_basis_aliases(
    source_field: str, basis_field: str
) -> None:
    metadata = {
        "source_kind": "measured_db",
        "value_type": "direct_db_record",
        "verification_status": "verified",
        "comparison_allowed": True,
        source_field: "wetting-series-42",
        basis_field: "compare_shared",
    }
    props_a = {
        "wetting_fmax_pred_mn": 2.0,
        "wetting_t0_pred_s": 1.0,
        "wetting_temp_c": 250.0,
        "wetting_temp_basis": "compare_shared",
        "wetting_metadata": metadata,
    }
    props_b = deepcopy(props_a)

    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is True

    props_b["wetting_metadata"][source_field] = "different-series"
    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is False

    props_b = deepcopy(props_a)
    props_b["wetting_metadata"].pop(source_field)
    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is False

    props_b = deepcopy(props_a)
    props_b["wetting_metadata"][basis_field] = "user"
    props_b["wetting_temp_basis"] = "user"
    assert _wetting_pair_comparison_allowed(props_a, props_b, {}, {}) is False


@pytest.mark.parametrize(
    "source_kind,value_type",
    [
        ("measured_db", "direct_db_record"),
        ("measured_db", "measured"),
        ("idw_prediction", "idw_prediction"),
    ],
)
def test_wetting_comparison_allows_only_contract_exact_pairs(
    source_kind: str, value_type: str
) -> None:
    metadata = {
        "source_kind": source_kind,
        "value_type": value_type,
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "wetting-series-contract",
        "comparison_basis": "compare_shared",
    }
    props = {
        "wetting_fmax_pred_mn": 2.0,
        "wetting_t0_pred_s": 1.0,
        "wetting_temp_c": 250.0,
        "wetting_metadata": metadata,
    }

    assert _wetting_pair_comparison_allowed(props, deepcopy(props), {}, {})


def test_wetting_comparison_rejects_alias_and_props_evidence_conflicts() -> None:
    metadata = {
        "source_kind": "measured_db",
        "value_type": "direct_db_record",
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "wetting-series-42",
        "source_id": "wetting-series-42",
        "comparison_basis": "compare_shared",
        "test_method": "compare_shared",
    }
    props_a = {
        "wetting_fmax_pred_mn": 2.0,
        "wetting_t0_pred_s": 1.0,
        "wetting_temp_c": 250.0,
        "wetting_temp_basis": "compare_shared",
        "wetting_metadata": deepcopy(metadata),
    }
    props_b = deepcopy(props_a)
    evidence_a = {"wetting": deepcopy(metadata)}
    evidence_b = {"wetting": deepcopy(metadata)}

    assert _wetting_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b
    )

    measured_props_a = deepcopy(props_a)
    measured_props_b = deepcopy(props_b)
    measured_evidence_a = deepcopy(evidence_a)
    measured_evidence_b = deepcopy(evidence_b)
    for metadata_copy in (
        measured_props_a["wetting_metadata"],
        measured_props_b["wetting_metadata"],
        measured_evidence_a["wetting"],
        measured_evidence_b["wetting"],
    ):
        metadata_copy["value_type"] = "measured"
    assert _wetting_pair_comparison_allowed(
        measured_props_a,
        measured_props_b,
        measured_evidence_a,
        measured_evidence_b,
    )

    props_a["wetting_metadata"]["source_id"] = "conflicting-series"
    assert not _wetting_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b
    )

    props_a = deepcopy(props_b)
    props_a["wetting_metadata"]["test_method"] = "user"
    assert not _wetting_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b
    )

    props_a = deepcopy(props_b)
    evidence_a["wetting"]["source_identifier"] = "different-evidence-series"
    assert not _wetting_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b
    )
    assert _wetting_source_label(props_a, evidence_a) == (
        "측정 DB(시험조건 미확인)"
    )

    evidence_a = {"wetting": {**metadata, "temperature_c": 260.0}}
    assert not _wetting_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b
    )

    evidence_a = {"wetting": deepcopy(metadata)}
    props_a["wetting_metadata"]["source_id"] = ""
    assert not _wetting_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b
    )

    props_a = deepcopy(props_b)
    assert not _wetting_pair_comparison_allowed(
        props_a, props_b, {"wetting": []}, evidence_b
    )


def test_mechanical_comparison_fails_closed_without_source_identity() -> None:
    props_a = {
        "shear_strength": 10.0,
        "mechanical_property_metadata": {
            "shear_strength": {
                "verification_status": "verified",
                "comparison_allowed": True,
            }
        },
    }
    props_b = deepcopy(props_a)

    assert (
        _mechanical_pair_comparison_allowed(
            props_a, props_b, {}, {}, "shear_strength"
        )
        is False
    )


@pytest.mark.parametrize(
    "source_field", ["source_identifier", "source_id", "test_series_id", "dataset_id"]
)
@pytest.mark.parametrize(
    "basis_field", ["comparison_basis", "test_standard", "test_method"]
)
def test_mechanical_comparison_requires_matching_identifier_and_basis_aliases(
    source_field: str, basis_field: str
) -> None:
    metadata = {
        "source_type": "verified_property_db",
        "value_type": "verified_measured_mean",
        "verification_status": "verified",
        "comparison_allowed": True,
        source_field: "mechanical-series-42",
        basis_field: "same-specimen-and-method",
    }
    props_a = {
        "shear_strength": 10.0,
        "mechanical_property_metadata": {"shear_strength": metadata},
    }
    props_b = deepcopy(props_a)

    assert _mechanical_pair_comparison_allowed(
        props_a, props_b, {}, {}, "shear_strength"
    )

    props_b["mechanical_property_metadata"]["shear_strength"][source_field] = (
        "different-series"
    )
    assert not _mechanical_pair_comparison_allowed(
        props_a, props_b, {}, {}, "shear_strength"
    )

    props_b = deepcopy(props_a)
    props_b["mechanical_property_metadata"]["shear_strength"].pop(source_field)
    assert not _mechanical_pair_comparison_allowed(
        props_a, props_b, {}, {}, "shear_strength"
    )

    props_b = deepcopy(props_a)
    props_b["mechanical_property_metadata"]["shear_strength"][basis_field] = (
        "different-method"
    )
    assert not _mechanical_pair_comparison_allowed(
        props_a, props_b, {}, {}, "shear_strength"
    )


@pytest.mark.parametrize(
    "source_type,value_type",
    [
        ("measured_db", "measured"),
        ("verified_property_db", "verified_measured_mean"),
        ("literature", "literature_reference"),
    ],
)
def test_mechanical_comparison_allows_only_contract_exact_pairs(
    source_type: str, value_type: str
) -> None:
    metadata = {
        "source_type": source_type,
        "value_type": value_type,
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "mechanical-series-contract",
        "comparison_basis": "same-specimen-and-method",
    }
    props = {
        "tensile_strength": 42.0,
        "mechanical_property_metadata": {"tensile_strength": metadata},
    }

    assert _mechanical_pair_comparison_allowed(
        props, deepcopy(props), {}, {}, "tensile_strength"
    )


def test_mechanical_comparison_rejects_crossed_pair_alias_and_copy_conflicts() -> None:
    metadata = {
        "source_type": "verified_property_db",
        "value_type": "verified_measured_mean",
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "mechanical-series-42",
        "source_id": "mechanical-series-42",
        "comparison_basis": "same-specimen-and-method",
        "test_method": "same-specimen-and-method",
    }
    props_a = {
        "shear_strength": 10.0,
        "mechanical_property_metadata": {"shear_strength": deepcopy(metadata)},
    }
    props_b = deepcopy(props_a)
    evidence_a = {
        "mechanical_properties": {"shear_strength": deepcopy(metadata)}
    }
    evidence_b = deepcopy(evidence_a)

    assert _mechanical_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b, "shear_strength"
    )

    crossed = deepcopy(props_a)
    crossed_meta = crossed["mechanical_property_metadata"]["shear_strength"]
    crossed_meta["source_type"] = "measured_db"
    assert not _mechanical_pair_comparison_allowed(
        crossed, crossed, {}, {}, "shear_strength"
    )

    props_a["mechanical_property_metadata"]["shear_strength"]["source_id"] = (
        "conflicting-series"
    )
    assert not _mechanical_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b, "shear_strength"
    )

    props_a = deepcopy(props_b)
    props_a["mechanical_property_metadata"]["shear_strength"]["test_method"] = (
        "different-method"
    )
    assert not _mechanical_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b, "shear_strength"
    )

    props_a = deepcopy(props_b)
    evidence_a["mechanical_properties"]["shear_strength"]["comparison_basis"] = (
        "different-evidence-method"
    )
    assert not _mechanical_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b, "shear_strength"
    )
    assert "검증됨" not in _mechanical_provenance_text(
        props_a, evidence_a, "shear_strength"
    )

    evidence_a = {
        "mechanical_properties": {"shear_strength": deepcopy(metadata)}
    }
    props_a["mechanical_property_metadata"]["shear_strength"]["source_id"] = ""
    assert not _mechanical_pair_comparison_allowed(
        props_a, props_b, evidence_a, evidence_b, "shear_strength"
    )

    props_a = deepcopy(props_b)
    assert not _mechanical_pair_comparison_allowed(
        props_a,
        props_b,
        {"mechanical_properties": {"shear_strength": []}},
        evidence_b,
        "shear_strength",
    )


@pytest.mark.parametrize("bad_value", [{"kind": "model"}, ["model"], "unknown"])
@pytest.mark.parametrize("field", ["source_type", "value_type"])
def test_mechanical_comparison_rejects_non_enum_source_metadata(
    field: str, bad_value: object
) -> None:
    metadata = {
        "source_type": "verified_property_db",
        "value_type": "verified_measured_mean",
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "mechanical-series-42",
        "comparison_basis": "same-specimen-and-method",
    }
    metadata[field] = bad_value
    props_a = {
        "shear_strength": 10.0,
        "mechanical_property_metadata": {"shear_strength": metadata},
    }
    props_b = deepcopy(props_a)

    assert (
        _mechanical_pair_comparison_allowed(
            props_a, props_b, {}, {}, "shear_strength"
        )
        is False
    )
    assert "검증됨" not in _mechanical_provenance_text(
        props_a, {}, "shear_strength"
    )


def test_mechanical_comparison_rejects_unknown_status_boolean_and_crossed_identity() -> None:
    base = {
        "shear_strength": 10.0,
        "mechanical_property_metadata": {
            "shear_strength": {
                "source_type": "verified_property_db",
                "value_type": "verified_measured_mean",
                "verification_status": "verified",
                "comparison_allowed": True,
                "source_identifier": "mechanical-series-42",
                "comparison_basis": "same-specimen-and-method",
            }
        },
    }
    for field, bad_value in (
        ("verification_status", {"status": "verified"}),
        ("verification_status", ["verified"]),
        ("verification_status", "unknown"),
        ("comparison_allowed", 1),
    ):
        props_a = deepcopy(base)
        props_a["mechanical_property_metadata"]["shear_strength"][field] = bad_value
        assert not _mechanical_pair_comparison_allowed(
            props_a, deepcopy(props_a), {}, {}, "shear_strength"
        )

    crossed = deepcopy(base)
    crossed["mechanical_property_metadata"]["shear_strength"]["source_type"] = (
        "measured_db"
    )
    assert not _mechanical_pair_comparison_allowed(
        crossed, deepcopy(crossed), {}, {}, "shear_strength"
    )


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("source_kind", {"kind": "measured_db"}),
        ("source_kind", ["measured_db"]),
        ("source_kind", "unknown"),
        ("value_type", {"kind": "direct_db_record"}),
        ("value_type", ["direct_db_record"]),
        ("value_type", "unknown"),
        ("verification_status", {"status": "verified"}),
        ("verification_status", ["verified"]),
        ("verification_status", "unknown"),
        ("comparison_allowed", 1),
    ],
)
def test_wetting_comparison_rejects_non_enum_or_non_boolean_metadata(
    field: str, bad_value: object
) -> None:
    metadata = {
        "source_kind": "measured_db",
        "value_type": "direct_db_record",
        "verification_status": "verified",
        "comparison_allowed": True,
        "source_identifier": "wetting-series-42",
        "comparison_basis": "compare_shared",
    }
    metadata[field] = bad_value
    props_a = {
        "wetting_fmax_pred_mn": 2.0,
        "wetting_t0_pred_s": 1.0,
        "wetting_temp_c": 250.0,
        "wetting_temp_basis": "compare_shared",
        "wetting_metadata": metadata,
    }

    assert not _wetting_pair_comparison_allowed(
        props_a, deepcopy(props_a), {}, {}
    )
    if field in {"source_kind", "value_type"}:
        assert _wetting_source_label(props_a, {}) == "출처 미확인"
    else:
        assert _wetting_source_label(props_a, {}) == "측정 DB(시험조건 미확인)"


@pytest.mark.parametrize(
    "bad_basis", [{"basis": "compare_shared"}, ["compare_shared"], "unknown"]
)
def test_wetting_comparison_rejects_non_enum_temperature_basis(
    bad_basis: object,
) -> None:
    props_a = {
        "wetting_fmax_pred_mn": 2.0,
        "wetting_t0_pred_s": 1.0,
        "wetting_temp_c": 250.0,
        "wetting_temp_basis": bad_basis,
        "wetting_metadata": {
            "source_kind": "measured_db",
            "value_type": "direct_db_record",
            "verification_status": "verified",
            "comparison_allowed": True,
            "source_identifier": "wetting-series-42",
            "comparison_basis": "compare_shared",
        },
    }

    assert not _wetting_pair_comparison_allowed(
        props_a, deepcopy(props_a), {}, {}
    )


def test_wetting_override_clears_stale_verified_provenance_when_metadata_missing() -> None:
    gui = AlloyGUI.__new__(AlloyGUI)
    stale_result = {
        "props": {
            "wetting_fmax_pred_mn": 9.9,
            "wetting_temp_c": 250.0,
            "wetting_temp_basis": "compare_shared",
            "wetting_metadata": {
                "source_kind": "measured_db",
                "value_type": "direct_db_record",
                "verification_status": "verified",
                "comparison_allowed": True,
                "source_identifier": "stale-wetting-series",
                "comparison_basis": "compare_shared",
                "exact_match": True,
            },
        },
        "evidence": {
            "wetting": {
                "source": "Measured(DB-exact)",
                "source_kind": "measured_db",
                "value_type": "direct_db_record",
                "verification_status": "verified",
                "comparison_allowed": True,
                "source_identifier": "stale-wetting-series",
                "comparison_basis": "compare_shared",
                "exact_match": True,
            }
        },
    }
    base_details = {
        "wetting_temp_c": 250.0,
        "fmax_pred_mn": 1.5,
        "t0_pred_s": 0.8,
        "wetting_temp_basis": "compare_shared",
    }

    for supplied_metadata in (None, [], "verified", {}):
        result = deepcopy(stale_result)
        details = deepcopy(base_details)
        if supplied_metadata is not None:
            details["wetting_metadata"] = supplied_metadata
        gui._apply_wetting_props_from_details(result, details)

        props_meta = result["props"]["wetting_metadata"]
        wet_evidence = result["evidence"]["wetting"]
        assert props_meta["source_kind"] == "unknown"
        assert props_meta["verification_status"] == "unverified"
        assert props_meta["comparison_allowed"] is False
        assert wet_evidence["source"] == "Unknown"
        assert wet_evidence["verification_status"] == "unverified"
        assert wet_evidence["comparison_allowed"] is False
        assert "exact_match" not in wet_evidence
        assert _wetting_source_label(result["props"], result["evidence"]) == (
            "출처 미확인"
        )


def test_single_summary_shows_tensile_provenance_and_zero_without_tk_root() -> None:
    gui = AlloyGUI.__new__(AlloyGUI)
    gui.result_box = _TextCapture()
    gui._link_targets = {}
    for attr in (
        "view_show_phase",
        "view_show_imc",
        "view_show_risk",
        "view_show_roles",
        "view_show_dopant",
    ):
        setattr(gui, attr, SimpleNamespace(get=lambda: True))

    props = {
        "tensile_strength": 0.0,
        "shear_strength": None,
        "elongation": None,
        "mechanical_property_metadata": {
            "tensile_strength": {
                "comparison_allowed": False,
                "verification_status": "unverified",
            }
        },
    }
    gui._render_result_text(
        "",
        {
            "best_name": "테스트 합금",
            "confidence_overall": 81.0,
            "props": props,
            "evidence": {},
        },
    )

    assert "인장 0.0 MPa" in gui.result_box.text
    assert "전단 N/A MPa" in gui.result_box.text
    assert "인장 근거" in gui.result_box.text
    assert "항복 근거" in gui.result_box.text
    assert "연신 근거" in gui.result_box.text
    assert "전단 근거" in gui.result_box.text
    assert "시험조건·출처 미확인/검증 보류 · 상대비교·추천 제외" in gui.result_box.text
    assert "신뢰도(조성·융점·젖음 근거)" in gui.result_box.text

    props["mechanical_property_metadata"]["tensile_strength"] = {
        "comparison_allowed": True,
        "verification_status": "verified",
    }
    gui._render_result_text(
        "",
        {
            "best_name": "출처 누락 합금",
            "props": props,
            "evidence": {},
        },
    )
    assert "출처 미확인 · 검증됨" not in gui.result_box.text
    assert "출처 미확인 · 시험조건·출처 미확인/검증 보류" in gui.result_box.text

    gui._render_result_text(
        "",
        {
            "type": "compare",
            "A": {"name": "A", "confidence": 90.0, "confidence_overall": 80.0},
            "B": {"name": "B", "confidence": 70.0, "confidence_overall": 60.0},
        },
    )
    assert "조성 근접 90% / 조성·융점·젖음 근거 80%" in gui.result_box.text


def test_single_radar_refuses_missing_and_all_numeric_unverified(monkeypatch) -> None:
    assert "tensile_strength_db_mpa" not in {axis[0] for axis in _RADAR_PROPERTY_AXES}
    gui = AlloyGUI.__new__(AlloyGUI)
    gui.last_result = {
        "props": {
            "tensile_strength": 0.0,
            "yield_strength": 1.0,
            "elongation": None,
            "shear_strength": 3.0,
            "wetting_fmax_pred_mn": 4.0,
            "tensile_strength_db_mpa": 99.0,
        }
    }
    gui.compare_result = None
    scheduled = []
    warnings = []
    gui.root = SimpleNamespace(after=lambda *_args: scheduled.append(True))
    monkeypatch.setattr(
        "test7.gui.messagebox.showwarning",
        lambda title, message: warnings.append((title, message)),
    )

    gui.show_radar_chart()

    assert scheduled == []
    assert warnings and warnings[0][0] == "N/A 물성 포함"

    gui.last_result["props"]["elongation"] = 0.0
    gui.show_radar_chart()

    assert scheduled == []
    assert warnings[-1][0] == "검증 보류"
    assert "참고 전용" in warnings[-1][1]


def test_single_radar_allows_fully_verified_property_signatures(monkeypatch) -> None:
    gui = AlloyGUI.__new__(AlloyGUI)
    mechanical_metadata = {
        key: {
            "source_type": "verified_property_db",
            "value_type": "verified_measured_mean",
            "verification_status": "verified",
            "comparison_allowed": True,
            "source_identifier": f"verified-series-{key}",
            "comparison_basis": "same-specimen-and-method",
        }
        for key in (
            "tensile_strength",
            "yield_strength",
            "elongation",
            "shear_strength",
        )
    }
    gui.last_result = {
        "props": {
            "tensile_strength": 0.0,
            "yield_strength": 1.0,
            "elongation": 0.0,
            "shear_strength": 3.0,
            "wetting_fmax_pred_mn": 4.0,
            "wetting_t0_pred_s": 1.0,
            "wetting_temp_c": 250.0,
            "wetting_temp_basis": "compare_shared",
            "mechanical_property_metadata": mechanical_metadata,
            "wetting_metadata": {
                "source_kind": "measured_db",
                "value_type": "direct_db_record",
                "verification_status": "verified",
                "comparison_allowed": True,
                "source_identifier": "verified-wetting-series",
                "comparison_basis": "compare_shared",
            },
        },
        "evidence": {},
    }
    gui.compare_result = None
    scheduled = []
    warnings = []
    gui.root = SimpleNamespace(after=lambda *_args: scheduled.append(True))
    monkeypatch.setattr(
        "test7.gui.messagebox.showwarning",
        lambda title, message: warnings.append((title, message)),
    )

    gui.show_radar_chart()

    assert scheduled == [True]
    assert warnings == []


def test_reflow_popup_property_block_labels_every_raw_value_with_provenance() -> None:
    source_less_verified = {
        "comparison_allowed": True,
        "verification_status": "verified",
    }
    props = {
        "tensile_strength": 0.0,
        "yield_strength": 10.0,
        "elongation": None,
        "shear_strength": 28.0,
        "wetting_fmax_pred_mn": 1.94,
        "wetting_t0_pred_s": 1.09,
        "wetting_temp_c": 250.0,
        "wetting_temp_basis": "compare_shared",
        "tensile_strength_db_mpa": 78.0,
        "mechanical_property_metadata": {
            key: deepcopy(source_less_verified)
            for key in (
                "tensile_strength",
                "yield_strength",
                "elongation",
                "shear_strength",
            )
        },
        "wetting_metadata": deepcopy(source_less_verified),
    }

    popup_text = _reflow_property_info(props, {})

    assert "인장강도" in popup_text and "인장강도 근거" in popup_text
    assert "항복강도" in popup_text and "항복강도 근거" in popup_text
    assert "연신율" in popup_text and "연신율 근거" in popup_text
    assert "전단강도" in popup_text and "전단강도 근거" in popup_text
    assert "젖음 Fmax : 1.94 mN" in popup_text
    assert "젖음 T0   : 1.09 s" in popup_text
    assert "젖음 근거 : 출처 미확인" in popup_text
    assert any(
        line.startswith("연신율") and line.endswith(": N/A")
        for line in popup_text.splitlines()
    )
    assert any(
        line.startswith("인장강도") and line.endswith(": 0.0 MPa")
        for line in popup_text.splitlines()
    )
    assert "물성DB인장: 78.0 MPa (참고값·검증 보류)" in popup_text
    assert popup_text.count("상대비교·추천 제외") == 5
    assert "검증됨" not in popup_text


def test_optional_finite_float_fails_closed_on_huge_integer_overflow() -> None:
    huge_integer = 10**10000

    assert _optional_finite_float(huge_integer) is None
    assert AlloyGUI._fmt_num(huge_integer) == "N/A"
