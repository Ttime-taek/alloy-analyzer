# melting_predictor.py  (v2.0 — Hybrid Melting Point Prediction Engine)
#
# 예측 레이어 (우선순위 순):
#   L1. DB 직접 일치      — dist < 0.3 → 실측값 최우선
#   L2. 이진/삼원 상태도  — 문헌 기반 공정점·liquidus 곡선 정밀 보간
#   L3. KNN 가중 보간     — 인근 DB 합금들의 가중평균 (liquidus 보조)
#   L4. CALPHAD 근사      — L2 없을 때만 활성화
#   L6. AI 델타 보정      — 미지 조성에만 소량 반영
#
# 핵심 규칙:
#   · SAC 삼원계 → solidus 반드시 217°C (공정점 고정)
#   · 이원계 지배 → L2만 사용, CALPHAD 비활성
#   · L2 신뢰도 높을수록 L4 비중 0에 수렴

import math

try:
    from .sn_pb_library import SN_PB_PHASE
except ImportError:
    from test7.sn_pb_library import SN_PB_PHASE

# ─────────────────────────────────────────────────────────────────────────────
# 이원계 상태도 데이터
# 출처: ASM Handbook Vol.3, NIST, IPC J-STD-006, JIS(납·플럭스·페이스트 시험 계열), 학술 문헌
# Sn-Pb 표는 sn_pb_library.py (SN_PB_PHASE)에서만 편집
# ─────────────────────────────────────────────────────────────────────────────

# Sn-Bi  공정점: Sn42Bi58 = 139°C  (ASM)
SN_BI_PHASE = [
    (0.0,   231.0, 231.0),
    (5.0,   205.0, 222.0),
    (10.0,  186.0, 215.0),
    (20.0,  160.0, 199.0),
    (30.0,  139.0, 187.0),
    (40.0,  139.0, 170.0),
    (50.0,  139.0, 155.0),
    (57.0,  139.0, 141.0),
    (58.0,  139.0, 139.0),
    (60.0,  139.0, 140.5),
    (70.0,  139.0, 152.0),
    (80.0,  167.0, 187.0),
    (90.0,  219.0, 229.0),
    (100.0, 271.0, 271.0),
]

# Sn-In  공정점: Sn48In52 = 117°C  (ASM)
SN_IN_PHASE = [
    (0.0,  231.0, 231.0),
    (10.0, 210.0, 220.0),
    (20.0, 185.0, 209.0),
    (30.0, 158.0, 195.0),
    (40.0, 120.0, 175.0),
    (48.0, 117.0, 143.0),
    (52.0, 117.0, 117.0),
    (60.0, 118.0, 125.0),
    (70.0, 130.0, 145.0),
    (100.0,156.0, 156.0),
]

# Sn-Ag  공정점: Sn96.5Ag3.5 = 221°C  (ASM)
SN_AG_PHASE = [
    (0.0,  231.0, 231.0),
    (1.0,  217.0, 227.0),
    (2.0,  217.0, 224.0),
    (3.0,  217.0, 222.0),
    (3.5,  221.0, 221.0),
    (4.0,  221.0, 226.0),
    (5.0,  221.0, 245.0),
    (10.0, 221.0, 332.0),
]

# Sn-Cu  공정점: Sn99.3Cu0.7 = 227°C  (ASM)
SN_CU_PHASE = [
    (0.0,  231.0, 231.0),
    (0.5,  227.0, 285.0),
    (0.7,  227.0, 227.0),
    (1.0,  227.0, 259.0),
    (2.0,  228.0, 340.0),
    (3.0,  228.0, 394.0),
]

# Sn-Sb  (ASM)
SN_SB_PHASE = [
    (0.0,  231.0, 231.0),
    (5.0,  235.0, 240.0),
    (10.0, 245.0, 251.0),
    (20.0, 261.0, 270.0),
    (30.0, 275.0, 310.0),
]

# Sn-Zn  공정점: Sn91Zn9 = 198°C  (ASM)
SN_ZN_PHASE = [
    (0.0,  231.0, 231.0),
    (5.0,  198.0, 215.0),
    (9.0,  198.0, 198.0),
    (15.0, 198.0, 233.0),
    (20.0, 200.0, 275.0),
]

