"""Regression: legacy strength anchors must not masquerade as sourced measurements."""

from __future__ import annotations

import pytest

from test7.db_regression import parse_alloy
from test7.strength_literature_refs import (
    STRENGTH_LITERATURE_ANCHORS,
    nearest_strength_literature,
    strength_literature_lines,
)


def _anchor_for_doi(doi: str) -> dict:
    matches = [anchor for anchor in STRENGTH_LITERATURE_ANCHORS if anchor.get("doi") == doi]
    assert len(matches) == 1
    return matches[0]


def test_metals_2022_sac205_bi_anchor_matches_table_1_composition() -> None:
    anchor = _anchor_for_doi("10.3390/met12081245")

    assert anchor["alloy"] == "Sn2.0Ag0.5Cu1Bi"
    assert anchor["comp"] == {"Sn": 96.5, "Ag": 2.0, "Cu": 0.5, "Bi": 1.0}
    assert anchor["tensile_mpa"] == pytest.approx(43.7)
    assert anchor["source"] == (
        "SAC205 + 1 wt% Bi (SAC305의 Ag 1 wt% 대체) bulk tensile"
    )
    assert anchor["alloy"] != "Sn3.0Ag0.5Cu1Bi"
    assert anchor["comp"] != {"Sn": 95.5, "Ag": 3.0, "Cu": 0.5, "Bi": 1.0}

    result = nearest_strength_literature(anchor["comp"], top_k=1)
    assert result is not None
    assert result["best_dist"] == pytest.approx(0.0)
    assert result["refs"][0]["doi"] == "10.3390/met12081245"
    assert result["refs"][0]["tensile_mpa"] == pytest.approx(43.7)


def test_sn07cu_baseline_does_not_mislabel_co_added_strength_as_a_range() -> None:
    anchor = _anchor_for_doi("10.1007/s10854-023-09967-7")

    assert anchor["alloy"] == "Sn0.7Cu"
    assert anchor["comp"] == {"Sn": 99.3, "Cu": 0.7}
    assert anchor["tensile_mpa"] == pytest.approx(30.5)
    assert "tensile_range" not in anchor

    result = nearest_strength_literature(anchor["comp"], top_k=1)
    assert result is not None
    assert result["tensile_mpa"] == pytest.approx(30.5)
    assert result["tensile_range"] is None
    assert result["refs"][0]["doi"] == "10.1007/s10854-023-09967-7"
    assert result["refs"][0]["tensile_range"] is None


def test_high_bi_anchor_uses_linked_primary_bulk_tensile_value() -> None:
    anchor = _anchor_for_doi("10.3390/met9040462")

    assert anchor["alloy"] == "Sn57.6Bi0.4Ag"
    assert anchor["comp"] == {"Sn": 42.0, "Bi": 57.6, "Ag": 0.4}
    assert anchor["tensile_mpa"] == pytest.approx(58.7)
    assert "tensile_range" not in anchor

    result = nearest_strength_literature(anchor["comp"], top_k=1)
    assert result is not None
    assert result["best_dist"] == pytest.approx(0.0)
    assert result["tensile_mpa"] == pytest.approx(58.7)
    assert result["refs"][0]["source_link_status"] == "available"


def test_unsourced_high_bi_interpolation_is_not_a_literature_anchor() -> None:
    assert all(
        anchor.get("alloy") != "Sn1Ag25Bi0.7Cu"
        for anchor in STRENGTH_LITERATURE_ANCHORS
    )
    assert nearest_strength_literature(parse_alloy("Sn1Ag25Bi0.7Cu")) is None
    assert all(
        anchor.get("doi") or anchor.get("url")
        for anchor in STRENGTH_LITERATURE_ANCHORS
    )


@pytest.mark.parametrize(
    ("alloy", "tensile_mpa", "shear_mpa"),
    [
        ("Sn3.0Ag0.5Cu", 48.5, 84.5),
        ("Sn3.0Ag0.5Cu3Bi", 78.0, 28.0),
    ],
)
def test_legacy_internal_anchor_is_explicitly_unverified_reference_only(
    alloy: str,
    tensile_mpa: float,
    shear_mpa: float,
) -> None:
    result = nearest_strength_literature(parse_alloy(alloy))

    assert result is not None
    legacy_refs = [
        ref
        for ref in result["refs"]
        if ref.get("source_kind") == "legacy_internal_db_mean"
    ]
    assert len(legacy_refs) == 1
    ref = legacy_refs[0]
    assert ref["alloy"] == alloy
    assert ref["tensile_mpa"] == pytest.approx(tensile_mpa)
    assert ref["shear_mpa"] == pytest.approx(shear_mpa)
    assert ref["source"] == "레거시 내부 DB 평균"
    assert ref["value_type"] == "legacy_internal_db_mean"
    assert ref["provenance_status"] == "unconfirmed"
    assert ref["verification_status"] == "unverified"
    assert ref["comparison_allowed"] is False
    assert ref["source_link_status"] == "unavailable"
    assert not ref.get("url")
    assert not ref.get("doi")


def test_plain_evidence_lines_distinguish_linked_literature_from_legacy_db() -> None:
    lines = strength_literature_lines(parse_alloy("Sn3.0Ag0.5Cu"))

    external = next(line for line in lines if "10.1515/pmp-2018-0006" in line)
    legacy = next(line for line in lines if "[LegacyStrengthDB]" in line)
    assert external.startswith("[StrengthLit]")
    assert "URL:https://doi.org/10.1515/pmp-2018-0006" in external
    assert "UTS≈48.5 MPa" in legacy
    assert "전단≈84.5 MPa" in legacy
    assert "레거시 내부 DB 평균" in legacy
    assert "원출처 링크 미확인 · 시험조건 미확인 · 참고 전용" in legacy
    assert "내부실측" not in legacy
    assert not legacy.startswith("[StrengthLit]")
