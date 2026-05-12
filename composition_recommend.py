# -*- coding: utf-8 -*-
"""
목표 고상/액상(허용 오차)에 맞는 조성 후보 탐색.

- 융점은 AlloyAnalyzer.calc_melting_with_detail 과 동일 경로.
- `list_db_compositions_matching_melt_target`: solder_db에서 목표 온도 밴드에
  들어가는 등록 조성 나열. AND/OR(고상·액상 모두 vs 하나만) 선택 가능.
  밴드 필터는 축별 `max(요청 허용오차, min_axis_band_tolerance_c)`(기본 50℃)로
  넓혀 근사 데이터가 빠지지 않게 한다. 정렬용 점수는 ``MeltTarget.rank_match_any_axis``에 따라
  L1 합 또는(고상·액상 동시 지정 시) 더 나은 축의 min 편차를 사용한다.
  API `/api/recommend_melt`는 OR 밴드로 DB 행을 가져와 격자 후보와 **한 목록**으로 합칩니다.
- 격자 후보에는 `db_close_names`(조성 최근접 + 예측 고상·액상 근접 DB명, 중점 구분)가 포함됩니다.
- `merge_db_registered_into_recommend_candidates`: `list_db_compositions_matching_melt_target`과
  동일한 DB 행 목록을 격자 결과와 합칩니다. 등록 DB 조성은 모델 예측보다 우선(고상·액상은
  DB 실측/문헌값 사용)하며, 동일 정규화 조성이면 격자 행을 제외합니다.
- **용도 구분(제품 의도)**: solder_db는 “목표 융점에 가까운 **기준(닻) 조성**”을 보여 주는 용도이고,
  격자(모델) 행은 그와 **동일 조성이 아닌** wt%를 바꾼 **미지 후보**를 스윕한 결과입니다.
  (예: 액상 200℃ 목표 → DB에 근접한 Sn–Ag–Cu–In–Bi 계열이 있으면 참고로 올리고, 실제 추천은
  고정·가변 축을 조절해 스윕한 조성을 우선 비교합니다.)
- 병합 표(`candidates`)에는 DB 등록 행 개수를 **상한**(`max_db_registered_in_merged`, API 기본 4 전후)으로
  두어, 밴드 일치 DB가 매우 많아도 **격자(미지 조성) 후보**가 표에서 사라지지 않게 한다.
- 병합 목록 정렬: penalty → plastic_range_c → match_score → (동점 시) 모델 격자 후보 우선.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# solder_db 온도 밴드 필터: 축별 허용을 이 값 이하로 좁히지 않음(기본 ±50℃).
MIN_DB_AXIS_BAND_TOLERANCE_C: float = 50.0


@dataclass
class MeltTarget:
    solidus_c: Optional[float] = None
    solidus_tolerance_c: float = 50.0
    liquidus_c: Optional[float] = None
    liquidus_tolerance_c: float = 50.0
    #: 고상·액상을 둘 다 지정했을 때 정렬 점수·penalty를 ``min(축별)``으로 할지(L1 합의 기본값과 대비).
    rank_match_any_axis: bool = False

    def validate(self) -> None:
        if self.solidus_c is None and self.liquidus_c is None:
            raise ValueError("target_solidus_c 또는 target_liquidus_c 중 하나 이상을 지정하세요.")
        for name, v in (
            ("solidus_tolerance_c", self.solidus_tolerance_c),
            ("liquidus_tolerance_c", self.liquidus_tolerance_c),
        ):
            if v is None or float(v) < 0:
                raise ValueError(f"{name}는 0 이상이어야 합니다.")


def _db_close_names_for_predicted_melt(
    db: Any,
    solidus: float,
    liquidus: float,
    comp_best_name: Optional[str],
    *,
    max_labels: int = 8,
    liq_focus_min_c: float = 185.0,
    max_liq_focus_extras: int = 5,
) -> str:
    """
    격자 후보 한 줄에 표시할 DB 참고명: 조성 최근접 + 예측 융점에 가까운 solder_db 행.

    - 항상 조성 최근접(comp_best_name)을 앞에 둔다.
    - 예측 액상이 liq_focus_min_c 이상이면 |Δ액상|이 작은 DB 행을 우선 추가(Sn-In-SAC 등 액상대 근접).
    - 그 외 고상+액상 L1 거리(|ΔTs|+|ΔTl|)가 작은 행을 채운다.
    """
    if not isinstance(db, list) or max_labels < 1:
        return (comp_best_name or "").strip()

    scored_l1: List[Tuple[float, str]] = []
    scored_liq: List[Tuple[float, str, bool, float]] = []
    for row in db:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name:
            continue
        try:
            ds = float(row.get("solidus", 0.0))
            dl = float(row.get("liquidus", 0.0))
        except (TypeError, ValueError):
            continue
        l1 = abs(float(solidus) - ds) + abs(float(liquidus) - dl)
        scored_l1.append((l1, str(name)))
        comp = row.get("comp")
        has_in = isinstance(comp, dict) and float(comp.get("In", 0.0) or 0.0) >= 0.4
        dliq = abs(float(liquidus) - dl)
        # In 없는 행은 액상대만 맞아도 덜 우선(저융점 Zn–Bi 등이 SAC-In 계열을 밀어내는 것 방지)
        liq_key = dliq + (0.0 if has_in else 10.0)
        scored_liq.append((liq_key, str(name), has_in, dliq))

    scored_l1.sort(key=lambda x: x[0])
    scored_liq.sort(key=lambda x: x[0])

    out: List[str] = []
    if comp_best_name:
        bn = str(comp_best_name).strip()
        if bn:
            out.append(bn)

    if float(liquidus) >= liq_focus_min_c:
        liq_added = 0
        for _liq_key, nm, _has_in, dliq in scored_liq:
            if nm in out:
                continue
            if dliq > 22.0:
                break
            out.append(nm)
            liq_added += 1
            if liq_added >= max_liq_focus_extras:
                break

    for l1, nm in scored_l1:
        if nm in out:
            continue
        out.append(nm)
        if len(out) >= max_labels:
            break

    return " · ".join(out) if out else (comp_best_name or "")


def _melt_penalty(solidus: float, liquidus: float, tgt: MeltTarget) -> float:
    if tgt.solidus_c is not None:
        d_s = abs(float(solidus) - float(tgt.solidus_c))
        pen_s = max(0.0, d_s - float(tgt.solidus_tolerance_c)) ** 2
    else:
        pen_s = 0.0
    if tgt.liquidus_c is not None:
        d_l = abs(float(liquidus) - float(tgt.liquidus_c))
        pen_l = max(0.0, d_l - float(tgt.liquidus_tolerance_c)) ** 2
    else:
        pen_l = 0.0
    if (
        getattr(tgt, "rank_match_any_axis", False)
        and tgt.solidus_c is not None
        and tgt.liquidus_c is not None
    ):
        return float(min(pen_s, pen_l))
    return float(pen_s + pen_l)


def _melt_target_l1_score(solidus: float, liquidus: float, tgt: MeltTarget) -> float:
    """
    목표 융점 대비 정렬용 점수(낮을수록 우선).

    - 기본: 지정 축의 ``|Δ고상|+|Δ액상|`` 합(L1).
    - ``rank_match_any_axis=True`` 이고 고상·액상이 **둘 다** 지정된 경우: ``min(|Δ고상|,|Δ액상|)``
      (한 축만 잘 맞아도 상위로 올라가게).
    """
    if (
        getattr(tgt, "rank_match_any_axis", False)
        and tgt.solidus_c is not None
        and tgt.liquidus_c is not None
    ):
        return float(
            min(
                abs(float(solidus) - float(tgt.solidus_c)),
                abs(float(liquidus) - float(tgt.liquidus_c)),
            )
        )
    score = 0.0
    if tgt.solidus_c is not None:
        score += abs(float(solidus) - float(tgt.solidus_c))
    if tgt.liquidus_c is not None:
        score += abs(float(liquidus) - float(tgt.liquidus_c))
    return float(score)


def _plastic_range_c(solidus: float, liquidus: float) -> float:
    """과냉각 구간(액상 - 고상), ℃. 동점 시 좁을수록 우선."""
    return max(0.0, float(liquidus) - float(solidus))


def _effective_band_target_for_db(
    target: MeltTarget,
    *,
    min_axis_band_tolerance_c: float,
) -> MeltTarget:
    """
    solder_db 포함 여부 판단용 목표: 지정된 각 축에 대해
    허용오차 = max(사용자 값, min_axis_band_tolerance_c).
    min_axis_band_tolerance_c=0 이면 사용자 값 그대로.
    """
    mn = max(0.0, float(min_axis_band_tolerance_c))
    s_tol = float(target.solidus_tolerance_c)
    l_tol = float(target.liquidus_tolerance_c)
    if target.solidus_c is not None:
        s_tol = max(s_tol, mn)
    if target.liquidus_c is not None:
        l_tol = max(l_tol, mn)
    return MeltTarget(
        solidus_c=target.solidus_c,
        solidus_tolerance_c=s_tol,
        liquidus_c=target.liquidus_c,
        liquidus_tolerance_c=l_tol,
    )


def _db_row_in_melt_band(
    solidus: float,
    liquidus: float,
    tgt: MeltTarget,
    *,
    match_any_specified_axis: bool,
) -> bool:
    """
    solder_db 행의 고정 solidus/liquidus가 목표 밴드에 들어가는지.

    - match_any_specified_axis=False: 지정된 축은 모두 허용 오차 안이어야 함(AND).
    - match_any_specified_axis=True: 지정된 축 중 하나라도 허용 오차 안이면 포함(OR).
    """
    checks: List[bool] = []
    if tgt.solidus_c is not None:
        d = abs(float(solidus) - float(tgt.solidus_c))
        checks.append(d <= float(tgt.solidus_tolerance_c))
    if tgt.liquidus_c is not None:
        d = abs(float(liquidus) - float(tgt.liquidus_c))
        checks.append(d <= float(tgt.liquidus_tolerance_c))
    if not checks:
        return False
    if match_any_specified_axis:
        return any(checks)
    return all(checks)


def list_db_compositions_matching_melt_target(
    analyzer: Any,
    target: MeltTarget,
    *,
    match_any_specified_axis: bool = False,
    max_rows: int = 300,
    min_axis_band_tolerance_c: float = MIN_DB_AXIS_BAND_TOLERANCE_C,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    `solder_db`에 등록된 조성 중 목표 고상/액상(±허용)에 해당하는 행을 모두 나열.

    격자 탐색(`recommend_compositions`)과 별개로, **DB에 저장된 실측·문헌 고상/액상 값** 기준이다.
    온도 밴드는 축별로 ``max(사용자 허용, min_axis_band_tolerance_c)``(기본 50℃)로 잡는다.
    행의 penalty(L1)는 사용자가 지정한 목표 온도 그대로 기준이다.
    """
    target.validate()
    band_tgt = _effective_band_target_for_db(
        target, min_axis_band_tolerance_c=min_axis_band_tolerance_c
    )
    max_rows = max(1, min(int(max_rows), 500))

    sync = getattr(analyzer, "_sync_db_prepared", None)
    if callable(sync):
        sync()

    db = getattr(analyzer, "db", None)
    if not isinstance(db, list):
        return [], {"error": "analyzer.db가 없습니다.", "count": 0}

    out: List[Dict[str, Any]] = []
    for row in db:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        comp = row.get("comp")
        if not isinstance(comp, dict):
            continue
        try:
            s = float(row.get("solidus", 0.0))
            l = float(row.get("liquidus", 0.0))
        except (TypeError, ValueError):
            continue
        if not _db_row_in_melt_band(
            s, l, band_tgt, match_any_specified_axis=match_any_specified_axis
        ):
            continue
        l1 = _melt_target_l1_score(s, l, target)
        pr = _plastic_range_c(s, l)
        out.append(
            {
                "name": str(name) if name is not None else "",
                "comp": dict(comp),
                "solidus": s,
                "liquidus": l,
                "penalty": float(l1),
                "plastic_range_c": float(pr),
                "source": "solder_db",
            }
        )

    out.sort(key=lambda r: (float(r["penalty"]), float(r["plastic_range_c"]), str(r["name"])))
    trimmed = out[:max_rows]
    meta = {
        "db_temperature_match_count": len(out),
        "db_temperature_match_returned": len(trimmed),
        "db_temperature_match_any_axis": bool(match_any_specified_axis),
        "db_temperature_match_cap": max_rows,
        "db_min_axis_band_tolerance_c": float(min_axis_band_tolerance_c),
        "db_band_effective_solidus_tolerance_c": (
            float(band_tgt.solidus_tolerance_c) if target.solidus_c is not None else None
        ),
        "db_band_effective_liquidus_tolerance_c": (
            float(band_tgt.liquidus_tolerance_c) if target.liquidus_c is not None else None
        ),
    }
    return trimmed, meta


