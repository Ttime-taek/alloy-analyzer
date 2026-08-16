# -*- coding: utf-8 -*-
"""미등록 합금 예측을 위한 버전 고정 응답 계약과 사용 판정."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable

try:
    from .app_meta import API_VERSION_SEMVER
    from .melting_predictor import DB_EXACT_MATCH_EPS, MELTING_ENGINE_VERSION
    from .prediction_validation import CALIBRATION_VERSION, validation_profile
    from .solder_db import SOLDER_DB_FINGERPRINT, classify_family
except ImportError:
    from test7.app_meta import API_VERSION_SEMVER
    from test7.melting_predictor import DB_EXACT_MATCH_EPS, MELTING_ENGINE_VERSION
    from test7.prediction_validation import CALIBRATION_VERSION, validation_profile
    from test7.solder_db import SOLDER_DB_FINGERPRINT, classify_family


CONTRACT_VERSION = "1.1"
POLICY_VERSION = "prediction-use-policy-v1"

STATE_ORDER = {
    "exact_match": 0,
    "in_domain": 1,
    "weak_support": 2,
    "out_of_domain": 3,
    "unavailable": 4,
    "data_quality_error": 5,
}

STATE_LABEL_KO = {
    "exact_match": "DB 등록값",
    "in_domain": "검증 범위 내 예측",
    "weak_support": "근거 부족 예측",
    "out_of_domain": "DB 범위 밖",
    "unavailable": "예측 불가",
    "data_quality_error": "데이터 품질 오류",
}

USAGE_LABEL_KO = {
    "reference": "참고 가능",
    "review": "공학 검토 필요",
    "provisional": "임시 추정만",
    "refused": "사용 중단",
}

PROCESS_USAGE_LABEL_KO = {
    "reference": "일반 참고값",
    "review": "공학 검토 필요",
    "provisional": "임시 추정만",
    "refused": "공정 추천 중단",
}

REASON_LABEL_KO = {
    "EXACT_DB_MATCH": "동일 조성이 DB에 등록되어 있습니다.",
    "WITHIN_VALIDATED_DISTANCE": "그룹 홀드아웃 검증 거리 안에 있습니다.",
    "FAMILY_SAMPLE_TOO_SMALL": "동일 합금족의 독립 검증 표본이 부족해 전체 DB 오차를 사용했습니다.",
    "BEYOND_FAMILY_Q90": "최근접 DB 거리가 검증 표본의 90백분위보다 큽니다.",
    "BEYOND_FAMILY_Q99": "최근접 DB 거리가 검증 표본의 99백분위보다 큽니다.",
    "UNSUPPORTED_ELEMENT_AXIS": "학습·검증이 충분하지 않은 원소 축이 포함되어 있습니다.",
    "NO_VALIDATION_DATA": "이 물성의 교차검증 자료가 없습니다.",
    "PROCESS_CONSTRAINTS_MISSING": "부품 허용온도·오븐 편차가 없어 생산 승인값이 아닌 일반 참고값입니다.",
    "PROCESS_RECOMMENDATION_REFUSED": "예측 근거가 약하거나 DB 범위 밖이라 리플로우 권장값을 내지 않습니다.",
    "PROCESS_LIMIT_EXCEEDED": "피크와 오븐 편차를 반영하면 부품 허용온도를 넘습니다.",
    "INVALID_MELTING_ORDER": "고상선·액상선·피크의 물리적 순서가 맞지 않습니다.",
}


def _finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _worst_state(states: Iterable[str]) -> str:
    vals = list(states)
    return max(vals, key=lambda x: STATE_ORDER.get(x, 99)) if vals else "unavailable"


def _usage(state: str) -> str:
    return {
        "exact_match": "reference",
        "in_domain": "review",
        "weak_support": "provisional",
        "out_of_domain": "refused",
        "unavailable": "refused",
        "data_quality_error": "refused",
    }.get(state, "refused")


def _state_for(
    distance: float | None,
    profile: Dict[str, Any],
    *,
    exact: bool,
    unsupported_elements: list[str],
) -> tuple[str, list[str]]:
    if exact:
        return "exact_match", ["EXACT_DB_MATCH"]
    if unsupported_elements:
        return "out_of_domain", ["UNSUPPORTED_ELEMENT_AXIS"]
    if distance is None or int(profile.get("sample_count") or 0) <= 0:
        return "unavailable", ["NO_VALIDATION_DATA"]
    q90 = _finite_float(profile.get("distance_q90"))
    q99 = _finite_float(profile.get("distance_q99"))
    if q90 is None or q99 is None:
        return "unavailable", ["NO_VALIDATION_DATA"]
    if bool(profile.get("family_fallback")):
        reasons = ["FAMILY_SAMPLE_TOO_SMALL"]
        if distance > q99:
            reasons.append("BEYOND_FAMILY_Q99")
            return "out_of_domain", reasons
        if distance > q90:
            reasons.append("BEYOND_FAMILY_Q90")
        return "weak_support", reasons
    if distance <= q90:
        return "in_domain", ["WITHIN_VALIDATED_DISTANCE"]
    if distance <= q99:
        return "weak_support", ["BEYOND_FAMILY_Q90"]
    return "out_of_domain", ["BEYOND_FAMILY_Q99"]


def _interval(
    point: float | None,
    profile: Dict[str, Any],
    *,
    exact: bool,
    lower_bound: float | None = None,
) -> Dict[str, Any] | None:
    if point is None:
        return None
    if exact:
        return {
            "lower": round(point, 3),
            "upper": round(point, 3),
            "level": 1.0,
            "kind": "registered_db_value",
        }
    radius = _finite_float(profile.get("p90_absolute_error"))
    if radius is None:
        return None
    lower = point - radius
    if lower_bound is not None:
        lower = max(float(lower_bound), lower)
    return {
        "lower": round(lower, 3),
        "upper": round(point + radius, 3),
        "level": 0.90,
        "kind": str(profile.get("interval_kind") or "empirical_absolute_residual"),
        "empirical_coverage": profile.get("empirical_coverage"),
        "sample_count": int(profile.get("sample_count") or 0),
        "cohort": str(profile.get("cohort") or "global"),
    }


def _property_result(
    key: str,
    point: Any,
    unit: str,
    family: str,
    distance: float | None,
    *,
    exact: bool,
    method: str,
    unsupported_elements: list[str],
    evidence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    point_f = _finite_float(point)
    profile = validation_profile(key, family)
    state, reasons = _state_for(
        distance,
        profile,
        exact=bool(exact and point_f is not None),
        unsupported_elements=unsupported_elements,
    )
    return {
        "point": round(point_f, 3) if point_f is not None else None,
        "unit": unit,
        "interval": _interval(
            point_f,
            profile,
            exact=state == "exact_match",
            lower_bound=0.0 if unit == "MPa" else None,
        ),
        "method": method,
        "state": state,
        "state_label_ko": STATE_LABEL_KO[state],
        "usage": _usage(state),
        "usage_label_ko": USAGE_LABEL_KO[_usage(state)],
        "reason_codes": reasons,
        "reason_labels_ko": [REASON_LABEL_KO[x] for x in reasons],
        "validation": profile,
        "evidence": {
            "nearest_distance": round(distance, 4) if distance is not None else None,
            **(evidence or {}),
        },
    }


def _canonical_analysis_context(
    result: Dict[str, Any], analysis_context: Dict[str, Any] | None
) -> Dict[str, Any]:
    context = dict(analysis_context or {})
    props = dict(result.get("props") or {})
    wetting_temp = _finite_float(context.get("wetting_temp_c"))
    if wetting_temp is None:
        wetting_temp = _finite_float(props.get("wetting_temp_c"))
    wetting_basis = str(
        context.get("wetting_temp_basis") or props.get("wetting_temp_basis") or "auto"
    ).strip().lower()
    return {
        "mode": "lab" if str(context.get("mode") or "eng").lower() == "lab" else "eng",
        "literature_mode": (
            "deep"
            if str(context.get("literature_mode") or "fast").lower() == "deep"
            else "fast"
        ),
        "wetting_temp_c": round(wetting_temp, 4) if wetting_temp is not None else None,
        "wetting_temp_basis": wetting_basis,
    }


def _analysis_id(norm: Dict[str, Any], analysis_context: Dict[str, Any]) -> str:
    payload = {
        "composition": sorted((str(k), round(float(v), 8)) for k, v in norm.items()),
        "analysis_context": analysis_context,
        "contract": CONTRACT_VERSION,
        "api": API_VERSION_SEMVER,
        "melting_model": MELTING_ENGINE_VERSION,
        "db": SOLDER_DB_FINGERPRINT,
        "calibration": CALIBRATION_VERSION,
        "policy": POLICY_VERSION,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "ana_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_prediction_contract(
    result: Dict[str, Any],
    process_constraints: Dict[str, Any] | None = None,
    analysis_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    norm = dict(result.get("norm") or {})
    family = str(classify_family(norm))
    evidence = dict(result.get("evidence") or {})
    melting_ev = dict(evidence.get("melting") or {})
    props_db_ev = dict(evidence.get("props_db") or {})
    unknown_ev = dict(evidence.get("unknown_elements") or {})
    unknown_names = [str(x) for x in (unknown_ev.get("names") or [])]
    melting_distance = _finite_float(melting_ev.get("best_dist"))
    tensile_distance = _finite_float(props_db_ev.get("best_dist"))
    props = dict(result.get("props") or {})
    canonical_context = _canonical_analysis_context(result, analysis_context)
    neighbors = list((result.get("alloy_inference") or {}).get("neighbors") or [])[:3]

    melting_exact = bool(melting_ev.get("forced_db")) or (
        melting_distance is not None and melting_distance <= DB_EXACT_MATCH_EPS
    )
    tensile_exact = tensile_distance is not None and tensile_distance <= DB_EXACT_MATCH_EPS

    property_results = {
        "solidus_c": _property_result(
            "solidus_c",
            result.get("solidus"),
            "°C",
            family,
            melting_distance,
            exact=melting_exact,
            method="registered_db" if melting_exact else "hybrid_phase_knn_calphad",
            unsupported_elements=unknown_names,
            evidence={"neighbors": neighbors},
        ),
        "liquidus_c": _property_result(
            "liquidus_c",
            result.get("liquidus"),
            "°C",
            family,
            melting_distance,
            exact=melting_exact,
            method="registered_db" if melting_exact else "hybrid_phase_knn_calphad",
            unsupported_elements=unknown_names,
            evidence={"neighbors": neighbors},
        ),
        "tensile_strength_mpa": _property_result(
            "tensile_strength_mpa",
            props.get("tensile_strength"),
            "MPa",
            family,
            tensile_distance,
            exact=tensile_exact,
            method=str(props.get("tensile_strength_basis") or "property_db_idw_model"),
            unsupported_elements=unknown_names,
            evidence={
                "support_n": props_db_ev.get("support_n"),
                "neighbors": list(
                    props_db_ev.get("tensile_top") or props_db_ev.get("top") or []
                )[:5],
            },
        ),
    }

    melting_state = _worst_state(
        [property_results["solidus_c"]["state"], property_results["liquidus_c"]["state"]]
    )
    constraints = dict(process_constraints or {})
    solidus_point = _finite_float(result.get("solidus"))
    liquidus_point = _finite_float(result.get("liquidus"))
    peak_point = _finite_float(result.get("peak"))
    valid_order = bool(
        solidus_point is not None
        and liquidus_point is not None
        and peak_point is not None
        and solidus_point <= liquidus_point < peak_point
    )
    if not valid_order:
        for key in ("solidus_c", "liquidus_c"):
            item = property_results[key]
            item["state"] = "data_quality_error"
            item["state_label_ko"] = STATE_LABEL_KO["data_quality_error"]
            item["usage"] = "refused"
            item["usage_label_ko"] = USAGE_LABEL_KO["refused"]
            item["reason_codes"] = [*item.get("reason_codes", []), "INVALID_MELTING_ORDER"]
            item["reason_labels_ko"] = [
                *item.get("reason_labels_ko", []),
                REASON_LABEL_KO["INVALID_MELTING_ORDER"],
            ]
        melting_state = "data_quality_error"
    overall_state = _worst_state(
        [str(item.get("state") or "unavailable") for item in property_results.values()]
    )
    process_allowed = melting_state in ("exact_match", "in_domain") and valid_order
    process_reasons: list[str] = []
    if not valid_order:
        process_reasons.append("INVALID_MELTING_ORDER")
    if melting_state not in ("exact_match", "in_domain"):
        process_reasons.append("PROCESS_RECOMMENDATION_REFUSED")
    if not constraints:
        process_reasons.append("PROCESS_CONSTRAINTS_MISSING")
    max_component = _finite_float(constraints.get("max_component_temp_c"))
    oven_tolerance = _finite_float(constraints.get("oven_tolerance_c")) or 0.0
    target_margin = _finite_float(constraints.get("target_peak_margin_c"))
    candidate_peak = peak_point
    if liquidus_point is not None and target_margin is not None:
        candidate_peak = max(candidate_peak or liquidus_point, liquidus_point + target_margin)
    safe_component_limit = (
        max_component - oven_tolerance if max_component is not None else None
    )
    if (
        process_allowed
        and safe_component_limit is not None
        and candidate_peak is not None
        and candidate_peak > safe_component_limit
    ):
        process_allowed = False
        process_reasons.append("PROCESS_LIMIT_EXCEEDED")
    if not process_allowed:
        process_usage = "refused"
    elif constraints:
        process_usage = "review"
    else:
        process_usage = "reference"

    return {
        "analysis_id": _analysis_id(norm, canonical_context),
        "contract_version": CONTRACT_VERSION,
        "versions": {
            "api": API_VERSION_SEMVER,
            "melting_model": MELTING_ENGINE_VERSION,
            "database": SOLDER_DB_FINGERPRINT,
            "calibration": CALIBRATION_VERSION,
            "policy": POLICY_VERSION,
        },
        "composition": norm,
        "analysis_context": canonical_context,
        "family": family,
        "overall_state": overall_state,
        "overall_state_label_ko": STATE_LABEL_KO[overall_state],
        "overall_usage": _usage(overall_state),
        "overall_usage_label_ko": USAGE_LABEL_KO[_usage(overall_state)],
        "melting_state": melting_state,
        "melting_state_label_ko": STATE_LABEL_KO[melting_state],
        "properties": property_results,
        "process_recommendation": {
            "allowed": process_allowed,
            "production_ready": False,
            "usage": process_usage,
            "usage_label_ko": PROCESS_USAGE_LABEL_KO[process_usage],
            "recommended_peak_c": (
                round(float(candidate_peak), 2)
                if process_allowed and candidate_peak is not None
                else None
            ),
            "reference_peak_c": peak_point,
            "safe_component_limit_c": (
                round(safe_component_limit, 2) if safe_component_limit is not None else None
            ),
            "constraints": constraints,
            "reason_codes": process_reasons,
            "reason_labels_ko": [REASON_LABEL_KO[x] for x in process_reasons],
        },
        "disclaimer_ko": (
            "예측 구간은 현재 DB의 그룹 홀드아웃 잔차로 계산한 경험적 90% 범위입니다. "
            "공인 시험·DSC·인장 시험과 사내 공정 승인을 대체하지 않습니다."
        ),
    }