# SAC 삼원계 공정점 (Sn-Ag-Cu ternary eutectic)
# Ag 3.5~3.9% + Cu 0.5~0.9% → 217°C (Ohnuma et al., 2000)
SAC_TERNARY_EUTECTIC = {
    "solidus": 217.0,
    "liquidus_base": 221.0,   # SAC305 기준
}

# 원소별 순수 융점(°C)
ELEMENT_MP = {
    "Sn": 231.9, "Bi": 271.4, "Pb": 327.5, "In": 156.6,
    "Ag": 961.8, "Cu": 1084.6, "Sb": 630.6, "Zn": 419.5,
    "Ni": 1455.0, "Ge": 938.3, "Au": 1064.2, "Ga": 29.8,
    "Al": 660.3,  "Pd": 1554.9,
}


# ─────────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────────
def _interp(x, table):
    """구간 선형 보간"""
    if x <= table[0][0]:
        return table[0][1], table[0][2]
    if x >= table[-1][0]:
        return table[-1][1], table[-1][2]
    for i in range(len(table) - 1):
        x0, s0, l0 = table[i]
        x1, s1, l1 = table[i + 1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return s0 + t * (s1 - s0), l0 + t * (l1 - l0)
    return table[-1][1], table[-1][2]


def _classify(norm):
    """합금 계열 분류"""
    sn  = norm.get("Sn", 0)
    bi  = norm.get("Bi", 0)
    inp = norm.get("In", 0)
    pb  = norm.get("Pb", 0)
    ag  = norm.get("Ag", 0)
    cu  = norm.get("Cu", 0)
    sb  = norm.get("Sb", 0)
    zn  = norm.get("Zn", 0)

    non_sn_maj = max(bi, inp, pb, zn)   # 주요 저융점 원소

    if pb > 5:
        return "SnPb"
    if bi > 5 and inp == 0 and pb == 0:
        return "SnBi"
    if inp > 5 and bi == 0 and pb == 0:
        return "SnIn"
    if zn > 3 and bi == 0:
        return "SnZn"
    if sn > 80 and ag > 0 and cu > 0 and bi < 3 and inp == 0:
        return "SAC"
    if sn > 80 and ag > 0 and cu == 0:
        return "SnAg"
    if sn > 80 and cu > 0 and ag == 0:
        return "SnCu"
    if sb > 3:
        return "SnSb"
    return "other"


# ─────────────────────────────────────────────────────────────────────────────
# L2: 상태도 기반 예측 (계열별 특화)
# ─────────────────────────────────────────────────────────────────────────────
def _phase_diagram_predict(norm, family):
    sn  = norm.get("Sn", 0)
    bi  = norm.get("Bi", 0)
    inp = norm.get("In", 0)
    pb  = norm.get("Pb", 0)
    ag  = norm.get("Ag", 0)
    cu  = norm.get("Cu", 0)
    sb  = norm.get("Sb", 0)
    zn  = norm.get("Zn", 0)

    # ── Sn-Bi 계 ─────────────────────────────────────────────────────────────
    if family == "SnBi":
        # 유효 Bi 비율: Bi/(Sn+Bi) 기준
        denom  = sn + bi
        eff_bi = (bi / denom * 100) if denom > 0 else bi
        sol, liq = _interp(eff_bi, SN_BI_PHASE)

        # Ag 존재 시 삼원계 공정점(139°C) 인력 보정
        # Sn-Ag-Bi 삼원계: Bi >= 10%, Ag >= 1% → solidus 139°C로 수렴 (문헌)
        if ag >= 1.0 and bi >= 10.0:
            pull  = min(1.0, (ag / 3.0) * (bi / 20.0))  # Ag·Bi 함량에 비례
            sol   = sol * (1.0 - pull * 0.9) + 139.0 * (pull * 0.9)
        elif ag > 0:
            # 소량 Ag: liquidus 소폭 상승만
            liq_adj = min(ag * 12.5, 20.0)
            liq    += liq_adj
            sol     = max(sol, 139.0)

        if cu > 0:
            liq += cu * 3.5
        if sb > 0:
            liq += sb * 2.0
        # 공정점 하한 클램프
        sol = max(sol, 139.0)
        return sol, liq, 0.92

    # ── Sn-In 계 ─────────────────────────────────────────────────────────────
    if family == "SnIn":
        denom  = sn + inp
        eff_in = (inp / denom * 100) if denom > 0 else inp
        sol, liq = _interp(eff_in, SN_IN_PHASE)
        if ag > 0:
            liq += ag * 5.0
        if bi > 0:
            sol  = max(sol - bi * 1.5, 117.0)
            liq  = max(liq - bi * 0.8, sol)
        return sol, liq, 0.90

    # ── Sn-Pb 계 ─────────────────────────────────────────────────────────────
    if family == "SnPb":
        denom  = sn + pb
        eff_pb = (pb / denom * 100) if denom > 0 else pb
        sol, liq = _interp(eff_pb, SN_PB_PHASE)
        return sol, liq, 0.92

    # ── Sn-Zn 계 ─────────────────────────────────────────────────────────────
    if family == "SnZn":
        sol, liq = _interp(zn, SN_ZN_PHASE)
        if bi > 0:
            liq -= bi * 2.0
        return sol, liq, 0.85

    # ── SAC 삼원계 ────────────────────────────────────────────────────────────
    if family == "SAC":
        # Solidus: SAC 공정점 217°C (Sn-Ag-Cu ternary eutectic)
        # 다만 Cu >> 0.7% 이면 solidus 소폭 상승
        if cu <= 1.0:
            sol = SAC_TERNARY_EUTECTIC["solidus"]   # 217.0
        else:
            sol = 217.0 + (cu - 1.0) * 3.0

        # Liquidus: Sn-Ag 상태도 기반 + Cu 보정
        _, liq_ag = _interp(ag, SN_AG_PHASE)
        liq = liq_ag
        if cu > 0.7:
            liq += (cu - 0.7) * 9.0

        # Bi 소량 첨가 효과
        if bi > 0:
            sol -= bi * 1.8
            liq -= bi * 0.9
            sol  = max(sol, 200.0)

        # In 소량 첨가 효과
        if inp > 0:
            sol -= inp * 2.5
            liq -= inp * 1.5
            sol  = max(sol, 190.0)

        # Sb 첨가 효과
        if sb > 0:
            liq += sb * 2.5

        return sol, liq, 0.90

    # ── Sn-Ag 이원계 ─────────────────────────────────────────────────────────
    if family == "SnAg":
        sol, liq = _interp(ag, SN_AG_PHASE)
        if sb > 0:
            liq += sb * 2.0
        return sol, liq, 0.85

    # ── Sn-Cu 이원계 ─────────────────────────────────────────────────────────
    if family == "SnCu":
        sol, liq = _interp(cu, SN_CU_PHASE)
        if sb > 0:
            liq += sb * 1.5
        return sol, liq, 0.85

    # ── Sn-Sb 계 ─────────────────────────────────────────────────────────────
    if family == "SnSb":
        sol, liq = _interp(sb, SN_SB_PHASE)
        return sol, liq, 0.82

    return None


# ─────────────────────────────────────────────────────────────────────────────
# L4: CALPHAD 근사 (L2 없을 때만)
# ─────────────────────────────────────────────────────────────────────────────
def _calphad_approx(norm, family):
    """
    기본 Vegard's Law + 공정점 인력 보정.
    SAC/이원계 계열에서는 L2가 있으므로 보조용으로만 사용.
    """
    # 순수 Sn 기준 융점에서 각 원소 기여 합산
    sn_frac = norm.get("Sn", 0) / 100.0

    # 1) 가중 평균 융점
    base_mp = 0.0
    total_frac = 0.0
    for elem, pct in norm.items():
        frac = pct / 100.0
        mp   = ELEMENT_MP.get(elem, 600.0)
        base_mp    += mp * frac
        total_frac += frac

    # 2) 공정점 인력 보정
    bi  = norm.get("Bi", 0) / 100.0
    inp = norm.get("In", 0) / 100.0
    pb  = norm.get("Pb", 0) / 100.0
    ag  = norm.get("Ag", 0) / 100.0
    cu  = norm.get("Cu", 0) / 100.0

    eutectic_correction = 0.0

    # Sn-Bi 공정점 인력 (공정점 Bi=0.58)
    if bi > 0:
        dist = abs(bi - 0.58)
        pull = math.exp(-dist * 6.0)
        eutectic_correction += (139.0 - base_mp) * pull * 0.85

    # Sn-In 공정점 인력 (공정점 In=0.52)
    if inp > 0:
        dist = abs(inp - 0.52)
        pull = math.exp(-dist * 6.0)
        eutectic_correction += (117.0 - base_mp) * pull * 0.85

    # Sn-Pb 공정점 인력 (공정점 Pb=0.37)
    if pb > 0:
        dist = abs(pb - 0.37)
        pull = math.exp(-dist * 6.0)
        eutectic_correction += (183.0 - base_mp) * pull * 0.80

    # SAC 공정점 인력
    if family == "SAC":
        eutectic_correction += (217.0 - base_mp) * 0.60

    sol_calphad = base_mp + eutectic_correction

    # 3) Liquidus 추정
    delta_t = 2.0
    if bi > 0:   delta_t += bi  * 100.0 * max(0.0, 1.0 - bi  / 0.58)
    if inp > 0:  delta_t += inp * 90.0  * max(0.0, 1.0 - inp / 0.52)
    if pb > 0:   delta_t += pb  * 50.0  * max(0.0, 1.0 - pb  / 0.37)
    if cu > 0.007: delta_t += (cu - 0.007) * 350.0
    if ag > 0.035: delta_t += (ag - 0.035) * 60.0

    liq_calphad = sol_calphad + max(0.0, delta_t)

    return sol_calphad, liq_calphad, 0.55


# ─────────────────────────────────────────────────────────────────────────────
# 메인: 하이브리드 앙상블 예측
# ─────────────────────────────────────────────────────────────────────────────
def hybrid_melting_predict(norm, db_prepared, ai_engine=None):
    """
    Parameters
    ----------
    norm        : dict — 정규화 조성 (wt%, 합계 ~100)
    db_prepared : list — solder_db 정제 항목
    ai_engine   : AIEngine (없으면 L6 스킵)

    Returns
    -------
    solidus  : float
    liquidus : float
    peak     : float
    detail   : dict  (레이어별 기여 정보)
    """
    from .utils import composition_distance

    family = _classify(norm)

    # ─── L1: DB 직접 일치 ────────────────────────────────────────────────────
    best_dist = 9999.0
    best_item = None
    knn_raw   = []

    for item in db_prepared:
        d = composition_distance(norm, item["comp"])
        knn_raw.append((d, item))
        if d < best_dist:
            best_dist = d
            best_item = item

    knn_raw.sort(key=lambda x: x[0])
    knn5 = knn_raw[:5]

    l1_sol, l1_liq, l1_w = None, None, 0.0
    if best_dist < 0.3:
        l1_sol = best_item["solidus"]
        l1_liq = best_item["liquidus"]
        l1_w   = math.exp(-best_dist * 6.0) * 4.0

        # dist<0.3 구간은 "실측값 최우선"을 규칙이 아니라 강제로 적용
        # (앙상블로 섞여 DB 기반 융점이 틀어지는 케이스 방지)
        final_sol = float(l1_sol)
        final_liq = float(l1_liq)
        if final_liq < final_sol:
            final_liq = final_sol + 1.0
        final_sol = max(50.0, min(420.0, final_sol))
        final_liq = max(50.0, min(520.0, final_liq))
        delta_t     = final_liq - final_sol
        peak_offset = 20.0 if delta_t < 5 else 25.0
        final_peak  = final_liq + peak_offset

        detail = {
            "family":    family,
            "layers":    [("L1:DB_direct(FORCED)", round(final_sol,2), round(final_liq,2), round(l1_w,3))],
            "best_dist": round(best_dist, 3),
            "best_name": best_item["name"] if best_item else "N/A",
            "l6_applied": False,
            "l6_delta":  (0.0, 0.0),
            "forced_db": True,
        }

        return round(final_sol, 1), round(final_liq, 1), round(final_peak, 1), detail

    # ─── L2: 상태도 보간 ─────────────────────────────────────────────────────
    phase_result = _phase_diagram_predict(norm, family)
    l2_sol, l2_liq, l2_conf = (phase_result if phase_result
                                else (None, None, 0.0))

    # 이원계/SAC 지배이면 상태도 신뢰도 최대 부여
    is_simple = family in ("SnBi", "SnIn", "SnPb", "SAC", "SnAg",
                            "SnCu", "SnSb", "SnZn")
    if l2_sol is not None:
        l2_w = l2_conf * (3.0 if is_simple else 1.8)
    else:
        l2_w = 0.0

    # ─── L3: KNN 가중 보간 ───────────────────────────────────────────────────
    if knn5:
        w_total = sum(1.0 / (d + 1e-6) for d, _ in knn5)
        l3_sol  = sum(item["solidus"]  * (1.0/(d+1e-6)) for d, item in knn5) / w_total
        l3_liq  = sum(item["liquidus"] * (1.0/(d+1e-6)) for d, item in knn5) / w_total
        l3_conf = math.exp(-knn5[0][0] * 0.6)
        # 이원계/SAC에서 KNN은 상태도 보조 역할만
        l3_w    = l3_conf * (0.4 if is_simple and l2_sol is not None else 1.2)
    else:
        l3_sol, l3_liq, l3_w = 217.0, 221.0, 0.1

    # ─── L4: CALPHAD (L2 없을 때, 또는 unknown 계열 보조) ──────────────────
    l4_sol, l4_liq, l4_conf = _calphad_approx(norm, family)
    # L2가 고신뢰도면 L4 비중 0에 수렴
    if l2_sol is not None and l2_conf > 0.85:
        l4_w = 0.0
    elif l2_sol is not None:
        l4_w = l4_conf * 0.3
    else:
        l4_w = l4_conf * 0.9

    # ─── 앙상블 ──────────────────────────────────────────────────────────────
    layers = []
    if l1_sol is not None:
        layers.append((l1_sol, l1_liq, l1_w, "L1:DB_direct"))
    if l2_sol is not None:
        layers.append((l2_sol, l2_liq, l2_w, "L2:phase_diagram"))
    layers.append((l3_sol, l3_liq, l3_w, "L3:knn"))
    if l4_w > 0:
        layers.append((l4_sol, l4_liq, l4_w, "L4:calphad"))

    total_w = sum(w for _, _, w, _ in layers)
    if total_w == 0:
        final_sol, final_liq = 217.0, 221.0
    else:
        final_sol = sum(s * w for s, _, w, _ in layers) / total_w
        final_liq = sum(l * w for _, l, w, _ in layers) / total_w

    # ─── L6: AI 델타 보정 ────────────────────────────────────────────────────
    l6_delta_sol, l6_delta_liq = 0.0, 0.0
    l6_applied = False
    if ai_engine is not None and best_dist > 3.0 and family == "other":
        try:
            ai_result = ai_engine.get_melting_data(norm)
            l6_delta_sol = max(-12.0, min(12.0, ai_result.get("delta_solidus",  0.0)))
            l6_delta_liq = max(-12.0, min(12.0, ai_result.get("delta_liquidus", 0.0)))
            ai_w = min(0.35, best_dist / 25.0)
            final_sol += l6_delta_sol * ai_w
            final_liq += l6_delta_liq * ai_w
            l6_applied = True
        except Exception:
            pass

    # ─── 물리 제약 ───────────────────────────────────────────────────────────
    if final_liq < final_sol:
        final_liq = final_sol + 1.0
    final_sol = max(50.0, min(420.0, final_sol))
    final_liq = max(50.0, min(520.0, final_liq))

    # ─── 피크 온도 (IPC-J-STD-020E 권역과 정합되도록 오프셋; JIS 조립·시험은 TM-650·Z3198 등과 병행 검토) ──
    delta_t     = final_liq - final_sol
    peak_offset = 20.0 if delta_t < 5 else 25.0
    final_peak  = final_liq + peak_offset

    detail = {
        "family":    family,
        "layers":    [(name, round(s,2), round(l,2), round(w,3))
                      for s, l, w, name in layers],
        "best_dist": round(best_dist, 3),
        "best_name": best_item["name"] if best_item else "N/A",
        "l6_applied": l6_applied,
        "l6_delta":  (round(l6_delta_sol,2), round(l6_delta_liq,2)),
    }

    return round(final_sol, 1), round(final_liq, 1), round(final_peak, 1), detail
