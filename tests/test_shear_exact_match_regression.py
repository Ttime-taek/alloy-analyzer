"""Regression coverage for exact-match shear DB prediction."""

from __future__ import annotations

import pytest

from test7.db_regression import get_statistics, parse_alloy, predict_shear_from_db

# Regression: DATA-002 — exact registered alloys raised KeyError in shear prediction.
# Found by /qa on 2026-08-16.
# Report: .gstack/investigation-reports/2026-08-12-tensile-neighbor-duplication.md


@pytest.mark.parametrize(
    "alloy_name",
    ["Sn3.0Ag0.5Cu", "Sn0.7Cu", "Sn3.0Ag0.5Cu3Bi"],
)
def test_exact_registered_composition_returns_measured_shear_mean(alloy_name):
    stats = get_statistics(alloy_name)

    assert stats is not None
    assert stats["shear"] is not None
    assert predict_shear_from_db(parse_alloy(alloy_name)) == pytest.approx(
        stats["shear"]["mean"]
    )
