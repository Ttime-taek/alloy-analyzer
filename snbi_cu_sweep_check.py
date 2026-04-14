"""
Sn-Bi 고Bi 구간 Cu sweep 검증 스크립트.

요구:
- Bi>=20% (예: Bi=25, Ag=1 고정)에서 Cu 0.50~0.80를 0.01 간격으로 바꿔도
  solidus가 138℃ 부근에서 점프 없이 평탄하게 유지되는지 확인.

사용:
  python -m test7.snbi_cu_sweep_check
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def _comp_sn_ag_bi_cu(ag: float, bi: float, cu: float) -> Dict[str, float]:
    sn = 100.0 - float(ag) - float(bi) - float(cu)
    return {"Sn": sn, "Ag": float(ag), "Bi": float(bi), "Cu": float(cu)}


def run() -> Tuple[List[Tuple[float, float]], Dict[str, float]]:
    from .analyzer import AlloyAnalyzer
    from .solder_db import SOLDER_DB

    class _DummyAI:
        available = False
        status_detail = "dummy"

        def get_full_analysis(self, *args, **kwargs):
            return {"summary": "[dummy]", "phase": "", "imc": [], "roles": "", "dopant": "", "sources": []}

    analyzer = AlloyAnalyzer(SOLDER_DB, ai_engine=_DummyAI())

    ag = 1.0
    bi = 25.0
    out: List[Tuple[float, float]] = []

    prev = None
    max_jump = 0.0
    max_jump_at = None

    cu = 0.50
    while cu <= 0.800001:
        comp = _comp_sn_ag_bi_cu(ag=ag, bi=bi, cu=round(cu, 2))
        r = analyzer.analyze_all(comp, mode="eng")
        s = float(r.get("solidus", 0.0) or 0.0)
        out.append((round(cu, 2), s))
        if prev is not None:
            j = abs(s - prev)
            if j > max_jump:
                max_jump = j
                max_jump_at = (round(cu - 0.01, 2), round(cu, 2))
        prev = s
        cu += 0.01

    solidus_vals = [s for _, s in out]
    stats = {
        "min": min(solidus_vals) if solidus_vals else float("nan"),
        "max": max(solidus_vals) if solidus_vals else float("nan"),
        "max_jump": float(max_jump),
        "max_jump_at_cu": max_jump_at[1] if max_jump_at else None,
        "ag": ag,
        "bi": bi,
    }
    return out, stats


if __name__ == "__main__":
    pairs, stats = run()
    print(f"[Sn-Ag-Bi-Cu sweep] Ag={stats['ag']} Bi={stats['bi']}")
    print(f"solidus_min={stats['min']:.2f}C solidus_max={stats['max']:.2f}C max_jump={stats['max_jump']:.2f}C")
    for cu, s in pairs:
        print(f"Cu={cu:.2f}%  solidus={s:.2f}C")
