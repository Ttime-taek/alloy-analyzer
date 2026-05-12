# -*- coding: utf-8 -*-
import sys
from pathlib import Path

_PARENT = Path(__file__).resolve().parents[1].parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from test7.solder_db import SOLDER_DB, SOLDER_DB_FINGERPRINT, fingerprint_solder_db


def test_fingerprint_matches_module_db():
    assert fingerprint_solder_db(SOLDER_DB) == SOLDER_DB_FINGERPRINT


def test_fingerprint_changes_when_melting_changes():
    base = [
        {"name": "TestAlloy", "comp": {"Sn": 100.0}, "solidus": 230.0, "liquidus": 230.0},
    ]
    b2 = [{"name": "TestAlloy", "comp": {"Sn": 100.0}, "solidus": 231.0, "liquidus": 230.0}]
    assert fingerprint_solder_db(base) != fingerprint_solder_db(b2)


def test_analyzer_resyncs_after_db_mutation():
    from test7.analyzer import AlloyAnalyzer
    from test7.ai_engine import AIEngine

    db = [{"name": "Tmp", "comp": {"Sn": 100.0}, "solidus": 100.0, "liquidus": 100.0, "family": "x", "eutectic_type": "y"}]
    a = AlloyAnalyzer(db, ai_engine=AIEngine())
    fp0 = a._solder_db_fingerprint
    db[0]["solidus"] = 101.0
    a._sync_db_prepared()
    assert a._solder_db_fingerprint != fp0
    assert a.db_prepared[0]["solidus"] == 101.0