def _norm_fingerprint(norm: Any, *, ndigits: int = 4) -> Tuple[Tuple[str, float], ...]:
    """정규화 조성 중복 판별용 키(원소별 wt% 반올림 후 정렬)."""
    if not isinstance(norm, dict) or not norm:
        return tuple()
    items: List[Tuple[str, float]] = []
    for el in sorted(norm.keys()):
        try:
            w = round(float(norm[el]), ndigits)
        except (TypeError, ValueError):
            continue
        if w > 0.0:
            items.append((str(el), float(w)))
    return tuple(items)


def db_alloy_row_to_melt_candidate_row(
    analyzer: Any,
    row: Dict[str, Any],
    target: MeltTarget,
    *,
    db_list: Any,
) -> Optional[Dict[str, Any]]:
    """
    solder_db 한 행을 격자 후보와 동일 형태의 dict로 변환.

    고상·액상·penalty·plastic_range는 **DB 등록값** 기준(목표 대비 L1).
    peak·melting_stage·melting_detail은 참고용으로 모델 경로를 한 번 호출해 채운다.
    """
    comp = row.get("comp")
    if not isinstance(comp, dict):
        return None
    raw: Dict[str, float] = {}
    try:
        for k, v in comp.items():
            ck = analyzer.canonical_element_symbol(str(k).strip())
            if ck in analyzer.KNOWN_PERIODIC_METALS:
                raw[ck] = float(raw.get(ck, 0.0)) + float(v)
        analyzer.validate_input_comp(raw)
    except Exception:
        return None
    try:
        db_s = float(row["solidus"])
        db_l = float(row["liquidus"])
    except (TypeError, ValueError, KeyError):
        return None

    norm = analyzer.normalize(raw)
    best, score, conf = analyzer.find_best_match(norm)
    pred_s, pred_l, peak, stage, detail = analyzer.calc_melting_with_detail(best, norm)
    l1 = _melt_target_l1_score(db_s, db_l, target)
    pr = _plastic_range_c(db_s, db_l)
    nm = str(row.get("name", "")).strip()
    comp_best_nm = (best or {}).get("name") if isinstance(best, dict) else None
    db_close = _db_close_names_for_predicted_melt(
        db_list,
        float(db_s),
        float(db_l),
        nm or (str(comp_best_nm) if comp_best_nm is not None else None),
    )
    md: Dict[str, Any] = dict(detail) if isinstance(detail, dict) else {}
    md["melt_temperatures_source"] = "solder_db_registered"
    md["registered_db_name"] = nm
    md["model_solidus_preview_c"] = float(pred_s)
    md["model_liquidus_preview_c"] = float(pred_l)

    return {
        "comp": raw,
        "norm": norm,
        "solidus": float(db_s),
        "liquidus": float(db_l),
        "peak": float(peak),
        "melting_stage": int(stage),
        "match_score": float(score),
        "match_confidence": float(conf),
        "best_name": comp_best_nm,
        "db_close_names": db_close,
        "penalty": float(l1),
        "plastic_range_c": float(pr),
        "melting_detail": md,
        "melt_row_source": "solder_db_registered",
        "registered_name": nm or None,
    }


