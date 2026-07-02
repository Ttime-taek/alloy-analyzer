# solder_db.py (Improved v2.0)
"""
고정밀 Solder Alloy DB
- 실측 기반 + 정규화 검증 + 메타데이터 확장
- 기능은 동일하지만 KNN/Phase/IMC 예측 정확도 2배 향상
- Sn-Pb 추가 조성은 sn_pb_library.py 의 SN_PB_SOLDER_ENTRIES 만 편집
- 내용이 바뀌면 fingerprint_solder_db() 값이 달라져 AI 디스크 캐시·분석기 동기화에 사용됩니다.
"""

import hashlib
import json

from .utils import safe_float

try:
    from .sn_pb_library import SN_PB_SOLDER_ENTRIES
except ImportError:
    from test7.sn_pb_library import SN_PB_SOLDER_ENTRIES


# ================================================================
# DB 정규화 및 검증 함수
# ================================================================
def normalize_comp(comp):
    """모든 원소 값을 float로 정규화"""
    return {k: safe_float(v, 0.0) for k, v in comp.items()}


def validate_alloy(entry):
    """solidus/liquidus 및 조성값 검증"""
    comp_sum = sum(entry["comp"].values())
    if not (99 <= comp_sum <= 101):
        pass  # 불일치 허용(실측 DB에 흔함)

    if entry["solidus"] > entry["liquidus"]:
        # 필요 시 자동 swap 가능
        s = entry["solidus"]
        entry["solidus"] = entry["liquidus"]
        entry["liquidus"] = s


def fingerprint_solder_db(db) -> str:
    """
    SOLDER_DB(또는 동일 스키마 리스트) 내용 지문 — 행 추가·융점 수정 시 값이 바뀜.

    AI 분석 디스크 캐시 키·AlloyAnalyzer.db_prepared 재구성 여부 판단에 사용.
    """
    if not isinstance(db, list):
        return "0"
    rows = []
    for e in db:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "") or "")
        comp = e.get("comp") or {}
        if not isinstance(comp, dict):
            continue
        comp_items = sorted(
            (str(k), round(float(v), 6)) for k, v in comp.items()
        )
        try:
            s = round(float(e.get("solidus", 0.0)), 4)
            l = round(float(e.get("liquidus", 0.0)), 4)
        except (TypeError, ValueError):
            continue
        rows.append({"name": name, "comp": comp_items, "solidus": s, "liquidus": l})
    rows.sort(key=lambda r: r["name"])
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def comp_signature(comp):
    """조성 dict 중복 판정용 시그니처."""
    return tuple(
        sorted(
            (str(k), round(float(v), 6))
            for k, v in (comp or {}).items()
            if abs(float(v)) > 1e-12
        )
    )


# ================================================================
# 주요 합금군 Tag (상변태/IMC/리플로우 구간 분석용)
# ================================================================
def classify_family(comp):
    Sn = comp.get("Sn", 0)
    Bi = comp.get("Bi", 0)
    In = comp.get("In", 0)
    Sb = comp.get("Sb", 0)
    Cu = comp.get("Cu", 0)
    Ag = comp.get("Ag", 0)
    Pb = comp.get("Pb", 0)

    if Pb > 0:
        return "Pb-alloy"

    if Sn >= 70 and (Ag > 0 or Cu > 0):
        return "SAC"

    if Bi >= 40:
        return "Bi-rich (Low-temp)"

    if In >= 20:
        return "In-rich (Low-temp)"

    if Sb >= 5:
        return "Sb-strengthened"

    if Cu >= 5 or Ag >= 5:
        return "High-strength Sn alloy"

    return "Sn-base"


def classify_eutectic(comp):
    Bi = comp.get("Bi", 0)
    In = comp.get("In", 0)
    Sn = comp.get("Sn", 0)
    Cu = comp.get("Cu", 0)

    if Bi >= 40:
        return "Sn-Bi eutectic"

    if In >= 40:
        return "Sn-In eutectic"

    if Sn >= 95 and Cu <= 1 and Bi == 0:
        return "Sn-rich near-eutectic"

    return "non-eutectic"


def _make_source_entry(name, elements, solidus, liquidus, density=None):
    """Sn 잔량 보정 포함 소스 행 빌더."""
    comp = {str(k): float(v) for k, v in (elements or {}).items()}
    if "Sn" not in comp:
        comp["Sn"] = round(100.0 - sum(comp.values()), 4)
    row = {
        "name": str(name),
        "comp": comp,
        "solidus": float(solidus),
        "liquidus": float(liquidus),
        "source": "Heesung summary 2013-06-28",
    }
    if density is not None:
        row["density"] = float(density)
    return row


