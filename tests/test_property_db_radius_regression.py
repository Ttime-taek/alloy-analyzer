# Regression: 2026-10-30 — 인장·항복 물성 DB 혼합 반경 3 → 1.5.
# P2에서 조성 모델을 재보정한 뒤에는 먼 합금의 DB 평균을 섞을수록 오차가 커졌다
# (합금별 leave-one-out: 인장 4.90 → 3.90, 항복 6.01 → 4.75 MPa). 연신·전단은 반경 3 유지.
# Found by 계산 로직 후속 점검 (Claude) on 2026-10-30
from __future__ import annotations

import pytest

from test7.analyzer import _PROPERTY_DB_RADIUS, _property_db_weight


def test_radius_per_property() -> None:
    assert _PROPERTY_DB_RADIUS == {"tensile": 1.5, "yield_strength": 1.5, "elongation": 3.0, "shear": 3.0}


def test_weight_curve_is_smooth_and_hits_zero_at_radius() -> None:
    assert _property_db_weight(0.0, 1.5) == 1.0
    assert _property_db_weight(0.75, 1.5) == pytest.approx(0.5)
    assert _property_db_weight(1.5, 1.5) == 0.0
    assert _property_db_weight(2.0, 1.5) == 0.0
    # 기본 반경(3)은 이전과 같다.
    assert _property_db_weight(1.5) == pytest.approx(0.5)
    assert _property_db_weight(None, 1.5) == 0.0
    prev = 1.0
    for i in range(1, 151):
        w = _property_db_weight(i * 0.01, 1.5)
        assert 0.0 <= prev - w < 0.02
        prev = w
