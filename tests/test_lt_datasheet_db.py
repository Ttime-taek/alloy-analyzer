# -*- coding: utf-8 -*-
"""LT 데이터시트 추가 항목 로드·예측 반영 검증."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PARENT = ROOT.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

LT_MECHANICAL_ALLOYS = [
    "Sn3.5Ag0.7Cu",
    "Sn1.0Ag0.7Cu",
    "Sn0.3Ag2.0Cu",
    "Sn8.0Zn3.0Bi",
    "Sn3.5Ag0.5CuNiGe",
    "Sn3.5Ag0.5Bi3.0In",
    "Sn3.0Cu",
    "Sn3.0Cu0.5Ni",
    "Sn58Bi",
    "Sn3.9Ag0.6Cu",
    "Sn3.5Ag0.5Bi8.0In",
    "Sn100",
    "Sn63Pb37",
    "Sn42In1Cu1Zn",
    "Sn1.75Ag1.5Sb1In",
]

LT_MELTING_NEW = [
    "Sn0.3Ag0.5Cu3Bi",
    "Sn3.0Cu",
    "Sn0.3Ag2.0Cu",
    "Sn1.75Ag1.5Sb1In",
]


def test_lt_mechanical_rows_present():
    from test7.solder_properties import rows_for_alloy

    for alloy in LT_MECHANICAL_ALLOYS:
        rows = rows_for_alloy(alloy)
        assert len(rows) == 1, alloy
        assert rows[0]["test"] == "LT datasheet"
        assert rows[0]["tensile"] is not None


def test_lt_yield_elongation_filled_where_in_table():
    from test7.solder_properties import rows_for_alloy

    cases = [
        ("Sn1.0Ag0.7Cu", 32, 51.2),
        ("Sn3.5Ag0.5Bi8.0In", 55, None),
        ("Sn63Pb37", 43, 20.7),
    ]
    for alloy, y, e in cases:
        row = rows_for_alloy(alloy)[0]
        assert row["yield_strength"] == y, alloy
        assert row["elongation"] == e, alloy
        assert row["shear"] is None, alloy


def test_lt_melting_entries_in_solder_db():
    from test7.solder_db import SOLDER_DB

    names = {e["name"] for e in SOLDER_DB}
    for alloy in LT_MELTING_NEW:
        assert alloy in names, alloy


def test_predict_from_db_uses_sn1_ag07cu_neighbor():
    from test7.db_regression import parse_alloy, predict_from_db_with_detail
    from test7.solder_properties import rows_for_alloy

    rows = rows_for_alloy("Sn1.0Ag0.7Cu")
    assert rows[0]["tensile"] == 33

    # Bi 1.8% 근접 조성 — 신규 LT 앵커가 상위 이웃에 포함
    comp = {"Sn": 96.4, "Ag": 1.1, "Cu": 0.7, "Bi": 1.8}
    detail = predict_from_db_with_detail(comp)
    top_names = [n["alloy"] for n in detail.get("top", [])]
    assert "Sn1.0Ag0.7Cu" in top_names
    assert detail["pred"].get("tensile") is not None


def test_melting_db_sn03_ag05cu3bi_values():
    from test7.solder_db import SOLDER_DB

    entry = next(e for e in SOLDER_DB if e["name"] == "Sn0.3Ag0.5Cu3Bi")
    assert entry["solidus"] == 208
    assert entry["liquidus"] == 225
