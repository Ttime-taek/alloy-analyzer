"""Regression coverage for property-DB nearest-neighbor selection."""

from __future__ import annotations

import pytest

from test7.db_regression import (
    _unique_alloy_candidates,
    get_statistics,
    parse_alloy,
    predict_from_db,
    predict_from_db_with_detail,
)

# Regression: DATA-001 — repeated measurement rows occupied multiple KNN slots and were weighted twice.
# Found by /qa on 2026-08-12.
# Report: .gstack/investigation-reports/2026-08-12-tensile-neighbor-duplication.md


def _expected_unique_neighbor_property(input_comp: dict[str, float], prop: str) -> float:
    candidates = sorted(
        _unique_alloy_candidates(input_comp).items(),
        key=lambda item: item[1]["dist"],
    )
    exact = [item for item in candidates if item[1]["dist"] <= 1e-4]
    selected = (exact or candidates)[:5]

    weighted_values = []
    weights = []
    for alloy_name, item in selected:
        stats = get_statistics(alloy_name)
        prop_stats = stats.get(prop) if stats else None
        if not prop_stats:
            continue
        weight = (1.0 / (1.0 + item["dist"])) * prop_stats["n"]
        weighted_values.append(prop_stats["mean"] * weight)
        weights.append(weight)

    assert weights
    return sum(weighted_values) / sum(weights)


def test_unregistered_composition_uses_five_unique_alloy_neighbors():
    comp = {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0}

    detail = predict_from_db_with_detail(comp)
    top_names = [item["alloy"] for item in detail["top"]]

    assert len(top_names) == 5
    assert len(top_names) == len(set(top_names))
    assert detail["pred"]["tensile"] == pytest.approx(
        _expected_unique_neighbor_property(comp, "tensile")
    )
    assert detail["pred"]["tensile"] == pytest.approx(70.4780276803982)


def test_exact_registered_composition_still_returns_measured_alloy_mean():
    alloy_name = "Sn3.0Ag0.5Cu"
    comp = parse_alloy(alloy_name)
    stats = get_statistics(alloy_name)

    assert stats is not None
    prediction = predict_from_db(comp)

    for prop in ("tensile", "yield_strength", "elongation", "shear"):
        prop_stats = stats[prop]
        if prop_stats:
            assert prediction[prop] == pytest.approx(prop_stats["mean"])