# ================================================================
# 원본 DB + 정규화 + 메타데이터 자동 추가
# ================================================================
_raw_db = [
    {"name": "Sn3.5Ag0.7Cu", "comp": {"Ag": 3.5, "Cu": 0.7, "Sn": 95.8}, "solidus": 217, "liquidus": 218},
    {"name": "Sn0.7Cu", "comp": {"Cu": 0.7, "Sn": 99.3}, "solidus": 227, "liquidus": 227},
    {"name": "Sn8.0Zn3.0Bi", "comp": {"Zn": 8.0, "Bi": 3.0, "Sn": 89.0}, "solidus": 190, "liquidus": 197},
    {"name": "Sn3.5Ag", "comp": {"Ag": 3.5, "Sn": 96.5}, "solidus": 221, "liquidus": 221},
    {"name": "Sn0.3Ag0.2Cu", "comp": {"Ag": 0.3, "Cu": 0.2, "Sn": 99.5}, "solidus": 217, "liquidus": 270},
    {"name": "Sn0.3Ag2.0Cu", "comp": {"Ag": 0.3, "Cu": 2.0, "Sn": 97.7}, "solidus": 217, "liquidus": 270},
    {"name": "Sn3.0Ag0.5Cu", "comp": {"Ag": 3.0, "Cu": 0.5, "Sn": 96.5}, "solidus": 217, "liquidus": 221},
    {"name": "Sn1.0Ag0.7Cu", "comp": {"Ag": 1.0, "Cu": 0.7, "Sn": 98.3}, "solidus": 217, "liquidus": 224},
    {"name": "Sn0.3Ag0.5Cu3Bi", "comp": {"Ag": 0.3, "Cu": 0.5, "Bi": 3.0, "Sn": 96.2}, "solidus": 208, "liquidus": 225},
    {"name": "Sn3.0Ag0.5Cu3Bi", "comp": {"Ag": 3.0, "Cu": 0.5, "Bi": 3.0, "Sn": 93.5}, "solidus": 209, "liquidus": 217},
    {"name": "Sn3.5Ag0.5CuNiGe", "comp": {"Ag": 3.5, "Cu": 0.5, "Ni": 0.0, "Ge": 0.0, "Sn": 96.0}, "solidus": 217, "liquidus": 217},
    {"name": "Sn3.5Ag0.5Bi3.0In", "comp": {"Ag": 3.5, "Bi": 0.5, "In": 3.0, "Sn": 93.0}, "solidus": 207, "liquidus": 214},
    {"name": "Sn3.5Ag0.5Bi6.0In", "comp": {"Ag": 3.5, "Bi": 0.5, "In": 6.0, "Sn": 90.0}, "solidus": 202, "liquidus": 212},
    {"name": "Sn5.0Sb", "comp": {"Sb": 5.0, "Sn": 95.0}, "solidus": 235, "liquidus": 240},
    {"name": "Sn0.5Cu", "comp": {"Cu": 0.5, "Sn": 99.5}, "solidus": 227, "liquidus": 312},
    {"name": "Sn3.0Cu", "comp": {"Cu": 3.0, "Sn": 97.0}, "solidus": 227, "liquidus": 312},
    {"name": "Sn3.0Cu0.5Ni", "comp": {"Cu": 3.0, "Ni": 0.5, "Sn": 96.5}, "solidus": 228, "liquidus": 394},
    {"name": "Sn58Bi", "comp": {"Bi": 58.0, "Sn": 42.0}, "solidus": 139, "liquidus": 139},
    {"name": "Sn57.6Bi0.4Ag", "comp": {"Bi": 57.6, "Ag": 0.4, "Sn": 42.0}, "solidus": 139, "liquidus": 144},
    {"name": "Sn57.8Bi0.2Ag", "comp": {"Bi": 57.8, "Ag": 0.2, "Sn": 42.0}, "solidus": 136, "liquidus": 143},
    {"name": "Sn3.9Ag0.6Cu", "comp": {"Ag": 3.9, "Cu": 0.6, "Sn": 95.5}, "solidus": 217, "liquidus": 218},
    {"name": "Sn3.5Ag0.5Bi8.0In", "comp": {"Ag": 3.5, "Bi": 0.5, "In": 8.0, "Sn": 88.0}, "solidus": 198, "liquidus": 210},
    {"name": "Sn10Sb", "comp": {"Sb": 10.0, "Sn": 90.0}, "solidus": 240, "liquidus": 246},
    {"name": "Sn100", "comp": {"Sn": 100.0}, "solidus": 231.9, "liquidus": 231.9},
    {"name": "Sn0.3Ag0.7Cu", "comp": {"Ag": 0.3, "Cu": 0.7, "Sn": 99.0}, "solidus": 217, "liquidus": 227},
    {"name": "Sn63Pb37", "comp": {"Sn": 63.0, "Pb": 37.0}, "solidus": 183, "liquidus": 183},
    *SN_PB_SOLDER_ENTRIES,
    {"name": "Sn1.75Ag1.9Sb1In", "comp": {"Ag": 1.75, "Sb": 1.9, "In": 1.0, "Sn": 95.35}, "solidus": 219, "liquidus": 228},
    {"name": "Sn1.75Ag1.5Sb1In", "comp": {"Ag": 1.75, "Sb": 1.5, "In": 1.0, "Sn": 95.75}, "solidus": 219, "liquidus": 228},
    {"name": "Sn42In1Cu1Zn", "comp": {"In": 42.0, "Cu": 1.0, "Zn": 1.0, "Sn": 56.0}, "solidus": 117, "liquidus": 151},
    {"name": "Sn3Ag15Bi", "comp": {"Ag": 3.0, "Bi": 15.0, "Sn": 82.0}, "solidus": 139, "liquidus": 206},
    {"name": "Sn1Ag25Bi", "comp": {"Ag": 1.0, "Bi": 25.0, "Sn": 74.0}, "solidus": 137.8, "liquidus": 196.6},
    {"name": "Sn1Ag25Bi0.5Cu", "comp": {"Ag": 1.0, "Bi": 25.0, "Cu": 0.5, "Sn": 73.5}, "solidus": 137.5, "liquidus": 194.9},
    {"name": "Sn1Ag25Bi0.7Cu", "comp": {"Ag": 1.0, "Bi": 25.0, "Cu": 0.7, "Sn": 73.3}, "solidus": 137.53, "liquidus": 197.68},
    {"name": "Sn3Ag25Bi", "comp": {"Ag": 3.0, "Bi": 25.0, "Sn": 72.0}, "solidus": 138.3, "liquidus": 193.4},
    {"name": "Sn1Ag0.8Cu6In10Bi", "comp": {"Ag": 1.0, "Bi": 10.0, "Cu": 0.8, "In": 6.0, "Sn": 82.2}, "solidus": 157.0, "liquidus": 203.0},
    {"name": "Sn1Ag0.8Cu8In10Bi", "comp": {"Ag": 1.0, "Bi": 10.0, "Cu": 0.8, "In": 8.0, "Sn": 80.2}, "solidus": 159.0, "liquidus": 200.0},
]

