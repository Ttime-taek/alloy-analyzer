# Regression: 2026-09-25 계산 로직 점검 — 분류기 경계에서 0.01~0.05 wt% 차이로 융점이
# 최대 57 ℃ 튀고(Bi=In, Sn-Bi 20 %, In 5 %·Zn, 미량 Pb/Ag/Cu), Pb 1 % 이상이면 Bi를 무시해
# Sn43Pb43Bi14(실측 144/163 ℃)를 183/212 ℃로, Sn42Bi58+Pb1을 182/222 ℃로 예측했다.
# Found by 계산 로직 점검 (Claude) on 2026-09-25
from __future__ import annotations

import random

import pytest
from test7.melting_predictor import _classify, hybrid_melting_predict
from test7.solder_db import SOLDER_DB

DB = [
    {
        "name": row["name"],
        "comp": row["comp"],
        "solidus": float(row["solidus"]),
        "liquidus": float(row["liquidus"]),
    }
    for row in SOLDER_DB
]

# 기존 test_melting_classifier_boundaries_are_continuous 와 같은 기준(0.01~0.05 wt% 변화에 5 ℃ 미만)
MAX_STEP_C = 5.0


def _predict(comp, db=DB):
    solidus, liquidus, peak, detail = hybrid_melting_predict(comp, db, ai_engine=None)
    return float(solidus), float(liquidus), float(peak), detail


def _step(left, right, db=DB):
    a = _predict(left, db)
    b = _predict(right, db)
    return abs(b[0] - a[0]), abs(b[1] - a[1])


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # Bi=In 경계: SnBi(Bi≥In) ↔ SAC(Bi<In). 이전 고상 +22.4 / 액상 −15.7 ℃
        (
            {"Sn": 79, "Ag": 1, "Cu": 1, "Bi": 9.51, "In": 9.49},
            {"Sn": 79, "Ag": 1, "Cu": 1, "Bi": 9.49, "In": 9.51},
        ),
        # Sn-Bi 이원 Bi 20 %: 이전 고상 159.4 → 139.0
        ({"Sn": 80.01, "Bi": 19.99}, {"Sn": 80.0, "Bi": 20.0}),
        # Sn-Zn-In, In 5 %: SnZn ↔ SnIn. 이전 고상 +19.5 ℃
        ({"Sn": 89.11, "Zn": 5.92, "In": 4.97}, {"Sn": 89.06, "Zn": 5.92, "In": 5.02}),
        # Sn-Sb에 미량 Cu → SnSb ↔ SnCu. 이전 −4.5 ℃
        ({"Sn": 93.75, "Sb": 6.25}, {"Sn": 93.7, "Sb": 6.25, "Cu": 0.05}),
        # 미량 Pb가 Sn-Bi를 other로 떨어뜨림. 이전 고상 +56.9 ℃
        ({"Sn": 80.0, "Bi": 20.0}, {"Sn": 79.95, "Bi": 20.0, "Pb": 0.05}),
        # 미량 Ag·Pb가 Sn-In 공정을 other로 떨어뜨림. 이전 +29 / +28 ℃
        ({"Sn": 48.0, "In": 52.0}, {"Sn": 47.95, "In": 52.0, "Ag": 0.05}),
        ({"Sn": 48.0, "In": 52.0}, {"Sn": 47.95, "In": 52.0, "Pb": 0.05}),
        # Pb 1 % 경계(Sn-Bi 공정에 Pb 오염). 이전 고상 142 → 182 ℃
        ({"Sn": 41.01, "Bi": 58.0, "Pb": 0.99}, {"Sn": 41.0, "Bi": 58.0, "Pb": 1.0}),
        # Pb≈Bi 선(SnBi ↔ SnPb) + Ag
        (
            {"Sn": 78.01, "Ag": 2.71, "Bi": 9.66, "Pb": 9.62},
            {"Sn": 78.01, "Ag": 2.71, "Bi": 9.61, "Pb": 9.67},
        ),
    ],
)
def test_classifier_boundaries_do_not_jump(left, right) -> None:
    ds, dl = _step(left, right)
    assert ds < MAX_STEP_C, f"solidus step {ds:.1f} ℃"
    assert dl < MAX_STEP_C, f"liquidus step {dl:.1f} ℃"


def test_boundaries_also_continuous_without_db() -> None:
    # DB 이웃 없이 L2 자체가 연속이어야 한다(기존 경계 테스트와 같은 방식).
    ds, dl = _step(
        {"Sn": 79, "Ag": 1, "Cu": 1, "Bi": 9.51, "In": 9.49},
        {"Sn": 79, "Ag": 1, "Cu": 1, "Bi": 9.49, "In": 9.51},
        db=[],
    )
    assert ds < MAX_STEP_C and dl < MAX_STEP_C