def merge_db_registered_into_recommend_candidates(
    analyzer: Any,
    grid_rows: List[Dict[str, Any]],
    db_rows: List[Dict[str, Any]],
    target: MeltTarget,
    *,
    max_results: int,
    max_db_registered_in_merged: int = 0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    격자 탐색 결과와 `list_db_compositions_matching_melt_target`가 반환한 DB 행을 합친다.

    - DB 등록 행은 melt_row_source=`solder_db_registered`, 고상·액상은 DB 값.
    - 정규화 조성이 DB 행과 겹치면 격자 행은 제외(등록 데이터 우선).
    - **max_db_registered_in_merged** > 0 이면, 목표 적합도가 좋은 순으로 DB 후보만 그 개수까지
      표에 넣고 나머지 슬롯은 격자(탐색)로 채운다. solder_db 밴드가 넓을 때 DB만으로 표가
      가득 차는 것을 막는다. **0**이면 DB 행 개수 제한 없음(구 동작).
    - 최종 정렬: penalty → plastic_range_c → match_score → (동점 시) 모델 격자 후보 우선.
    """
    target.validate()
    db_list = getattr(analyzer, "db", None)

    db_candidates: List[Dict[str, Any]] = []
    seen_fp: set[Tuple[Tuple[str, float], ...]] = set()
    for row in db_rows:
        if not isinstance(row, dict):
            continue
        cand = db_alloy_row_to_melt_candidate_row(analyzer, row, target, db_list=db_list)
        if cand is None:
            continue
        fp = _norm_fingerprint(cand.get("norm"))
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        db_candidates.append(cand)

    db_sort_key = lambda r: (
        float(r["penalty"]),
        float(r["plastic_range_c"]),
        float(r["match_score"]),
        str(r.get("registered_name") or ""),
    )
    db_candidates.sort(key=db_sort_key)
    cap_db = int(max_db_registered_in_merged)
    if cap_db > 0:
        db_for_merge = db_candidates[:cap_db]
    else:
        db_for_merge = db_candidates

    grid_kept: List[Dict[str, Any]] = []
    for g in grid_rows:
        if not isinstance(g, dict):
            continue
        fp = _norm_fingerprint(g.get("norm"))
        if fp in seen_fp:
            continue
        gg = dict(g)
        gg.setdefault("melt_row_source", "predicted_grid")
        gg.setdefault("registered_name", None)
        grid_kept.append(gg)

    merged = list(db_for_merge) + grid_kept
    merged.sort(
        key=lambda r: (
            float(r["penalty"]),
            float(r["plastic_range_c"]),
            float(r["match_score"]),
            # 동일 적합도면 미지 조성(격자)을 앞에 — DB는 기준·참고 닻 역할
            1 if r.get("melt_row_source") == "solder_db_registered" else 0,
            str(r.get("registered_name") or r.get("best_name") or ""),
        )
    )
    cap = max(1, int(max_results))
    meta = {
        "melt_candidates_db_registered_total": len(db_candidates),
        "melt_candidates_db_registered_in_merged": len(db_for_merge),
        "melt_candidates_db_registered_cap": int(cap_db) if cap_db > 0 else None,
        "melt_candidates_grid_after_dedupe": len(grid_kept),
        "melt_candidates_merged_before_cap": len(merged),
        "melt_candidates_merge_sort": "penalty_then_plastic_then_match_then_grid_before_db_tiebreak",
    }
    return merged[:cap], meta


def _axis_values(min_v: float, max_v: float, step: float) -> List[float]:
    if step <= 0:
        raise ValueError("free 축의 step은 0보다 커야 합니다.")
    if max_v < min_v - 1e-12:
        raise ValueError("free 축에서 max는 min 이상이어야 합니다.")
    out: List[float] = []
    v = float(min_v)
    n = 0
    while v <= max_v + 1e-9:
        out.append(round(v, 8))
        v += float(step)
        n += 1
        if n > 200_000:
            raise ValueError("한 축의 스텝 수가 너무 많습니다. 범위를 줄이거나 step을 키우세요.")
    if not out:
        raise ValueError("free 축에서 유효한 값이 없습니다.")
    return out


def estimate_grid_points(free_axes: Sequence[Dict[str, Any]]) -> int:
    n = 1
    for ax in free_axes:
        vals = _axis_values(float(ax["min"]), float(ax["max"]), float(ax["step"]))
        n *= len(vals)
    return n


def recommend_compositions(
    analyzer: Any,
    *,
    fixed_comp: Dict[str, float],
    free_axes: Sequence[Dict[str, Any]],
    balance_element: str,
    target: MeltTarget,
    max_results: int = 15,
    max_grid_points: int = 15_000,
    balance_min: float = 0.02,
    balance_max: float = 98.0,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    unbounded_sorted_return: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    unbounded_sorted_return=True이면 정렬 후 슬라이스하지 않고 전체 격자 후보를 반환한다.
    (API에서 DB 등록 행과 병합한 뒤 max_results로 자를 때 사용.)
    """
    target.validate()

    canon_balance = analyzer.canonical_element_symbol(str(balance_element).strip())
    if canon_balance not in analyzer.KNOWN_PERIODIC_METALS:
        raise ValueError(f"지원하지 않는 balance 원소: {balance_element}")

    # solder_db 변경 시 융점·KNN이 갱신되도록 격자 루프 전에 한 번만 동기화
    sync = getattr(analyzer, "_sync_db_prepared", None)
    if callable(sync):
        sync()

    fixed_clean: Dict[str, float] = {}
    for k, val in (fixed_comp or {}).items():
        ck = analyzer.canonical_element_symbol(str(k).strip())
        if ck not in analyzer.KNOWN_PERIODIC_METALS:
            raise ValueError(f"지원하지 않는 원소: {k}")
        fixed_clean[ck] = float(fixed_clean.get(ck, 0.0)) + float(val)

    if canon_balance in fixed_clean:
        raise ValueError(f"balance_element({canon_balance})는 fixed_comp에 넣을 수 없습니다.")

    if not free_axes:
        raise ValueError("free_axes에 최소 1개 축이 필요합니다.")

    seen_el: set[str] = set()
    axis_element_keys: List[str] = []
    axis_value_lists: List[List[float]] = []

    for ax in free_axes:
        el_raw = str(ax.get("element", "")).strip()
        if not el_raw:
            raise ValueError("free 축에 element가 필요합니다.")
        el = analyzer.canonical_element_symbol(el_raw)
        if el not in analyzer.KNOWN_PERIODIC_METALS:
            raise ValueError(f"지원하지 않는 원소: {el_raw}")
        if el == canon_balance:
            raise ValueError(f"free 축에 balance_element({canon_balance})를 넣을 수 없습니다.")
        if el in fixed_clean:
            raise ValueError(f"{el}은(는) fixed_comp와 free 축에 동시에 올 수 없습니다.")
        if el in seen_el:
            raise ValueError(f"free 축에 {el}이(가) 중복되었습니다.")
        seen_el.add(el)
        axis_element_keys.append(el)
        axis_value_lists.append(
            _axis_values(float(ax["min"]), float(ax["max"]), float(ax["step"]))
        )

    grid_n = 1
    for lst in axis_value_lists:
        grid_n *= len(lst)
    if grid_n > max_grid_points:
        raise ValueError(
            f"격자 크기 {grid_n}가 허용 상한 {max_grid_points}을(를) 초과합니다. "
            "범위를 줄이거나 step을 키우거나 max_grid_points를 올리세요."
        )

    fixed_sum = float(sum(fixed_clean.values()))
    candidates: List[Dict[str, Any]] = []
    evaluated = 0

    db_list = getattr(analyzer, "db", None)

    for combo in itertools.product(*axis_value_lists):
        free_part = {axis_element_keys[i]: float(combo[i]) for i in range(len(combo))}
        free_sum = float(sum(free_part.values()))
        bal = 100.0 - fixed_sum - free_sum
        if bal < balance_min or bal > balance_max:
            evaluated += 1
            continue

        raw: Dict[str, float] = {}
        for k, v in fixed_clean.items():
            raw[k] = float(v)
        for k, v in free_part.items():
            raw[k] = float(v)
        raw[canon_balance] = float(raw.get(canon_balance, 0.0)) + bal

        try:
            analyzer.validate_input_comp(raw)
        except ValueError:
            evaluated += 1
            continue

        norm = analyzer.normalize(raw)
        best, score, conf = analyzer.find_best_match(norm)

        solidus, liquidus, peak, stage, detail = analyzer.calc_melting_with_detail(best, norm)
        l1 = _melt_target_l1_score(solidus, liquidus, target)
        pr = _plastic_range_c(solidus, liquidus)
        comp_best_nm = (best or {}).get("name")
        db_close = _db_close_names_for_predicted_melt(
            db_list,
            float(solidus),
            float(liquidus),
            str(comp_best_nm) if comp_best_nm is not None else None,
        )

        candidates.append(
            {
                "comp": raw,
                "norm": norm,
                "solidus": float(solidus),
                "liquidus": float(liquidus),
                "peak": float(peak),
                "melting_stage": int(stage),
                "match_score": float(score),
                "match_confidence": float(conf),
                "best_name": comp_best_nm,
                "db_close_names": db_close,
                "penalty": float(l1),
                "plastic_range_c": float(pr),
                "melting_detail": detail if isinstance(detail, dict) else {},
                "melt_row_source": "predicted_grid",
                "registered_name": None,
            }
        )
        evaluated += 1
        if progress_cb and evaluated % 500 == 0:
            try:
                progress_cb(evaluated, grid_n)
            except Exception:
                pass

    candidates.sort(
        key=lambda r: (
            float(r["penalty"]),
            float(r["plastic_range_c"]),
            float(r["match_score"]),
        )
    )
    cap = max(1, int(max_results))
    if unbounded_sorted_return:
        top = candidates
    else:
        top = candidates[:cap]

    meta = {
        "grid_points_evaluated": evaluated,
        "grid_points_planned": grid_n,
        "balance_element": canon_balance,
        "melt_sort": "l1_abs_error_then_plastic_range_then_match_score",
        "melt_grid_candidates_sorted_count": len(candidates),
        "melt_grid_candidates_returned_count": len(top),
        "disclaimer": (
            "탐색 결과는 내부 모델·DB에 따른 후보이며 유일한 정답 조성이 아닙니다. "
            "공인 분석·TDS·실측으로 반드시 검증하세요."
        ),
    }
    return top, meta
