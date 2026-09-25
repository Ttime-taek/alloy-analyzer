# Regression: 2026-09-25 계산 로직 점검 P3 — 상 서술이 계산 결과와 모순됐다. Bi 5 % 이상이면 항상
# "고상선–액상선 간격이 좁아짐"이라 했지만 앱 자체 결과 Sn80Bi20은 139/199 ℃(간격 60 ℃),
# Ag ≥ 2 %면 "초기 석출 판상 Ag₃Sn"이라 했지만 초정 판상은 과공정(Ag > 3.5 %) 문제. Pb·In·Zn 서술 없음.
# Found by 계산 로직 점검 (Claude) on 2026-09-25
from __future__ import annotations

from test7.phase import PhasePredictor, analyze_phase


def test_hypoeutectic_bi_says_range_widens() -> None:
    out = PhasePredictor().predict({"Sn": 80.0, "Bi": 20.0}, solidus=139.0, liquidus=198.9)
    assert "좁아지는" not in out
    assert "넓어짐" in out
    assert "59.9 ℃" in out


def test_eutectic_bi_says_range_is_narrow() -> None:
    out = PhasePredictor().predict({"Sn": 42.0, "Bi": 58.0}, solidus=139.0, liquidus=139.0)
    assert "공정" in out and "좁" in out


def test_primary_plate_ag3sn_only_for_hypereutectic_ag() -> None:
    assert "초정" not in PhasePredictor().predict({"Sn": 96.5, "Ag": 3.0, "Cu": 0.5})
    assert "초정" in PhasePredictor().predict({"Sn": 95.5, "Ag": 3.8, "Cu": 0.7})


def test_pb_bi_mentions_ternary_eutectic_and_pb_in_zn_notes_exist() -> None:
    out = PhasePredictor().predict({"Sn": 43.0, "Pb": 43.0, "Bi": 14.0})
    assert "96" in out and "Sn–Pb" in out
    assert "In–Sn 공정" in PhasePredictor().predict({"Sn": 90.0, "In": 10.0})
    assert "Sn91Zn9" in PhasePredictor().predict({"Sn": 91.0, "Zn": 9.0})


def test_analyze_phase_passes_melting_range() -> None:
    assert "예측 고상선–액상선 간격" in analyze_phase({"Sn": 80, "Bi": 20}, 139.0, 198.9)
