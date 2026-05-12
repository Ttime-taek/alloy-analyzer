# -*- coding: utf-8 -*-
"""
하이브리드 융점 앙상블(L2/L3/L4·외부 CALPHAD) 계열별 가중 튜닝.

- 기본값은 코드와 동일한 상수.
- 선택: JSON 설정 파일 또는 환경변수 MELTING_ENSEMBLE_CONFIG 로 경로 지정.
- 파일 형식 예: melting_ensemble_config.example.json

외부 CALPHAD 게이트는 melting_predictor 의 MELTING_CALPHAD_URL 과 함께 사용.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

_DEFAULT: Dict[str, Any] = {
    # L2: l2_w = l2_conf * (l2_simple_mult if is_simple else l2_other_mult)
    "l2_simple_mult": 3.0,
    "l2_other_mult": 1.8,
    # L3: l3_w = l3_conf * (l3_knn_with_l2_simple if is_simple and l2 else l3_knn_default)
    "l3_knn_with_l2_simple": 0.08,
    "l3_knn_default": 1.2,
    # L4: _calphad_approx 가중 (기존 분기 그대로, 마지막에 l4_conf 곱하기 전 스케일)
    "l4_if_l2_weak_mult": 0.3,
    "l4_if_no_l2_mult": 0.9,
    # 외부 CALPHAD HTTP 응답이 있을 때 추가 레이어 가중 (0 이면 URL만 있어도 비활성)
    "l4_external_weight": 0.5,
}

_CACHE: Dict[str, Any] | None = None


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)  # type: ignore[arg-type]
        else:
            out[k] = v
    return out


def _load_raw_config() -> Dict[str, Any]:
    path = (os.getenv("MELTING_ENSEMBLE_CONFIG") or "").strip()
    if not path:
        here = Path(__file__).resolve().parent
        cand = here / "melting_ensemble_config.json"
        path = str(cand) if cand.is_file() else ""
    if not path or not os.path.isfile(path):
        return {"default": {}, "families": {}}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return {"default": {}, "families": {}}
    return {
        "default": raw.get("default") if isinstance(raw.get("default"), dict) else {},
        "families": raw.get("families") if isinstance(raw.get("families"), dict) else {},
    }


def load_ensemble_store() -> Dict[str, Any]:
    """내부용: default + families 병합 결과 캐시."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    base = dict(_DEFAULT)
    raw = _load_raw_config()
    if isinstance(raw.get("default"), dict):
        base = _deep_merge(base, raw["default"])
    fams: Dict[str, Dict[str, Any]] = {}
    for fam, d in (raw.get("families") or {}).items():
        if isinstance(d, dict) and isinstance(fam, str):
            fams[fam] = _deep_merge(base, d)
    _CACHE = {"default": base, "families": fams}
    return _CACHE


def get_ensemble_profile(family: str) -> Dict[str, Any]:
    store = load_ensemble_store()
    fam = (family or "other").strip() or "other"
    if fam in store["families"]:
        return dict(store["families"][fam])
    return dict(store["default"])


def clear_ensemble_cache() -> None:
    """테스트에서 설정 리로드용."""
    global _CACHE
    _CACHE = None
