# -*- coding: utf-8 -*-
"""미등록 조성 예측의 그룹 홀드아웃 교차검증과 오차 구간.

DB의 같은 조성 또는 매우 가까운 변형을 한 그룹으로 묶어 함께 제외한 뒤
예측한다. 따라서 사실상 같은 행을 이웃으로 다시 보는 낙관적 누수를 줄인다.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Iterable, List, Sequence


CALIBRATION_VERSION = "group-holdout-v2-adaptive-tensile"
NEAR_DUPLICATE_DISTANCE = 0.25
MIN_FAMILY_SAMPLES = 8


def _percentile(values: Iterable[float], q: float) -> float | None:
    xs = sorted(float(x) for x in values)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = max(0.0, min(1.0, float(q))) * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def _family(comp: Dict[str, Any]) -> str:
    try:
        from .solder_db import classify_family
    except ImportError:
        from test7.solder_db import classify_family
    return str(classify_family(comp))


def _distance(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    try:
        from .utils import composition_distance
    except ImportError:
        from test7.utils import composition_distance
    return float(composition_distance(a, b))


def _cluster_indices(rows: Sequence[Dict[str, Any]]) -> List[List[int]]:
    """합금족이 같고 조성 거리가 가까운 행을 탐욕적으로 한 그룹에 묶는다."""
    groups: List[List[int]] = []
    for idx, row in enumerate(rows):
        comp = row.get("comp") or {}
        fam = _family(comp)
        placed = False
        for group in groups:
            anchor = rows[group[0]]
            if _family(anchor.get("comp") or {}) != fam:
                continue
            if _distance(comp, anchor.get("comp") or {}) <= NEAR_DUPLICATE_DISTANCE:
                group.append(idx)
                placed = True
                break
        if not placed:
            groups.append([idx])
    return groups


def _nearest_distance(comp: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> float | None:
    vals = [_distance(comp, row.get("comp") or {}) for row in rows if row.get("comp")]
    return min(vals) if vals else None


def _summary(records: Sequence[Dict[str, Any]], property_key: str) -> Dict[str, Any]:
    selected = [r for r in records if r.get("property") == property_key]
    errors = [float(r["absolute_error"]) for r in selected]
    distances = [float(r["nearest_distance"]) for r in selected]
    p90 = _percentile(errors, 0.90)
    return {
        "sample_count": len(selected),
        "mae": round(sum(errors) / len(errors), 3) if errors else None,
        "median_absolute_error": (
            round(float(_percentile(errors, 0.50)), 3) if errors else None
        ),
        "p90_absolute_error": round(float(p90), 3) if p90 is not None else None,
        "p95_absolute_error": (
            round(float(_percentile(errors, 0.95)), 3) if errors else None
        ),
        "empirical_coverage": (
            round(sum(1 for e in errors if e <= float(p90)) / len(errors), 3)
            if errors and p90 is not None
            else None
        ),
        "distance_q90": (
            round(float(_percentile(distances, 0.90)), 4) if distances else None
        ),
        "distance_q99": (
            round(float(_percentile(distances, 0.99)), 4) if distances else None
        ),
        "interval_kind": "empirical_group_holdout_absolute_residual_90pct",
        "calibration_version": CALIBRATION_VERSION,
    }


def _melting_records() -> List[Dict[str, Any]]:
    try:
        from .melting_predictor import hybrid_melting_predict
        from .solder_db import SOLDER_DB
    except ImportError:
        from test7.melting_predictor import hybrid_melting_predict
        from test7.solder_db import SOLDER_DB

    rows = [
        {
            "name": str(row.get("name") or ""),
            "comp": dict(row.get("comp") or {}),
            "solidus": float(row["solidus"]),
            "liquidus": float(row["liquidus"]),
        }
        for row in SOLDER_DB
        if row.get("comp") and row.get("solidus") is not None and row.get("liquidus") is not None
    ]
    records: List[Dict[str, Any]] = []
    for group in _cluster_indices(rows):
        held = set(group)
        train = [row for i, row in enumerate(rows) if i not in held]
        if len(train) < 3:
            continue
        for idx in group:
            row = rows[idx]
            solidus, liquidus, _peak, _detail = hybrid_melting_predict(
                row["comp"], train, ai_engine=None
            )
            nearest = _nearest_distance(row["comp"], train)
            if nearest is None:
                continue
            fam = _family(row["comp"])
            for key, predicted in (("solidus_c", solidus), ("liquidus_c", liquidus)):
                actual = float(row["solidus" if key == "solidus_c" else "liquidus"])
                records.append(
                    {
                        "property": key,
                        "family": fam,
                        "nearest_distance": nearest,
                        "absolute_error": abs(float(predicted) - actual),
                    }
                )
    return records


def _tensile_anchors() -> List[Dict[str, Any]]:
    try:
        from .SOLDER_PROPERTIES_DB import SOLDER_PROPERTIES_DB
        from .db_regression import parse_alloy
    except ImportError:
        from test7.SOLDER_PROPERTIES_DB import SOLDER_PROPERTIES_DB
        from test7.db_regression import parse_alloy

    grouped: Dict[str, Dict[str, Any]] = {}
    for row in SOLDER_PROPERTIES_DB:
        value = row.get("tensile")
        name = str(row.get("alloy") or "").strip()
        if not name or value is None:
            continue
        item = grouped.setdefault(name, {"name": name, "values": []})
        item["values"].append(float(value))
    out: List[Dict[str, Any]] = []
    for name, item in grouped.items():
        comp = parse_alloy(name)
        values = item["values"]
        if not comp or not values:
            continue
        out.append(
            {
                "name": name,
                "comp": dict(comp),
                "tensile": sum(values) / len(values),
                "n": len(values),
            }
        )
    out.sort(key=lambda x: x["name"])
    return out


def _predict_tensile(comp: Dict[str, Any], train: Sequence[Dict[str, Any]]) -> float | None:
    try:
        from .db_regression import _select_tensile_candidates
    except ImportError:
        from test7.db_regression import _select_tensile_candidates

    ranked = sorted(((_distance(comp, row["comp"]), row) for row in train), key=lambda x: x[0])
    selected_rows = _select_tensile_candidates(
        [(str(row["name"]), float(dist)) for dist, row in ranked]
    )
    selected_names = {name for name, _dist in selected_rows}
    top = [(dist, row) for dist, row in ranked if str(row["name"]) in selected_names]
    weighted: List[tuple[float, float]] = []
    for dist, row in top:
        weight = (1.0 / (1.0 + float(dist))) * max(1, int(row.get("n") or 1))
        weighted.append((float(row["tensile"]), weight))
    total = sum(w for _, w in weighted)
    return sum(v * w for v, w in weighted) / total if total > 0 else None


def _tensile_records() -> List[Dict[str, Any]]:
    rows = _tensile_anchors()
    records: List[Dict[str, Any]] = []
    for group in _cluster_indices(rows):
        held = set(group)
        train = [row for i, row in enumerate(rows) if i not in held]
        if len(train) < 3:
            continue
        for idx in group:
            row = rows[idx]
            predicted = _predict_tensile(row["comp"], train)
            nearest = _nearest_distance(row["comp"], train)
            if predicted is None or nearest is None:
                continue
            records.append(
                {
                    "property": "tensile_strength_mpa",
                    "family": _family(row["comp"]),
                    "nearest_distance": nearest,
                    "absolute_error": abs(float(predicted) - float(row["tensile"])),
                }
            )
    return records


@lru_cache(maxsize=1)
def calibration_report() -> Dict[str, Any]:
    records = _melting_records() + _tensile_records()
    properties = ("solidus_c", "liquidus_c", "tensile_strength_mpa")
    families = sorted({str(r["family"]) for r in records})
    return {
        "version": CALIBRATION_VERSION,
        "group_distance": NEAR_DUPLICATE_DISTANCE,
        "minimum_family_samples": MIN_FAMILY_SAMPLES,
        "properties": {
            prop: {
                "global": _summary(records, prop),
                "families": {
                    fam: _summary(
                        [r for r in records if str(r.get("family")) == fam], prop
                    )
                    for fam in families
                },
            }
            for prop in properties
        },
    }


def validation_profile(property_key: str, family: str) -> Dict[str, Any]:
    report = calibration_report()
    prop = (report.get("properties") or {}).get(property_key) or {}
    family_profile = ((prop.get("families") or {}).get(family) or {})
    if int(family_profile.get("sample_count") or 0) >= MIN_FAMILY_SAMPLES:
        out = dict(family_profile)
        out["cohort"] = f"family:{family}"
        out["family_fallback"] = False
        return out
    out = dict(prop.get("global") or {})
    out["cohort"] = "global"
    out["family_fallback"] = True
    out["requested_family"] = family
    out["family_sample_count"] = int(family_profile.get("sample_count") or 0)
    return out


def tensile_anchor_count() -> int:
    return len(_tensile_anchors())
