# -*- coding: utf-8 -*-
"""인장·전단 등 기계적 물성 외부 문헌과 레거시 내부 참고치.

- 표준 시험편·변형률·온도에 따라 편차가 크므로 **범위(min–max)** 와 대표값(median)을 함께 둡니다.
- 원출처가 없는 레거시 내부 DB 평균은 측정·문헌 근거가 아닌 참고값으로만 노출합니다.
- UI·evidence용 메타이며, 최종 적합성은 고객 시험 조건으로 확인해야 합니다.
"""
from __future__ import annotations

from .db_regression import parse_alloy
from .utils import composition_distance

# alloy: solder_db 연속 BD명, comp: parse_alloy 결과와 동일 조성
STRENGTH_LITERATURE_ANCHORS: list[dict] = [
    {
        "alloy": "Sn3.0Ag0.5Cu",
        "comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        "tensile_mpa": 40.95,
        "tensile_range": (31.0, 55.0),
        "yield_mpa": 36.2,
        "elongation_pct": 29.0,
        "source": "SAC305 인장 시험 (bulk solder)",
        "citation": "Sn-Ag-Cu mechanical properties review, SAC305 UTS 40.95 MPa",
        "doi": "10.1515/pmp-2018-0006",
        "url": "https://doi.org/10.1515/pmp-2018-0006",
    },
    {
        "alloy": "Sn3.0Ag0.5Cu",
        "comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        "tensile_mpa": 45.0,
        "tensile_range": (40.0, 50.0),
        "source": "SAC305 TDS (room-temperature tensile)",
        "citation": "Array Solders SAC305 product datasheet",
        "url": "https://arraysolders.com/wp-content/uploads/2023/06/TDS-for-Sac305.pdf",
    },
    {
        "alloy": "Sn0.7Cu",
        "comp": {"Sn": 99.3, "Cu": 0.7},
        "tensile_mpa": 30.5,
        "elongation_pct": 60.0,
        "source": "Sn-0.7Cu bulk tensile (25 °C)",
        "citation": "Co-added Sn-0.7Cu study, baseline UTS 30.5 MPa",
        "doi": "10.1007/s10854-023-09967-7",
        "url": "https://doi.org/10.1007/s10854-023-09967-7",
    },
    {
        "alloy": "Sn0.7Cu",
        "comp": {"Sn": 99.3, "Cu": 0.7},
        "tensile_mpa": 38.72,
        "tensile_range": (32.0, 39.0),
        "yield_mpa": 32.29,
        "source": "SnCu0.7 powder datasheet (RT)",
        "citation": "Stanford Advanced Materials SnCu0.7 mechanical data",
        "url": "https://www.samaterials.com/sncu0-7-tin-based-alloy-solder-powder.html",
    },
    {
        "alloy": "Sn4.0Ag0.5Cu",
        "comp": {"Sn": 95.5, "Ag": 4.0, "Cu": 0.5},
        "tensile_mpa": 43.70,
        "tensile_range": (41.0, 46.0),
        "source": "SAC405 vs SAC305 tensile comparison",
        "citation": "SAC405 UTS 43.70 MPa (Ag↑ → UTS↑)",
        "doi": "10.1515/pmp-2018-0006",
        "url": "https://doi.org/10.1515/pmp-2018-0006",
    },
    {
        "alloy": "Sn2.0Ag0.5Cu1Bi",
        "comp": {"Sn": 96.5, "Ag": 2.0, "Cu": 0.5, "Bi": 1.0},
        "tensile_mpa": 43.7,
        "tensile_range": (38.0, 48.0),
        "elongation_pct": 13.0,
        "source": "SAC205 + 1 wt% Bi (SAC305의 Ag 1 wt% 대체) bulk tensile",
        "citation": "SAC205-1Bi (SAC305의 Ag 1 wt%를 Bi 1 wt%로 대체), UTS 43.7 MPa",
        "doi": "10.3390/met12081245",
        "url": "https://doi.org/10.3390/met12081245",
    },
    {
        "alloy": "Sn57.6Bi0.4Ag",
        "comp": {"Sn": 42.0, "Bi": 57.6, "Ag": 0.4},
        "tensile_mpa": 58.7,
        "yield_mpa": 46.0,
        "source": "Sn57.6Bi0.4Ag as-cast bulk tensile (room temperature, 0.75 mm/min, n=5)",
        "citation": "Ren & Collins (2019), Sn57.6Bi0.4Ag UTS 58.7 MPa",
        "doi": "10.3390/met9040462",
        "url": "https://doi.org/10.3390/met9040462",
    },
]

