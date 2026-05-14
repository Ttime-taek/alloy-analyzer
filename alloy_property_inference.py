# -*- coding: utf-8 -*-
"""
조성-융점 데이터 추론: 상위 k개 DB 이웃 + 원소 함량 차이에 대한 선형 민감도(릿지)로
고상·액상 근사 및 리플로우·과냉각 주의 리포트 생성.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

try:
    from .utils import composition_distance
except ImportError:
    from test7.utils import composition_distance


def _neighbor_weights(distances: Sequence[float], *, power: float, eps: float) -> List[float]:
    raw = [1.0 / (float(d) + eps) ** float(power) for d in distances]
    s = sum(raw)
    if s <= 0:
        return [1.0 / len(raw)] * len(raw)
    return [float(x / s) for x in raw]


def _union_elems(comps: List[Dict[str, Any]]) -> List[str]:
    keys = set()
    for c in comps:
        if isinstance(c, dict):
            keys.update(c.keys())
    return sorted(keys, key=lambda e: (e != "Sn", e))


def _ridge_linear_map(
    X: "Any", y: "Any", lam: float
) -> Tuple["Any", float]:
    """X: (k, n), y: (k,) → coef (n,), intercept so that y ≈ X@coef + intercept (intercept = mean(y)-mean(X)@coef)."""
    import numpy as np

    k, n = X.shape
    xm = np.mean(X, axis=0)
    ym = float(np.mean(y))
    Xc = X - xm
    yc = y - ym
    # coef = (Xc.T Xc + lam I)^-1 Xc.T yc
    a = Xc.T @ Xc + lam * np.eye(n)
    b = Xc.T @ yc
    coef = np.linalg.solve(a, b)
    intercept = ym - float(xm @ coef)
    return coef, intercept


def predictAlloyProperties(
    norm: Dict[str, Any],
    db_prepared: Sequence[Dict[str, Any]],
    *,
    k: int = 3,
    power: float = 1.5,
    eps: float = 1e-6,
    ridge_lambda: float = 0.35,
) -> Dict[str, Any]:
    """
    상위 k 이웃(solder_db 스키마)으로부터 IDW 기준점 + 조성 차이에 대한 융점 선형 보정.

    Returns
    -------
    solidus, liquidus, recommended_peak_c, neighbors, neighbor_weights,
    element_weights_liquidus, element_weights_solidus, process_report, inference_note
    """
    if not norm or not isinstance(norm, dict):
        return _empty_inference("조성이 비어 있습니다.")
    if not db_prepared:
        return _empty_inference("DB가 비어 있습니다.")

    nfd = float(norm.get("Sn", 0) or 0) + float(norm.get("Ag", 0) or 0)
    if nfd <= 0:
        return _empty_inference("Sn 또는 Ag 기준 조성이 없습니다.")

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in db_prepared:
        try:
            comp = row.get("comp")
            if not isinstance(comp, dict):
                continue
            d = float(composition_distance(norm, comp))
            scored.append((d, row))
        except Exception:
            continue
    if not scored:
        return _empty_inference("유효한 DB 행이 없습니다.")
    scored.sort(key=lambda x: x[0])
    top = scored[: max(1, min(int(k), len(scored)))]
    dists = [t[0] for t in top]
    rows = [t[1] for t in top]
    w = _neighbor_weights(dists, power=power, eps=eps)

    comps = [r["comp"] for r in rows if isinstance(r.get("comp"), dict)]
    elems = _union_elems([dict(norm)] + comps)
    if not elems:
        return _empty_inference("원소 축을 구성할 수 없습니다.")

    def _vec(c: Dict[str, Any]) -> List[float]:
        return [float(c.get(e, 0.0) or 0.0) for e in elems]

    norm_v = _vec(norm)
    liq_idw = sum(w[i] * float(rows[i]["liquidus"]) for i in range(len(rows)))
    sol_idw = sum(w[i] * float(rows[i]["solidus"]) for i in range(len(rows)))
    comp_idw = [
        sum(w[i] * float(rows[i]["comp"].get(e, 0.0) or 0.0) for i in range(len(rows)))
        for e in elems
    ]

    neighbors_out: List[Dict[str, Any]] = []
    for i, r in enumerate(rows):
        neighbors_out.append(
            {
                "name": str(r.get("name", "")),
                "dist": round(float(dists[i]), 4),
                "weight": round(float(w[i]), 4),
                "solidus": float(r["solidus"]),
                "liquidus": float(r["liquidus"]),
            }
        )

    elem_w_liq: Dict[str, float] = {}
    elem_w_sol: Dict[str, float] = {}
    pred_liq = float(liq_idw)
    pred_sol = float(sol_idw)
    note = "IDW(거리 가중) 기준점 + 이웃 3점 선형 민감도(릿지) 보정."

    try:
        import numpy as np

        if len(rows) >= 2:
            X = np.array([_vec(r["comp"]) for r in rows], dtype=float)
            y_l = np.array([float(r["liquidus"]) for r in rows], dtype=float)
            y_s = np.array([float(r["solidus"]) for r in rows], dtype=float)
            try:
                coef_l, ice_l = _ridge_linear_map(X, y_l, ridge_lambda)
                coef_s, ice_s = _ridge_linear_map(X, y_s, ridge_lambda)
            except np.linalg.LinAlgError:
                coef_l = coef_s = ice_l = ice_s = None
            if coef_l is not None and coef_s is not None:
                nv = np.array(norm_v, dtype=float)
                cid = np.array(comp_idw, dtype=float)
                pred_liq = float(ice_l + float(coef_l @ (nv - cid)))
                pred_sol = float(ice_s + float(coef_s @ (nv - cid)))
                for j, e in enumerate(elems):
                    elem_w_liq[e] = round(float(coef_l[j]), 4)
                    elem_w_sol[e] = round(float(coef_s[j]), 4)
    except Exception:
        note = "NumPy 미사용 또는 선형 보정 실패 — IDW 가중 평균만 사용."

    if pred_liq < pred_sol:
        pred_liq = pred_sol + 1.0
    pred_sol = max(50.0, min(420.0, pred_sol))
    pred_liq = max(50.0, min(520.0, pred_liq))
    if pred_liq < pred_sol + 0.5:
        pred_liq = pred_sol + 1.0

    dtl = pred_liq - pred_sol
    peak_off = 25.0 if dtl >= 5.0 else 20.0
    peak_c = pred_liq + peak_off

    report = _build_process_report(pred_sol, pred_liq, peak_c, dtl)

    return {
        "solidus": round(pred_sol, 2),
        "liquidus": round(pred_liq, 2),
        "recommended_peak_c": round(peak_c, 1),
        "neighbors": neighbors_out,
        "neighbor_weights": [float(x) for x in w],
        "element_weights_liquidus": elem_w_liq,
        "element_weights_solidus": elem_w_sol,
        "process_report": report,
        "inference_note": note,
        "idw_baseline_solidus": round(sol_idw, 2),
        "idw_baseline_liquidus": round(liq_idw, 2),
    }


def _empty_inference(reason: str) -> Dict[str, Any]:
    return {
        "solidus": None,
        "liquidus": None,
        "recommended_peak_c": None,
        "neighbors": [],
        "neighbor_weights": [],
        "element_weights_liquidus": {},
        "element_weights_solidus": {},
        "process_report": reason,
        "inference_note": "추론 생략",
        "idw_baseline_solidus": None,
        "idw_baseline_liquidus": None,
    }


def _build_process_report(sol: float, liq: float, peak_c: float, dtl: float) -> str:
    lines = [
        "[데이터 추론 — 리플로우·냉각 주의]",
        f"· 추정 액상선 {liq:.1f}℃ 기준 권장 피크(참고): 약 {peak_c:.1f}℃ (액상선 대비 +{peak_c - liq:.0f}℃ 오프셋, IPC-J-STD-020E 권역과의 정합을 위해 GUI 리플로우 튜너로 최종 확정 권장).",
        f"· 고상–액상 간격(플라스틱 레인지) 약 {dtl:.1f}℃.",
    ]
    if dtl < 5.0:
        lines.append(
            "· 간격이 좁습니다: 과냉각(슬러러블 콜드 슬럼프)과 부분융이 섞이기 쉬우므로, 피크 직후 냉각 곡선을 급격히 내리지 말고 TAL·Time-above-liquidus를 DSC/시험판으로 확인하세요."
        )
    elif dtl > 35.0:
        lines.append(
            "· 간격이 큽니다: 고온에서 장시간 체류 시 IMC 성장·보드 변색 위험이 커질 수 있으니, 피크 체류와 냉각 전 구간 프로파일을 계열 표준과 대조하세요."
        )
    else:
        lines.append(
            "· 일반 SAC/저온계열에서 흔한 간격입니다: 냉각은 2–4℃/s 전후부터 세밀 조정하고, BGA/CSP는 보드 변형·위성볼에 유의하세요."
        )
    if liq < 200.0:
        lines.append("· 저융 조성에 가깝습니다: 피크–프리히트 마진이 좁으니 온도 오버슈트를 최소화하세요.")
    return "\n".join(lines)

