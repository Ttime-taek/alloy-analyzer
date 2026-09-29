# Regression: 2026-09-30 계산 로직 2차 점검 P2 — 물성 조성 모델 정확도
#  - 연신율: 고상–액상 간격 ΔT × 0.3 %p 감점 때문에 고Cu·Ni 합금이 3~10 %(실측 30~32 %),
#    Sn58Bi 5 %(실측 25 %), Bi 3 % SAC는 거꾸로 28~32 %(실측 10~17 %).
#  - 인장: 순수 Sn 37 MPa(실측 14), Sn42In1Cu1Zn 54(실측 19), Pb 항 없음(Sn63Pb37 37 vs 47),
#    Zn 과소(Sn8Zn3Bi 53 vs 78).
# Found by 계산 로직 2차 점검 (Claude) on 2026-09-30
from __future__ import annotations

import statistics

import pytest

from test7.db_regression import parse_alloy
from test7.melting_predictor import hybrid_melting_predict
from test7.models import PropertyModels
from test7.solder_db import SOLDER_DB
import test7.SOLDER_PROPERTIES_DB as PDB

M = PropertyModels()
DB = [
    {"name": r["name"], "comp": r["comp"], "solidus": float(r["solidus"]), "liquidus": float(r["liquidus"])}
    for r in SOLDER_DB
]


def _comp(name):
    c = parse_alloy(name)
    total = sum(c.values())
    return {k: v * 100.0 / total for k, v in c.items()}


def _melt(comp):
    s, l, _p, _d = hybrid_melting_predict(comp, DB, ai_engine=None)
    return float(s), float(l)


def test_elongation_is_not_cut_by_freezing_range() -> None:
    # 초정 IMC 때문에 ΔT가 커도 연신은 유지된다.
    assert M.predict_elongation({"Sn": 97.0, "Cu": 3.0}, 227.0, 312.0) >= 25.0
    assert M.predict_elongation({"Sn": 96.5, "Cu": 3.0, "Ni": 0.5}, 228.0, 394.0) >= 25.0
    same = M.predict_elongation({"Sn": 97.0, "Cu": 3.0}, 227.0, 227.0)
    assert M.predict_elongation({"Sn": 97.0, "Cu": 3.0}, 227.0, 312.0) == pytest.approx(same)


def test_elongation_bi_shape() -> None:
    sac_bi = M.predict_elongation({"Sn": 93.5, "Ag": 3.0, "Cu": 0.5, "Bi": 3.0}, 209.0, 217.0)
    eutectic = M.predict_elongation({"Sn": 42.0, "Bi": 58.0}, 139.0, 139.0)
    sac = M.predict_elongation({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, 217.0, 221.0)
    assert sac_bi < 20.0
    assert 18.0 <= eutectic <= 32.0
    assert sac > sac_bi + 15.0


def test_elongation_unavailable_without_melting() -> None:
    assert M.predict_elongation({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, None, None) is None


@pytest.mark.parametrize(
    ("comp", "lo", "hi"),
    [
        ({"Sn": 100.0}, 13.0, 15.0),
        ({"Sn": 56.0, "In": 42.0, "Cu": 1.0, "Zn": 1.0}, 12.0, 30.0),
        ({"Sn": 63.0, "Pb": 37.0}, 40.0, 55.0),
        ({"Sn": 89.0, "Zn": 8.0, "Bi": 3.0}, 65.0, 85.0),
    ],
)
def test_tensile_model_reference_alloys(comp, lo, hi) -> None:
    s, l = _melt(comp)
    assert lo <= M.predict_tensile_strength(comp, s, l) <= hi


def test_tensile_rises_smoothly_from_pure_sn() -> None:
    prev = None
    for i in range(0, 301):
        cu = i * 0.005
        v = M.predict_tensile_strength({"Sn": 100.0 - cu, "Cu": cu}, 227.0, 229.0)
        if prev is not None:
            assert 0.0 <= v - prev < 0.6
        prev = v


def test_model_only_accuracy_against_property_db() -> None:
    # 모델 인자를 이 DB로 맞췄으므로 in-sample 오차 상한(악화 방지용 가드).
    errs = {"tensile": [], "elongation": []}
    for name in sorted({r["alloy"] for r in PDB.SOLDER_PROPERTIES_DB}):
        comp = _comp(name)
        s, l = _melt(comp)
        rows = [r for r in PDB.SOLDER_PROPERTIES_DB if r["alloy"] == name]
        for key, fn in (("tensile", M.predict_tensile_strength), ("elongation", M.predict_elongation)):
            vals = [r[key] for r in rows if r[key] is not None]
            if vals:
                errs[key].append(abs(fn(comp, s, l) - statistics.mean(vals)))
    assert statistics.mean(errs["tensile"]) < 5.0
    assert statistics.mean(errs["elongation"]) < 5.5
