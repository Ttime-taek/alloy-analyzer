# -*- coding: utf-8 -*-
"""alloy_property_inference.predictAlloyProperties — 3-NN + 릿지 민감도 스모크."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PARENT = ROOT.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.alloy_property_inference import predictAlloyProperties


def _tiny_db():
    return [
        {
            "name": "SAC305-like-A",
            "comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
            "solidus": 217.0,
            "liquidus": 220.0,
        },
        {
            "name": "SAC305-like-B",
            "comp": {"Sn": 96.0, "Ag": 3.2, "Cu": 0.8},
            "solidus": 216.5,
            "liquidus": 219.5,
        },
        {
            "name": "SAC305-like-C",
            "comp": {"Sn": 95.5, "Ag": 3.5, "Cu": 1.0},
            "solidus": 216.0,
            "liquidus": 219.0,
        },
    ]


def test_predict_returns_neighbors_and_melting_range():
    norm = {"Sn": 96.2, "Ag": 3.3, "Cu": 0.5}
    out = predictAlloyProperties(norm, _tiny_db(), k=3)
    assert out["solidus"] is not None and out["liquidus"] is not None
    assert out["liquidus"] >= out["solidus"]
    assert len(out["neighbors"]) == 3
    assert abs(sum(out["neighbor_weights"]) - 1.0) < 1e-5
    assert out["recommended_peak_c"] is not None
    assert out["recommended_peak_c"] >= out["liquidus"]
    assert "리플로우" in (out.get("process_report") or "")


def test_empty_norm():
    out = predictAlloyProperties({}, _tiny_db())
    assert out["solidus"] is None
