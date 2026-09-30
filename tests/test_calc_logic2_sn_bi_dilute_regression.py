# Regression: 2026-09-30 계산 로직 2차 점검 — Sn-Bi 이원 저Bi(≤5 %) 구간.
# 'other' 계열(L4 휴리스틱)로 분류돼 액상선이 순수 Sn(231.9℃)보다 높게 나오고(Sn-4Bi 236℃ 성분),
# Bi 4.6 → 5 %에서 L2 상태도가 켜지며 액상 231 → 224℃, 고상 223 → 210℃로 급락했다.
# (젖음 평가 온도 = 액상선+30℃라 젖음 점수도 같이 튀었다.) 이제 이원 Sn-Bi는 Bi 0 %부터 SnBi 상태도.
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

from test7.melting_predictor import _classify, hybrid_melting_predict
from test7.solder_db import SOLDER_DB

DB = [
    {"name": r["name"], "comp": r["comp"], "solidus": float(r["solidus"]), "liquidus": float(r["liquidus"])}
    for r in SOLDER_DB
]


def _p(comp):
    s, l, _peak, _d = hybrid_melting_predict(comp, DB, ai_engine=None)
    return float(s), float(l)


def test_binary_sn_bi_is_routed_to_sn_bi_from_zero() -> None:
    assert _classify({"Sn": 99.0, "Bi": 1.0}) == "SnBi"
    assert _classify({"Sn": 97.0, "Bi": 3.0}) == "SnBi"
    # SAC + Bi는 여전히 SAC 경로.
    assert _classify({"Sn": 93.5, "Ag": 3.0, "Cu": 0.5, "Bi": 3.0}) == "SAC"


def test_dilute_sn_bi_melting_is_monotone_and_continuous() -> None:
    prev = _p({"Sn": 100.0})
    for i in range(1, 201):
        x = 0.05 * i
        cur = _p({"Sn": 100.0 - x, "Bi": x})
        assert cur[1] <= prev[1] + 0.3, x  # Bi를 넣을수록 액상선은 내려간다
        assert abs(cur[0] - prev[0]) < 1.5 and abs(cur[1] - prev[1]) < 1.5, x
        prev = cur
    s, l = _p({"Sn": 95.0, "Bi": 5.0})
    assert 218.0 <= l <= 226.0
    assert 200.0 <= s <= 214.0
