"""Regression tests for prediction boundary and missing-evidence behavior."""

from __future__ import annotations

import urllib.request

import pytest

from test7.analyzer import AlloyAnalyzer
from test7.melting_predictor import (
    _classify,
    _external_calphad_http,
    hybrid_melting_predict,
)
from test7.models import PropertyModels, compare_default_wetting_temp_c
from test7.solder_db import SOLDER_DB


def _normalize(**parts: float) -> dict[str, float]:
    total = sum(parts.values())
    return {**parts, "Sn": 100.0 - total}


def test_exact_row_without_shear_does_not_borrow_a_distant_shear_idw() -> None:
    # Sn0.3Ag2Cu is an exact property-DB row, but its shear observation is
    # missing.  The nearest valid shear value belongs to another alloy and is
    # reference-only, not a replacement for the model output.
    result = AlloyAnalyzer(SOLDER_DB).analyze_all(
        {"Sn": 97.7, "Ag": 0.3, "Cu": 2.0}, include_ai=False
    )
    props = result["props"]

    assert props["shear_strength"] is not None
    assert props["shear_strength_db_mpa"] is not None
    assert props["shear_strength"] != pytest.approx(props["shear_strength_db_mpa"])
    assert props["shear_metadata"]["value_type"] == "model_prediction"


def test_compare_wetting_temperature_rejects_missing_liquidus() -> None:
    with pytest.raises(ValueError, match="liquidus"):
        compare_default_wetting_temp_c(None, 220.0)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (_normalize(Ag=3.0, Cu=0.5, Bi=11.99), _normalize(Ag=3.0, Cu=0.5, Bi=12.01)),
    ],
)
def test_bi_tensile_transition_has_no_12_percent_step(left, right) -> None:
    models = PropertyModels()
    left_value = models.predict_tensile_strength(left, 210.0, 220.0)
    right_value = models.predict_tensile_strength(right, 210.0, 220.0)

    assert abs(right_value - left_value) < 1.0


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (_normalize(Ag=3.0, Cu=0.5, Bi=18.0), _normalize(Ag=3.0, Cu=0.5, Bi=18.01)),
        (_normalize(Ag=3.0, Cu=0.5, Bi=20.0), _normalize(Ag=3.0, Cu=0.5, Bi=20.01)),
        ({"Sn": 97.0, "Zn": 3.0}, {"Sn": 96.99, "Zn": 3.01}),
        ({"Sn": 99.01, "Pb": 0.99}, {"Sn": 99.0, "Pb": 1.0}),
        ({"Sn": 97.0, "Sb": 3.0}, {"Sn": 96.99, "Sb": 3.01}),
    ],
)
def test_melting_classifier_boundaries_are_continuous(left, right) -> None:
    left_result = hybrid_melting_predict(left, [], ai_engine=None)
    right_result = hybrid_melting_predict(right, [], ai_engine=None)

    assert _classify(left) in {"SAC_BI_TRANSITION", "SAC", "SnZn", "SnPb", "SnSb"}
    assert _classify(right) in {"SAC_BI_TRANSITION", "SAC", "SnBi", "SnZn", "SnPb", "SnSb"}
    assert abs(float(right_result[0]) - float(left_result[0])) < 5.0
    assert abs(float(right_result[1]) - float(left_result[1])) < 5.0


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


@pytest.mark.parametrize(
    "body",
    [
        b'{"solidus": NaN, "liquidus": 220.0, "confidence": 0.9}',
        b'{"solidus": 210.0, "liquidus": Infinity, "confidence": 0.9}',
        b'{"solidus": 210.0, "liquidus": 220.0, "confidence": NaN}',
    ],
)
def test_external_calphad_rejects_nonfinite_numbers(monkeypatch, body: bytes) -> None:
    monkeypatch.setenv("MELTING_CALPHAD_URL", "https://calphad.invalid/predict")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: _Response(body))

    assert _external_calphad_http({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}) is None