def test_sac_side_of_bi_in_line_is_not_floored_at_190() -> None:
    # 이전: SAC 경로의 In 블록 바닥 190 ℃가 Bi 강하를 되돌려 고상 189 ℃(응고 구간 2 ℃) →
    # 목표 융점 탐색에 '거의 공정' 가짜 후보로 올라왔다. DB 인접 Sn1Ag0.8Cu8In10Bi 실측 159/200.
    solidus, liquidus, _peak, detail = _predict({"Sn": 79, "Ag": 1, "Cu": 1, "Bi": 8, "In": 11})
    assert _classify({"Sn": 79, "Ag": 1, "Cu": 1, "Bi": 8, "In": 11}) == "SAC"
    assert solidus < 175.0
    assert liquidus - solidus > 10.0


@pytest.mark.parametrize(
    ("comp", "solidus", "liquidus"),
    [
        # Wikipedia "Solder alloys" 표 값
        ({"Sn": 43, "Pb": 43, "Bi": 14}, 144.0, 163.0),
        ({"Sn": 16, "Pb": 32, "Bi": 52}, 96.0, 96.0),
        ({"Sn": 34, "Pb": 20, "Bi": 46}, 100.0, 105.0),
        ({"Sn": 62, "Pb": 36, "Ag": 2}, 179.0, 179.0),
    ],
)
def test_sn_pb_bi_and_sn_pb_ag_reference_alloys(comp, solidus, liquidus) -> None:
    s, l, _peak, _detail = _predict(comp)
    assert s == pytest.approx(solidus, abs=10.0)
    assert l == pytest.approx(liquidus, abs=10.0)


def test_pb_contamination_lowers_sn_bi_eutectic_instead_of_raising_it() -> None:
    base = _predict({"Sn": 42, "Bi": 58})
    prev = base[0]
    for pb in (0.5, 1.0, 1.5, 3.0):
        s, _l, _p, _d = _predict({"Sn": 42 - pb, "Bi": 58, "Pb": pb})
        assert s <= prev + 0.2, f"Pb {pb}: solidus {s} rose above {prev}"
        assert s <= 139.5
        prev = s


def test_pb_free_binaries_unchanged_by_ternary_helper() -> None:
    # Pb 또는 Bi가 0이면 3원 보정은 이원 표와 정확히 같아야 한다.
    from test7.melting_predictor import SN_BI_PHASE, SN_PB_PHASE, _interp, _sn_pb_bi_base

    assert _sn_pb_bi_base(42, 0, 58)[:2] == pytest.approx(_interp(58 / 100 * 100, SN_BI_PHASE))
    assert _sn_pb_bi_base(63, 37, 0)[:2] == pytest.approx(_interp(37, SN_PB_PHASE))


def _random_scan(n_trials: int, seed: int):
    rng = random.Random(seed)
    ranges = {
        "Ag": (0, 5), "Cu": (0, 3), "Bi": (0, 60), "In": (0, 20),
        "Sb": (0, 8), "Zn": (0, 10), "Pb": (0, 60), "Ni": (0, 0.3),
    }
    worst = (0.0, None)
    for _ in range(n_trials):
        k = rng.randint(1, 3)
        els = rng.sample(list(ranges), k)
        comp = {e: round(rng.uniform(*ranges[e]), 2) for e in els}
        if sum(comp.values()) > 70:
            continue
        comp["Sn"] = round(100 - sum(comp.values()), 3)
        e = rng.choice(els)
        comp2 = dict(comp)
        comp2[e] = round(comp[e] + 0.05, 3)
        comp2["Sn"] = round(comp["Sn"] - 0.05, 3)
        ds, dl = _step(comp, comp2)
        if max(ds, dl) > worst[0]:
            worst = (max(ds, dl), (comp, e))
    return worst


def test_random_composition_perturbations_have_no_classifier_jumps() -> None:
    # 점검 때 쓴 스캔과 같은 방식(무작위 조성 + 한 원소 0.05 wt%). 이전 최대 19.5 ℃.
    worst, where = _random_scan(600, seed=7)
    assert worst < MAX_STEP_C, f"{worst:.1f} ℃ jump at {where}"


@pytest.mark.parametrize(
    "base",
    [
        {"Sn": 42, "Bi": 58},
        {"Sn": 80, "Bi": 20},
        {"Sn": 96.5, "Ag": 3, "Cu": 0.5},
        {"Sn": 96.5, "Ag": 3.5},
        {"Sn": 99.3, "Cu": 0.7},
        {"Sn": 48, "In": 52},
        {"Sn": 80, "In": 20},
        {"Sn": 91, "Zn": 9},
        {"Sn": 63, "Pb": 37},
        {"Sn": 95, "Sb": 5},
    ],
)
def test_trace_impurity_does_not_switch_family_value(base) -> None:
    # 0.05 wt% 불순물로 계열이 바뀌어 수십 ℃ 튀던 'pb == 0'·'ag == 0' 함정
    for e in ("Pb", "Bi", "Ag", "Cu", "In", "Zn", "Sb", "Ni"):
        if e in base:
            continue
        comp = dict(base)
        comp[e] = 0.05
        comp["Sn"] = base["Sn"] - 0.05
        ds, dl = _step(base, comp)
        assert max(ds, dl) < MAX_STEP_C, f"{base} + 0.05 {e}: Δ {ds:.1f}/{dl:.1f} ℃"
