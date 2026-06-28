# -*- coding: utf-8 -*-
"""SOLDER_PROPERTIES_DB 합금명별 행 조회 — TDD용."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PARENT = ROOT.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))


def test_rows_for_alloy_returns_both_test_rows_for_sn3_ag_cu():
    from test7.solder_properties import rows_for_alloy

    rows = rows_for_alloy("Sn3.0Ag0.5Cu")
    assert len(rows) == 2
    assert {r["test"] for r in rows} == {"Test 1", "Test 2"}
    assert all(r["alloy"] == "Sn3.0Ag0.5Cu" for r in rows)


def test_rows_for_alloy_unknown_returns_empty_list():
    from test7.solder_properties import rows_for_alloy

    assert rows_for_alloy("__no_such_alloy__") == []


def test_unique_alloy_names_sorted_distinct_matches_db():
    from test7.solder_properties import rows_for_alloy, unique_alloy_names

    names = unique_alloy_names()
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert len(names) == 26
    assert "Sn3.0Ag0.5Cu" in names
    for alloy in names:
        assert len(rows_for_alloy(alloy)) >= 1
