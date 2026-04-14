"""
1D PCHIP (Piecewise Cubic Hermite Interpolating Polynomial) — 단조 구간에서 급격한 기울기 점프를 완화.
scipy 가 있으면 scipy.interpolate.PchipInterpolator 사용, 없으면 선형 보간으로 폴백.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

try:
    import numpy as np
    from scipy.interpolate import PchipInterpolator

    _HAS_PCHIP = True
except ImportError:
    np = None  # type: ignore
    PchipInterpolator = None  # type: ignore
    _HAS_PCHIP = False


def _linear_1d(x: float, xp: Sequence[float], fp: Sequence[float]) -> float:
    if not xp or len(xp) != len(fp):
        return float("nan")
    if x <= xp[0]:
        return float(fp[0])
    if x >= xp[-1]:
        return float(fp[-1])
    for i in range(len(xp) - 1):
        x0, x1 = xp[i], xp[i + 1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return float(fp[i] + t * (fp[i + 1] - fp[i]))
    return float(fp[-1])


def interp_pchip_1d(x: float, xp: Sequence[float], fp: Sequence[float]) -> float:
    """
    스칼라 x에 대한 PCHIP 보간값. xp는 비감소(일반적으로 엄격 증가)여야 함.
    """
    if not xp or len(xp) != len(fp):
        return float("nan")
    xs = [float(v) for v in xp]
    ys = [float(v) for v in fp]
    if len(xs) == 1:
        return ys[0]

    xc = min(max(float(x), xs[0]), xs[-1])

    if not _HAS_PCHIP:
        return _linear_1d(xc, xs, ys)

    # 중복 x 제거 (마지막 y 유지)
    ux: List[float] = []
    uy: List[float] = []
    for xv, yv in zip(xs, ys):
        if ux and abs(xv - ux[-1]) < 1e-15:
            ux[-1] = xv
            uy[-1] = yv
        else:
            ux.append(xv)
            uy.append(yv)

    if len(ux) < 2:
        return uy[0]
    xc = min(max(float(x), ux[0]), ux[-1])

    arr_x = np.asarray(ux, dtype=float)
    arr_y = np.asarray(uy, dtype=float)
    if np.any(np.diff(arr_x) <= 0):
        return _linear_1d(xc, ux, uy)

    poly = PchipInterpolator(arr_x, arr_y, extrapolate=True)
    return float(poly(xc))


def interp_pchip_table_solidus_liquidus(x: float, table: Sequence[Tuple[float, float, float]]) -> Tuple[float, float]:
    """
    table: (x_knot, solidus, liquidus) 행들. x_knot 오름차순.
    solidus / liquidus 각각 PCHIP.
    """
    if not table:
        return float("nan"), float("nan")
    xs = [float(row[0]) for row in table]
    ss = [float(row[1]) for row in table]
    ls = [float(row[2]) for row in table]
    return interp_pchip_1d(x, xs, ss), interp_pchip_1d(x, xs, ls)
