"""Regression coverage for the 2026-09-21 accuracy and AI-cost fixes."""
from __future__ import annotations

from unittest.mock import patch

import api_server as api_mod
from test7.melting_predictor import SN_CU_PHASE
from test7.solder_db import QUARANTINED_RAW_ROWS, SOLDER_DB


def test_sn_cu_liquidus_table_is_physically_shaped() -> None:
    xs = [cu for cu, _, _ in SN_CU_PHASE]
    liq = {cu: l for cu, _, l in SN_CU_PHASE}
    assert xs == sorted(xs)
    # 아공정: Sn → 공정(0.7Cu) 단조 감소, 과공정: 단조 증가
    hypo = [l for cu, _, l in SN_CU_PHASE if cu <= 0.7]
    hyper = [l for cu, _, l in SN_CU_PHASE if cu >= 0.7]
    assert hypo == sorted(hypo, reverse=True)
    assert hyper == sorted(hyper)
    assert liq[0.7] == 227.0
    # 같은 DB 실측 행과 일치
    db = {row["name"]: row for row in SOLDER_DB}
    assert liq[3.0] == float(db["Sn3.0Cu"]["liquidus"])


def test_copied_liquidus_rows_are_quarantined() -> None:
    names = {row["name"] for row in SOLDER_DB}
    assert not names & set(QUARANTINED_RAW_ROWS)


def test_low_cu_predictions_stay_near_eutectic() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(api_mod.app)

    def liq(comp):
        body = client.post("/api/v1/analyses", json={"comp": comp}).json()
        return body["prediction_contract"]["properties"]["liquidus_c"]["point"]

    # 이전: Sn-0.5Cu 238.9 °C(격리 전 269 °C 근처까지 끌림) → 상태도 ~229 °C
    assert 227.0 <= liq({"Sn": 99.5, "Cu": 0.5}) <= 232.0
    # SAC105 제조사 자료 217–227 °C
    assert 223.0 <= liq({"Sn": 98.5, "Ag": 1.0, "Cu": 0.5}) <= 229.0


def test_global_explanation_cap_applies_across_clients() -> None:
    with patch.object(api_mod, "_EXPLANATION_RATE_LIMIT", 100), patch.object(
        api_mod, "_EXPLANATION_GLOBAL_RATE_LIMIT", 3
    ), patch.dict(api_mod._explanation_requests, clear=True):
        results = [api_mod._consume_explanation_quota(f"10.0.0.{i}")[0] for i in range(5)]
    assert results == [True, True, True, False, False]
