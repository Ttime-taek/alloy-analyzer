# Regression: 2026-09-30 계산 로직 2차 점검 P2 — 등록 합금에 어떤 물성 실측이 없으면 그 합금 위에서는
# 모델 값을 쓰는데(다른 합금 값을 빌리지 않는 규칙), 바로 옆 조성은 거리 1쯤 떨어진 다른 합금의
# 실측을 크게 섞어 값이 튀었다: 순수 Sn 전단 24 MPa(모델) → Ni 0.01 % 첨가 47 MPa.
# 이제 그런 합금에서 거리 1.0까지 DB 가중을 0 → 원래 값으로 매끈하게 올린다.
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

from test7.analyzer import AlloyAnalyzer
from test7.solder_db import SOLDER_DB

A = AlloyAnalyzer(SOLDER_DB)


def _shear(comp):
    return float(A.analyze_all(comp, include_ai=False, include_melting_ai=False)["props"]["shear_strength"])


def test_pure_sn_shear_connects_to_trace_additions() -> None:
    base = _shear({"Sn": 100.0})
    assert abs(_shear({"Sn": 99.99, "Ni": 0.01}) - base) < 3.0
    assert abs(_shear({"Sn": 99.95, "Ni": 0.05}) - base) < 8.0


def test_shear_scan_near_pure_sn_has_no_steps() -> None:
    prev = None
    for i in range(0, 21):
        ni = i * 0.01
        comp = {"Sn": 100.0 - ni, "Ni": ni} if ni else {"Sn": 100.0}
        v = _shear(comp)
        if prev is not None:
            assert abs(v - prev) < 3.0, ni
        prev = v
