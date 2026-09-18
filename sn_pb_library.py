# sn_pb_library.py
"""
Sn-Pb 이원계 참조 데이터 (편집은 이 파일만 하면 됨).

- SN_PB_PHASE : melting_predictor L2 보간용. 튜플 (Pb%, solidus°C, liquidus°C)
  · Pb% = Pb / (Sn + Pb) × 100 (순수 Sn=0, 순수 Pb=100)
  · 행 추가/삭제 시 반드시 첫 번째 열 기준 오름차순 유지.

- SN_PB_SOLDER_ENTRIES : solder_db KNN용 항목. 비우려면 [] 로 두면 됨.

※ Sn63Pb37 등 기존 고정 항목은 solder_db.py 본문에 그대로 둠.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# (Pb wt% in Sn+Pb, solidus °C, liquidus °C) — 오름차순
SN_PB_PHASE: List[Tuple[float, float, float]] = [
    (0.0, 231.9, 231.9),
    (2.2, 183.0, 224.0),
    (10.0, 183.0, 216.0),
    (20.0, 183.0, 203.0),
    (30.0, 183.0, 192.0),
    (38.1, 183.0, 183.0),
    (40.0, 183.0, 188.0),
    (50.0, 183.0, 212.0),
    (60.0, 183.0, 238.0),
    (70.0, 183.0, 257.0),
    (80.0, 183.0, 275.0),
    (81.7, 183.0, 277.0),
    (85.0, 215.0, 290.0),
    # [2026-09-18 점검 패치] Pb-rich 고상선 수정
    #   변경: Sn10Pb90 255/301 → 268/302 °C, Sn5Pb95 290/312 → 301/314 °C
    #   근거: Kester Alloy Temperature Chart(268–302, 301–314), AIM 자료(275–302, 308–312)
    #   결과: 두 합금 모두 DB 정확일치로 268/302, 301/314 반환. 중간 조성 Sn7Pb93 예측 289.9/309.1 °C.
    #   검증: tests/test_audit_2026_09_18_regression.py::test_high_lead_sn_pb_solidus_matches_datasheets
    (90.0, 268.0, 302.0),  # Kester Alloy Temperature Chart: Sn10Pb90 268–302 °C
    (95.0, 301.0, 314.0),  # Kester Alloy Temperature Chart: Sn5Pb95 301–314 °C
    (98.0, 312.0, 322.0),
    (100.0, 327.5, 327.5),
]

# solder_db에 합류시키는 Sn-Pb 전용 행 (name, comp, solidus, liquidus)
SN_PB_SOLDER_ENTRIES: List[Dict[str, Any]] = [
    {"name": "Pb100", "comp": {"Pb": 100.0}, "solidus": 327.5, "liquidus": 327.5},
    {"name": "Sn2Pb98", "comp": {"Sn": 2.0, "Pb": 98.0}, "solidus": 312.0, "liquidus": 322.0},
    # [2026-09-18 점검 패치] 아래 두 행 = 위 SN_PB_PHASE와 동일 출처(Kester)로 수정 (이전 290/312, 255/301)
    {"name": "Sn5Pb95", "comp": {"Sn": 5.0, "Pb": 95.0}, "solidus": 301.0, "liquidus": 314.0},
    {"name": "Sn10Pb90", "comp": {"Sn": 10.0, "Pb": 90.0}, "solidus": 268.0, "liquidus": 302.0},
    {"name": "Sn15Pb85", "comp": {"Sn": 15.0, "Pb": 85.0}, "solidus": 215.0, "liquidus": 290.0},
    {"name": "Sn18.3Pb81.7", "comp": {"Sn": 18.3, "Pb": 81.7}, "solidus": 183.0, "liquidus": 277.0},
    {"name": "Sn20Pb80", "comp": {"Sn": 20.0, "Pb": 80.0}, "solidus": 183.0, "liquidus": 275.0},
    {"name": "Sn30Pb70", "comp": {"Sn": 30.0, "Pb": 70.0}, "solidus": 183.0, "liquidus": 257.0},
    {"name": "Sn40Pb60", "comp": {"Sn": 40.0, "Pb": 60.0}, "solidus": 183.0, "liquidus": 238.0},
    {"name": "Sn50Pb50", "comp": {"Sn": 50.0, "Pb": 50.0}, "solidus": 183.0, "liquidus": 212.0},
    {"name": "Sn60Pb40", "comp": {"Sn": 60.0, "Pb": 40.0}, "solidus": 183.0, "liquidus": 188.0},
    {"name": "Sn61.9Pb38.1", "comp": {"Sn": 61.9, "Pb": 38.1}, "solidus": 183.0, "liquidus": 183.0},
    {"name": "Sn70Pb30", "comp": {"Sn": 70.0, "Pb": 30.0}, "solidus": 183.0, "liquidus": 192.0},
    {"name": "Sn80Pb20", "comp": {"Sn": 80.0, "Pb": 20.0}, "solidus": 183.0, "liquidus": 203.0},
    {"name": "Sn90Pb10", "comp": {"Sn": 90.0, "Pb": 10.0}, "solidus": 183.0, "liquidus": 216.0},
    {"name": "Sn97.8Pb2.2", "comp": {"Sn": 97.8, "Pb": 2.2}, "solidus": 183.0, "liquidus": 224.0},
]