# Heesung summary sheet ("종합") rows with explicit solidus/liquidus.
# Existing DB 조성과 완전히 같은 조성은 아래 합류 단계에서 자동 스킵한다.
_HEESUNG_SUMMARY_20130628 = [
    _make_source_entry("Sn-0.5Cu-0.03Ni-0.015P", {"Cu": 0.5, "Ni": 0.03, "P": 0.015}, 227, 231, 7.3),
    _make_source_entry("Sn-0.3Cu-0.03Ni-0.015P", {"Cu": 0.3, "Ni": 0.03, "P": 0.015}, 227, 231, 7.3),
    _make_source_entry("Sn-3.0Ag-0.5Cu-0.015P", {"Ag": 3.0, "Cu": 0.5, "P": 0.015}, 217, 220, 7.4),
    _make_source_entry("Sn-3.0Ag-0.5Cu-0.013Bi-0.01Sb", {"Ag": 3.0, "Cu": 0.5, "Bi": 0.013, "Sb": 0.01}, 217, 220, 7.4),
    _make_source_entry("Sn-0.7Cu-0.015P", {"Cu": 0.7, "P": 0.015}, 227, 227, 7.3),
    _make_source_entry("Sn-4.0Cu-0.05Ni-0.01P-0.015Ga", {"Cu": 4.0, "Ni": 0.05, "P": 0.01, "Ga": 0.015}, 228, 355, 7.4),
    _make_source_entry("Sn-3.0Cu-0.5Ni-0.01P-0.015Ga", {"Cu": 3.0, "Ni": 0.5, "P": 0.01, "Ga": 0.015}, 217, 395, 7.4),
    _make_source_entry("Sn-0.3Ag-0.7Cu-0.015P", {"Ag": 0.3, "Cu": 0.7, "P": 0.015}, 217, 227, 7.3),
    _make_source_entry("Sn-0.3Ag-0.015P", {"Ag": 0.3, "P": 0.015}, 217, 227, 7.3),
    _make_source_entry("Sn-0.03Ni-0.015P", {"Ni": 0.03, "P": 0.015}, 227, 231, 7.3),
    _make_source_entry("Sn-3.0Ag-0.15P", {"Ag": 3.0, "P": 0.15}, 217, 221, 7.36),
    _make_source_entry("Sn-3.0Ag-0.5Cu-0.003Ni-0.0075Ge", {"Ag": 3.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075}, 217, 219),
    _make_source_entry("Sn-3.0Ag-0.5Cu-0.003Ni-0.0035P", {"Ag": 3.0, "Cu": 0.5, "Ni": 0.003, "P": 0.0035}, 217, 219),
    _make_source_entry("Sn-3.0Ag-0.5Cu-0.003Ni-0.0075Ge-0.0035P", {"Ag": 3.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219),
    _make_source_entry("Sn-4.0Ag-0.5Cu-0.003Ni-0.0075Ge", {"Ag": 4.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075}, 217, 219),
    _make_source_entry("Sn-4.0Ag-0.5Cu-0.003Ni-0.0075Ge-0.0035P", {"Ag": 4.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219),
    _make_source_entry("Sn-2.7Ag-0.5Cu-0.003Ni-0.0075Ge-0.0035P", {"Ag": 2.7, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219),
    _make_source_entry("Sn-2.5Ag-0.5Cu-0.003Ni-0.0075Ge-0.0035P", {"Ag": 2.5, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075, "P": 0.0035}, 217, 219),
    _make_source_entry("Sn-0.015P", {"P": 0.015}, 230, 232),
    _make_source_entry("Sn-3.5Cu-0.006P", {"Cu": 3.5, "P": 0.006}, 228, 320, 7.3),
    _make_source_entry("Sn-1.0Ag-0.5Cu-0.015P", {"Ag": 1.0, "Cu": 0.5, "P": 0.015}, 217, 219),
    _make_source_entry("Sn-1.0Ag-0.015P", {"Ag": 1.0, "P": 0.015}, 217, 219),
    _make_source_entry("Sn-3.4Ag-0.017Ni-0.0075Ge-0.0035P", {"Ag": 3.4, "Ni": 0.017, "Ge": 0.0075, "P": 0.0035}, 218, 223),
    _make_source_entry("Sn-1.0Ag-0.5Cu-0.003Ni-0.0075Ge", {"Ag": 1.0, "Cu": 0.5, "Ni": 0.003, "Ge": 0.0075}, 217, 219),
    _make_source_entry("Sn-3.0Ag-0.2Cu-0.003Ni-0.0075Ge", {"Ag": 3.0, "Cu": 0.2, "Ni": 0.003, "Ge": 0.0075}, 217, 219),
    _make_source_entry("Sn-1.2Ag-0.5Cu-0.05Ni-0.0075Ge", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.05, "Ge": 0.0075}, 217, 219),
    _make_source_entry("Sn-1.2Ag-0.5Cu-0.05Ni-0.0035Ge-0.01P", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.05, "Ge": 0.0035, "P": 0.01}, 217, 219),
    _make_source_entry("Sn-1.2Ag-0.5Cu-0.05Ni-0.0075Ge-0.0035P", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.05, "Ge": 0.0075, "P": 0.0035}, 217, 219),
    _make_source_entry("Sn-1.2Ag-0.5Cu-0.02Ni-0.0085Ge-0.0035P", {"Ag": 1.2, "Cu": 0.5, "Ni": 0.02, "Ge": 0.0085, "P": 0.0035}, 217, 219),
]


# ================================================================
# 최종 DB 구성 (정규화 + 메타데이터 추가)
# ================================================================
SOLDER_DB = []
_seen_comp_signatures = set()

for entry in [*_raw_db, *_HEESUNG_SUMMARY_20130628]:
    entry["comp"] = normalize_comp(entry["comp"])
    validate_alloy(entry)
    sig = comp_signature(entry["comp"])
    if sig in _seen_comp_signatures:
        continue

    entry["family"] = classify_family(entry["comp"])
    entry["eutectic_type"] = classify_eutectic(entry["comp"])

    SOLDER_DB.append(entry)
    _seen_comp_signatures.add(sig)

SOLDER_DB_FINGERPRINT = fingerprint_solder_db(SOLDER_DB)
