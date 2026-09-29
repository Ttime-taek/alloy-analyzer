# Regression: 2026-09-25 계산 로직 점검 P3 — Sn-Ag 이원계 표의 아공정 고상선이 217 ℃(SAC 3원 공정값)라
# Cu 없는 Sn-2Ag가 고상 218.7 ℃로, 공정 온도 221 ℃보다 낮게 나왔다(이원계에서 불가능).
# Found by 계산 로직 점검 (Claude) on 2026-09-25
from __future__ import annotations

from test7.melting_predictor import SN_AG_PHASE, hybrid_melting_predict
from test7.solder_db import SOLDER_DB

DB = [
    {"name": r["name"], "comp": r["comp"], "solidus": float(r["solidus"]), "liquidus": float(r["liquidus"])}
    for r in SOLDER_DB
]


def test_sn_ag_table_solidus_never_below_binary_eutectic() -> None:
    for ag, sol, _liq in SN_AG_PHASE:
        if ag > 0:
            assert sol >= 221.0, f"Ag {ag}: solidus {sol}"


def test_cu_free_hypoeutectic_sn_ag_solidus_near_221() -> None:
    # Ag 1 % 부근은 실측 행 Sn-1.0Ag-0.015P(요약표 217/219 °C)를 따르므로 여기서 제외한다
    # (2026-09-29 원본 대조로 격리 해제). DB 실측이 없는 구간만 이원계 공정 하한을 확인.
    for ag in (2.0, 2.5):
        solidus = float(hybrid_melting_predict({"Sn": 100 - ag, "Ag": ag}, DB, ai_engine=None)[0])
        assert solidus >= 220.0, f"Sn-{ag}Ag solidus {solidus}"
