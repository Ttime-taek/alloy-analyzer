"""Regression coverage for issues found while auditing the deployed web app (2026-09-21)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api_server as api_mod
from test7.analyzer import _imc_line_to_plain_korean


def _imc(comp):
    client = TestClient(api_mod.app)
    body = client.post("/api/v1/analyses", json={"comp": comp}).json()
    return body["result"]["imc"]


def test_imc_lines_are_not_duplicated_after_plain_korean_conversion() -> None:
    for comp in (
        {"Sn": 98.5, "Ag": 1.0, "Cu": 0.5},
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        {"Sn": 42.0, "Bi": 58.0},
    ):
        lines = _imc(comp)
        assert len(lines) == len(set(lines)), (comp, lines)


def test_unknown_imc_line_is_dropped_when_a_real_layer_is_listed() -> None:
    unknown = _imc_line_to_plain_korean("규칙 기반으로는 지배적 IMC를 특정하기 어려움")
    for comp in ({"Sn": 63.0, "Pb": 37.0}, {"In": 52.0, "Sn": 48.0}):
        lines = _imc(comp)
        assert unknown not in lines or len(lines) == 1, (comp, lines)


def test_bi_rich_phase_uses_plain_korean_wording() -> None:
    assert _imc_line_to_plain_korean("Bi 농화 분산상 (비금속간화합물, 공정/분산상)").startswith("비스무스")
