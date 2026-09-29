# Regression: 원본 희성 요약표(2013-06-28, "종합" 시트)와 solder_db 대조.
# 2026-09-29 사용자가 원본 사진을 제공 → 고상선·액상선이 적힌 모든 행이 DB에 같은 값으로 들어 있는지 고정한다.
# 이전 문제: 요약표에 없는 Sn0.3Ag0.2Cu 217/270(= Sn0.3Ag2.0Cu 소수점 오기), Sn0.5Cu 액상선 312(요약표 227),
#           요약표 실측 저Ag SAC 217/219 7행이 '모순'으로 격리돼 있었음.
# 제외: HSE-55 Sn-5Sb 223/238(7/14 사용자 수정값 238/242와 충돌 — 사용자 확인 대기),
#       HSE-100 Sn-In-Cu-Zn 119/121(조성 수치가 없어 입력 불가).
from __future__ import annotations

import pytest

from test7.solder_db import SOLDER_DB, comp_signature, normalize_comp

# (품명, 조성 wt% (Sn 잔량), 고상선, 액상선, 비중 또는 None)
SOURCE_ROWS = [
    ("HSE-01", {"Cu": 0.5, "Ni": 0.03, "P": 0.015}, 227, 231, 7.3),
    ("HSE-01P", {"Cu": 0.3, "Ni": 0.03, "P": 0.015}, 227, 231, 7.3),
    ("HSE-02", {"Ag": 3.0, "Cu": 0.5, "P": 0.015}, 217, 220, 7.4),
    ("HSE-02P", {"Ag": 3.0, "Cu": 0.5, "Bi": 0.013, "Sb": 0.01}, 217, 220, 7.4),
    ("HSE-04", {"Cu": 0.7, "P": 0.015}, 227, 227, 7.3),
    ("HSE-04(M)", {"Cu": 0.5}, 227, 227, 7.3),
    ("HSE-09", {"Cu": 4.0, "Ni": 0.05, "P": 0.01, "Ga": 0.015}, 228, 355, 7.4),
    ("HSE-10", {"Cu": 3.0, "Ni": 0.5, "P": 0.01, "Ga": 0.015}, 217, 395, 7.4),
    ("HSE-11 SP59", {"Ag": 0.3, "Cu": 0.7, "P": 0.015}, 217, 227, 7.3),
    ("HSE-11 SP86", {"Ag": 0.3, "P": 0.015}, 217, 227, 7.3),
    ("HSE-11(L) SP81", {"Ag": 0.3, "Cu": 0.7}, 217, 227, 7.3),
    ("HSE-16P보충", {"Ni": 0.03, "P": 0.015}, 227, 231, 7.3),
    ("HSE-21", {"Ag": 3.0, "P": 0.15}, 217, 221, 7.36),
    ("HSE-29(D3)", {"Ag": 3.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075}, 217, 219, None),
    ("HSE-29(PE)", {"Ag": 3.0, "Cu": 0.5, "Ni": 0.003, "P": 0.0035}, 217, 219, None),
    ("HSE-29(D3K)", {"Ag": 3.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219, None),
    ("HSE-30(D4)", {"Ag": 4.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075}, 217, 219, None),
    ("HSE-31(D4K)", {"Ag": 4.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219, None),
    ("HSE-32(D27K)", {"Ag": 2.7, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219, None),
    ("HSE-34(D25K)", {"Ag": 2.5, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219, None),
    ("HSE-35", {"P": 0.015}, 230, 232, None),
    ("HSE-38", {"Cu": 3.5, "P": 0.006}, 228, 320, 7.3),
    ("HSE-39", {"Ag": 1.0, "Cu": 0.5, "P": 0.015}, 217, 219, None),
    ("HSE-39A", {"Ag": 1.0, "P": 0.015}, 217, 219, None),
    ("HSE-41(D34K)", {"Ag": 3.4, "Ni": 0.017, "Ge": 0.0075, "P": 0.0035}, 218, 223, None),
    ("HSE-42(R)", {"Ag": 1.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075}, 217, 219, None),
    ("HSE-44(DA)", {"Ag": 3.0, "Cu": 0.2, "Ni": 0.003, "Ge": 0.0075}, 217, 219, None),
    ("HSE-45(NA)", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.05, "Ge": 0.0075}, 217, 219, None),
    ("HSE-46", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.05, "Ge": 0.0035, "P": 0.01}, 217, 219, None),
    ("HSE-48(NB)", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.05, "Ge": 0.0075, "P": 0.0035}, 217, 219, None),
    ("HSE-49(NE)", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.02, "Ge": 0.0085, "P": 0.0035}, 217, 219, None),
]


def _with_sn(elements):
    comp = dict(elements)
    comp["Sn"] = round(100.0 - sum(comp.values()), 4)
    return normalize_comp(comp)


_BY_SIG = {comp_signature(row["comp"]): row for row in SOLDER_DB}


@pytest.mark.parametrize(("code", "elements", "solidus", "liquidus", "density"), SOURCE_ROWS, ids=[r[0] for r in SOURCE_ROWS])
def test_db_matches_source_sheet(code, elements, solidus, liquidus, density) -> None:
    row = _BY_SIG.get(comp_signature(_with_sn(elements)))
    assert row is not None, f"{code}: 요약표 조성이 DB에 없음"
    assert float(row["solidus"]) == pytest.approx(solidus), code
    assert float(row["liquidus"]) == pytest.approx(liquidus), code
    if density is not None:
        assert float(row["density"]) == pytest.approx(density), code


def test_typo_row_removed() -> None:
    names = {row["name"] for row in SOLDER_DB}
    assert "Sn0.3Ag0.2Cu" not in names
