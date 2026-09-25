# Regression: 2026-09-25 계산 로직 점검 P3 — 상태도 표의 순수 Sn 값이 표마다 달랐고(Sn-Cu 231.9, 나머지 231.0),
# UI에서 입력 가능한 Pt·Fe·Co·Mn·Mo·Se·Te·P가 ELEMENT_MP에 없어 L4에서 600 ℃로 대체됐다(Se 221, P 44 ℃).
# Found by 계산 로직 점검 (Claude) on 2026-09-25
from __future__ import annotations

import pytest

from test7 import melting_predictor as mp

UI_ELEMENTS = [
    "Sn", "Ag", "Cu", "Bi", "In", "Sb", "Ni", "P", "Zn", "Pb", "Au",
    "Pd", "Pt", "Al", "Ga", "Ge", "Fe", "Co", "Mn", "Mo", "Se", "Te",
]


@pytest.mark.parametrize(
    "table", ["SN_BI_PHASE", "SN_IN_PHASE", "SN_AG_PHASE", "SN_CU_PHASE", "SN_SB_PHASE", "SN_ZN_PHASE"]
)
def test_pure_sn_endpoint_is_231_9(table) -> None:
    x, sol, liq = getattr(mp, table)[0]
    assert x == 0.0 and sol == pytest.approx(231.9) and liq == pytest.approx(231.9)


def test_every_ui_element_has_a_melting_point() -> None:
    missing = [e for e in UI_ELEMENTS if e not in mp.ELEMENT_MP]
    assert not missing, missing
