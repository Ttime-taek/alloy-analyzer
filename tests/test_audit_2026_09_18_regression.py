"""Regression coverage for fixes from the 2026-09-18 audit."""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server as api_mod
from test7.solder_db import QUARANTINED_SOURCE_ROWS, SOLDER_DB
from test7.sn_pb_library import SN_PB_PHASE, SN_PB_SOLDER_ENTRIES
from test_legacy_analyze_ai_opt_in_regression import _FakeAnalyzer, _FakeEngine


class _RecordingAnalyzer(_FakeAnalyzer):
    def __init__(self) -> None:
        super().__init__()
        self.melting_ai_calls: list[object] = []

    def analyze_all(self, comp, **kwargs):
        self.melting_ai_calls.append(kwargs.get("include_melting_ai"))
        return super().analyze_all(comp, **kwargs)


class _BoomAnalyzer(_FakeAnalyzer):
    def analyze_all(self, comp, **kwargs):
        raise RuntimeError("secret-internal-path /srv/app/db.sqlite")


def _post(analyzer, payload):
    client = TestClient(api_mod.app)
    with patch.object(api_mod, "_get_engine_bundle", return_value=(_FakeEngine(), analyzer)):
        return client.post("/api/analyze", json=payload)


def test_legacy_ai_is_rate_limited_and_never_adjusts_melting_numbers() -> None:
    analyzer = _RecordingAnalyzer()
    payload = {"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, "include_ai": True}
    with patch.object(api_mod, "_EXPLANATION_RATE_LIMIT", 2), patch.dict(
        api_mod._explanation_requests, clear=True
    ):
        codes = [_post(analyzer, payload).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert analyzer.melting_ai_calls and all(v is False for v in analyzer.melting_ai_calls)


def test_legacy_ai_respects_concurrency_gate() -> None:
    payload = {"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, "include_ai": True}
    with patch.dict(api_mod._explanation_requests, clear=True):
        assert api_mod._explanation_gate.acquire(blocking=False)
        try:
            assert _post(_FakeAnalyzer(), payload).status_code == 429
        finally:
            api_mod._explanation_gate.release()
        # 게이트가 풀리면 다시 허용되고, 요청 후 게이트가 반납된다.
        assert _post(_FakeAnalyzer(), payload).status_code == 200
        assert api_mod._explanation_gate.acquire(blocking=False)
        api_mod._explanation_gate.release()


def test_internal_errors_do_not_leak_exception_text() -> None:
    response = _post(_BoomAnalyzer(), {"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}})
    assert response.status_code == 500
    assert "secret-internal-path" not in response.text


def test_high_lead_sn_pb_solidus_matches_datasheets() -> None:
    by_name = {row["name"]: row for row in SN_PB_SOLDER_ENTRIES}
    assert (by_name["Sn10Pb90"]["solidus"], by_name["Sn10Pb90"]["liquidus"]) == (268.0, 302.0)
    assert (by_name["Sn5Pb95"]["solidus"], by_name["Sn5Pb95"]["liquidus"]) == (301.0, 314.0)
    phase = {pb: (sol, liq) for pb, sol, liq in SN_PB_PHASE}
    assert phase[90.0] == (268.0, 302.0)
    assert phase[95.0] == (301.0, 314.0)
    # Pb-rich 고상선은 Pb 증가에 따라 단조 증가해야 한다.
    rich = [sol for pb, sol, _ in SN_PB_PHASE if pb >= 81.7]
    assert rich == sorted(rich)


def test_contradictory_low_ag_sac_rows_are_quarantined() -> None:
    names = {row["name"] for row in SOLDER_DB}
    assert not names & set(QUARANTINED_SOURCE_ROWS)
    for row in SOLDER_DB:
        comp = row["comp"]
        ag, cu = comp.get("Ag", 0.0), comp.get("Cu", 0.0)
        if 0.9 <= ag <= 1.3 and 0.4 <= cu <= 0.8 and sum(v for k, v in comp.items() if k not in ("Sn", "Ag", "Cu")) < 0.2:
            assert row["liquidus"] >= 222.0, row["name"]