# 레거시 내부 DB 대표값 — 숫자 일관성 확인용 참고 앵커입니다.
# 원문헌/원시험 기록과 시험조건을 복구하기 전에는 측정 근거나 비교 근거로 취급하지 않습니다.
_LEGACY_INTERNAL_DB_ANCHORS: list[dict] = [
    {
        "alloy": "Sn3.0Ag0.5Cu",
        "tensile_mpa": 48.5,
        "shear_mpa": 84.5,
        "source": "레거시 내부 DB 평균",
        "source_kind": "legacy_internal_db_mean",
        "value_type": "legacy_internal_db_mean",
        "provenance_status": "unconfirmed",
        "verification_status": "unverified",
        "comparison_allowed": False,
        "source_link_status": "unavailable",
    },
    {
        "alloy": "Sn0.7Cu",
        "tensile_mpa": 38.0,
        "shear_mpa": 58.0,
        "source": "레거시 내부 DB 평균",
        "source_kind": "legacy_internal_db_mean",
        "value_type": "legacy_internal_db_mean",
        "provenance_status": "unconfirmed",
        "verification_status": "unverified",
        "comparison_allowed": False,
        "source_link_status": "unavailable",
    },
    {
        "alloy": "Sn3.0Ag0.5Cu3Bi",
        "tensile_mpa": 78.0,
        "shear_mpa": 28.0,
        "source": "레거시 내부 DB 평균",
        "source_kind": "legacy_internal_db_mean",
        "value_type": "legacy_internal_db_mean",
        "provenance_status": "unconfirmed",
        "verification_status": "unverified",
        "comparison_allowed": False,
        "source_link_status": "unavailable",
    },
]


def _median(values: list[float]) -> float:
    xs = sorted(values)
    n = len(xs)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


def nearest_strength_literature(
    comp: dict,
    *,
    max_dist: float = 4.0,
    top_k: int = 3,
) -> dict | None:
    """가까운 문헌 앵커와 레거시 내부 참고값을 출처 상태와 함께 반환."""
    if not isinstance(comp, dict) or not comp:
        return None

    ranked: list[tuple[float, dict]] = []
    for anchor in STRENGTH_LITERATURE_ANCHORS:
        ref = anchor.get("comp")
        if not isinstance(ref, dict):
            continue
        d = composition_distance(comp, ref)
        if d <= max_dist:
            ranked.append((d, anchor))

    ranked.sort(key=lambda x: x[0])
    top = ranked[: max(1, int(top_k))]
    tensiles = [float(a["tensile_mpa"]) for _, a in top if a.get("tensile_mpa") is not None]

    # 레거시 내부 DB 앵커 (가까우면 참고값으로만 병기)
    internal = None
    for row in _LEGACY_INTERNAL_DB_ANCHORS:
        try:
            ref = parse_alloy(row["alloy"])
            d = composition_distance(comp, ref)
            if internal is None or d < internal[0]:
                internal = (d, row)
        except Exception:
            continue
    internal_in_range = internal is not None and internal[0] <= max_dist
    if not top and not internal_in_range:
        return None

    refs_out = []
    for d, a in top:
        refs_out.append(
            {
                "alloy": a.get("alloy"),
                "dist": round(d, 3),
                "tensile_mpa": a.get("tensile_mpa"),
                "tensile_range": a.get("tensile_range"),
                "source": a.get("source"),
                "citation": a.get("citation"),
                "doi": a.get("doi"),
                "url": a.get("url"),
                "source_link_status": (
                    "available" if a.get("doi") or a.get("url") else "unavailable"
                ),
            }
        )

    if internal_in_range:
        refs_out.append(
            {
                "alloy": internal[1]["alloy"],
                "dist": round(internal[0], 3),
                "tensile_mpa": internal[1].get("tensile_mpa"),
                "shear_mpa": internal[1].get("shear_mpa"),
                "source": internal[1].get("source"),
                "source_kind": internal[1].get("source_kind"),
                "value_type": internal[1].get("value_type"),
                "provenance_status": internal[1].get("provenance_status"),
                "verification_status": internal[1].get("verification_status"),
                "comparison_allowed": internal[1].get("comparison_allowed"),
                "source_link_status": internal[1].get("source_link_status"),
            }
        )

    ranges = [a["tensile_range"] for _, a in top if a.get("tensile_range")]
    tensile_range = None
    if ranges:
        tensile_range = (min(r[0] for r in ranges), max(r[1] for r in ranges))

    return {
        # 레거시 내부 DB 수치는 refs에서만 제공한다. 문헌 집계값으로 승격하지 않는다.
        "tensile_mpa": _median(tensiles) if tensiles else None,
        "tensile_range": tensile_range,
        "best_dist": top[0][0] if top else None,
        "refs": refs_out,
    }


def strength_literature_lines(comp: dict, *, max_lines: int = 6) -> list[str]:
    """AI·리포트 evidence용 한 줄 참고 문구."""
    hit = nearest_strength_literature(comp)
    if not hit:
        return []
    lines: list[str] = []
    for ref in (hit.get("refs") or [])[:max_lines]:
        is_legacy_internal = ref.get("source_kind") == "legacy_internal_db_mean"
        parts = [
            f"[{'LegacyStrengthDB' if is_legacy_internal else 'StrengthLit'}] {ref.get('alloy', '?')}",
            f"UTS≈{ref.get('tensile_mpa')} MPa" if ref.get("tensile_mpa") is not None else None,
            f"전단≈{ref.get('shear_mpa')} MPa" if ref.get("shear_mpa") is not None else None,
            ref.get("source"),
        ]
        if ref.get("doi"):
            parts.append(f"DOI:{ref['doi']}")
        if ref.get("url"):
            parts.append(f"URL:{ref['url']}")
        if not ref.get("doi") and not ref.get("url"):
            parts.append("원출처 링크 미확인 · 시험조건 미확인 · 참고 전용")
        line = " — ".join(p for p in parts if p)
        if line:
            lines.append(line)
    return lines
