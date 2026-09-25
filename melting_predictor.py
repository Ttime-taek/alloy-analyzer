# melting_predictor.py  (v2.0 — Hybrid Melting Point Prediction Engine)
#
# 예측 레이어 (우선순위 순):
#   L1. DB 직접 일치      — composition_distance ≤ DB_EXACT_MATCH_EPS → DB 고상·액상 그대로(기준)
#   L2. 이진/삼원 상태도  — 문헌 기반 공정점·liquidus 곡선 정밀 보간
#   L3. KNN 가중 보간     — 조성 이웃 + L2(또는 이웃) 기준 융점대에서 고상·액상 OR 근접 DB를
#                          풀에 합쳐 가중(온도 정렬 보너스)으로 유사 온도대 다른 계열 반영
#   L4. CALPHAD 근사      — L2 없을 때만 활성화
#   L4e. 외부 CALPHAD(선택) — MELTING_CALPHAD_URL POST 시 추가 레이어
#   L6. AI 델타 보정      — 미지 조성에만 소량 반영
#
#   계열·레이어 가중: melting_ensemble.py + 선택 JSON (melting_ensemble_config.example.json 참고)
#
# 핵심 규칙:
#   · **DB 직접 일치(L1)** — solder_db 실측 행과 조성 거리 ≤ DB_EXACT_MATCH_EPS 이면
#     그 행의 고상·액상만 사용. 실측 앵커·미지원소 블렌드·L2/L3/L4/L6·물리 보정으로 덮지 않음(기준값).
#   · SAC 삼원계 → solidus 반드시 217°C (공정점 고정)
#   · 이원계 지배 → L2만 사용, CALPHAD 비활성
#   · L2 신뢰도 높을수록 L4 비중 0에 수렴

import math
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from .melting_ensemble import get_ensemble_profile
except ImportError:
    from test7.melting_ensemble import get_ensemble_profile

try:
    from .sn_pb_library import SN_PB_PHASE
    from .interp_pchip import interp_pchip_table_solidus_liquidus
except ImportError:
    from test7.sn_pb_library import SN_PB_PHASE
    from test7.interp_pchip import interp_pchip_table_solidus_liquidus

# AI 디스크 캐시 키 무효화용 — hybrid_melting_predict 로직·계수를 바꿀 때만 올린다.
MELTING_ENGINE_VERSION = "12"

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
    # 48wt%In: 공정(52%In, 118℃) 직전 — liquidus는 과대(143) 대신 상태도에 맞게 ~122℃
    (48.0, 117.0, 122.0),
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
# [2026-09-21 정확도 패치] 액상선 교정
#   변경 전: 0.5Cu 285, 1.0Cu 259, 2.0Cu 340, 3.0Cu 394 °C — 0.5Cu가 1.0Cu보다 높은 비단조 곡선이었고,
#            3.0Cu 394 °C는 Ni 0.5% 첨가 합금(Sn3.0Cu0.5Ni) 값이 섞인 것.
#   변경 후: 순수 Sn 231.9 → 공정 0.7Cu 227 (아공정, 단조 감소) → 과공정은 같은 DB의 실측 행
#            (Sn0.3Ag2.0Cu 270, Sn3.0Cu 312, Sn-3.5Cu-0.006P 320 °C)에 맞춘 단조 증가 곡선. 1.0Cu는 0.7↔2.0 보간.
#   결과: Sn-0.5Cu 예측 238.9 → 약 229 °C, 과공정 Sn-Cu 홀드아웃 오차 감소 (수치는 PR 설명 참고).
SN_CU_PHASE = [
    (0.0,  231.9, 231.9),
    (0.5,  227.0, 228.5),
    (0.7,  227.0, 227.0),
    (1.0,  227.0, 237.0),
    (2.0,  227.0, 270.0),
    (3.0,  227.0, 312.0),
    (3.5,  227.0, 320.0),
]

# Sn-Sb  (ASM)
SN_SB_PHASE = [
    (0.0,  231.0, 231.0),
    (5.0,  235.0, 240.0),
    (10.0, 240.0, 246.0),
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
    """
    상태도 고상선/액상선 보간 — PCHIP(단조 Hermite)로 구간 내 급격한 기울기 점프 완화.
    scipy 미설치 시 interp_pchip 모듈이 선형 보간으로 폴백.
    """
    if not table:
        return float("nan"), float("nan")
    xf = float(x)
    if xf <= table[0][0]:
        return float(table[0][1]), float(table[0][2])
    if xf >= table[-1][0]:
        return float(table[-1][1]), float(table[-1][2])
    s, lq = interp_pchip_table_solidus_liquidus(xf, table)
    return float(s), float(lq)


def _smoothstep01(t):
    """t∈[0,1] 에서 매끈한 S곡선 (계단 방지용)."""
    t = max(0.0, min(1.0, float(t)))
    return t * t * (3.0 - 2.0 * t)


# ─────────────────────────────────────────────────────────────────────────────
# Sn-Pb-Bi 3원계 [2026-09-25 계산 로직 점검]
#   이전: Pb≥1%면 Sn-Pb 이원 표만 쓰고 Bi를 무시, Pb가 조금이라도 있으면 Sn-Bi 경로에서 제외.
#         Sn43Pb43Bi14(실측 144/163) → 183/212, Sn42Bi58+Pb1 → 182/222(실제는 Pb 오염 시 오히려 하강).
#   변경: Sn-Bi 이원·Sn-Pb 이원을 Pb:Bi 비율로 섞은 뒤, 3원 공정(Bi52 Pb32 Sn16, 96℃)에
#         가까울수록 96℃ 쪽으로 당긴다. Pb 또는 Bi가 0이면 기존 이원계 값과 정확히 같다.
#   기준점(Wikipedia "Solder alloys" 표): Sn43Pb43Bi14 144/163, Bi52Pb32Sn16 96,
#         Bi46Sn34Pb20 100/105, Sn62Pb36Ag2 179 → 모두 ±8℃ 이내. 정밀값은 실제 CALPHAD 도입 시 교체.
# ─────────────────────────────────────────────────────────────────────────────
SN_PB_BI_TERNARY_EUTECTIC = {"Sn": 16.0, "Pb": 32.0, "Bi": 52.0, "T": 96.0}
SN_PB_BI_TERNARY_SIGMA = 55.0     # 3원 공정 조성으로부터의 거리(wt%) 스케일
SN_PB_BI_MINOR_SCALE = 5.0        # Pb·Bi 중 적은 쪽이 이 정도(wt%)는 돼야 3원 효과가 본격화


def _sn_pb_bi_pull(sn, pb, bi):
    """3원 공정(96℃) 쪽으로 당기는 가중 0~1. Pb 또는 Bi가 0이면 0."""
    sn, pb, bi = max(0.0, float(sn)), max(0.0, float(pb)), max(0.0, float(bi))
    minor = min(pb, bi)
    tot = sn + pb + bi
    if minor <= 0.0 or tot <= 0.0:
        return 0.0
    e = SN_PB_BI_TERNARY_EUTECTIC
    d2 = (
        (sn / tot * 100.0 - e["Sn"]) ** 2
        + (pb / tot * 100.0 - e["Pb"]) ** 2
        + (bi / tot * 100.0 - e["Bi"]) ** 2
    )
    near = math.exp(-d2 / (SN_PB_BI_TERNARY_SIGMA ** 2))
    return near * _smoothstep01(minor / SN_PB_BI_MINOR_SCALE)


def _sn_pb_bi_base(sn, pb, bi):
    """
    Sn-Pb-Bi 기준 고상·액상 (다른 원소 보정 전).
    반환: (solidus, liquidus, pull) — pull은 3원 공정 쪽 가중(하류 Sn-Bi 고정 보정 완화용).
    """
    sn, pb, bi = max(0.0, float(sn)), max(0.0, float(pb)), max(0.0, float(bi))
    eff_bi = (bi / (sn + bi) * 100.0) if (sn + bi) > 0 else 100.0
    eff_pb = (pb / (sn + pb) * 100.0) if (sn + pb) > 0 else 100.0
    x = pb / (pb + bi) if (pb + bi) > 0 else 0.0
    if x <= 0.0:
        s, l = _interp(eff_bi, SN_BI_PHASE)
        return float(s), float(l), 0.0
    if x >= 1.0:
        s, l = _interp(eff_pb, SN_PB_PHASE)
        return float(s), float(l), 0.0
    s_bi, l_bi = _interp(eff_bi, SN_BI_PHASE)
    s_pb, l_pb = _interp(eff_pb, SN_PB_PHASE)
    s = (1.0 - x) * s_bi + x * s_pb
    l = (1.0 - x) * l_bi + x * l_pb
    g = _sn_pb_bi_pull(sn, pb, bi)
    t_e = SN_PB_BI_TERNARY_EUTECTIC["T"]
    s = s - (s - t_e) * g
    l = l - (l - t_e) * g
    return float(s), float(max(l, s)), float(g)


SN_IN_ZN_TERNARY_EUTECTIC_C = 108.0   # In-Sn-Zn 3원 공정(~108℃)


def _combine_sn_in_zn(s_in, l_in, s_zn, l_zn):
    """
    Sn-In 이원값과 Sn-Zn 이원값을 결합(순수 Sn 231℃ → 3원 공정 108℃ 사이 '남은 여유'의 곱).
    대칭식이라 SnIn·SnZn 어느 경로로 계산해도 같다. 한쪽 용질이 0이면 다른 쪽 이원값 그대로.
    공정 근처(예: Sn56In42Zn1, 실측 117℃)에서 가산식처럼 과도하게 내려가지 않는다.
    """
    t0 = SN_IN_PHASE[0][1]            # 231.0 (두 표 공통 순수 Sn 값)
    te = SN_IN_ZN_TERNARY_EUTECTIC_C
    span = t0 - te

    def _mix(a, b):
        a = max(float(a), te)
        b = max(float(b), te)
        return te + (a - te) * (b - te) / span

    s = _mix(s_in, s_zn)
    l = _mix(l_in, l_zn)
    return s, max(l, s)


def _in_floor_relaxed_by_bi(floor_c, bi):
    """SAC/SnAg In 블록의 고상 바닥: Bi 2→8%에서 Sn-Bi 공정(139℃) 쪽으로 연속 완화."""
    return float(floor_c) - (float(floor_c) - 139.0) * _smoothstep01((float(bi or 0.0) - 2.0) / 6.0)


def _norm_pb_bi_pull(norm):
    try:
        return _sn_pb_bi_pull(norm.get("Sn", 0) or 0, norm.get("Pb", 0) or 0, norm.get("Bi", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _snbi_eutectic_pin_release(norm):
    """
    Sn-Bi 139℃ 고정 보정(plateau·physics)을 Pb 동반 시 풀어 주는 정도(0=그대로, 1=완전 해제).
    3원 공정 가중 g가 0.5 이상이면 완전 해제 — 이 보정은 L2와 최종 단계에서 두 번 적용되므로
    부분 해제로 두면 누적되어 3원 공정 근처(Bi46Sn34Pb20)를 +14℃ 끌어올렸다.
    Pb 미량 오염(Sn42Bi58+Pb1, g≈0.06)에서는 거의 그대로 유지된다.
    """
    return _smoothstep01(_norm_pb_bi_pull(norm) / 0.5)


def _db_neighbor_gate(dist, lo=0.10, hi=0.52):
    """
    가장 가까운 DB 행에 대한 신뢰 가중 (0~1).
    dist가 작을수록 1에 가깝고, hi 이상에서는 0 — 이전의 dist<0.3 계단을 부드럽게 대체.
    """
    if dist <= lo:
        return 1.0
    if dist >= hi:
        return 0.0
    return 1.0 - _smoothstep01((dist - lo) / (hi - lo))


def _physics_sn_bi_rich_solidus(norm, family, solidus):
    """
    Physics-informed soft prior: 고 Bi Sn–Bi 계열에서 고상선이 Sn–Bi 공정부(~139℃) 복합계로
    크게 튀지 않도록 [134, 144]℃ 복도 밖 값을 완만히 끌어당김 (분류/계단 아님).
    """
    try:
        bi = float(norm.get("Bi", 0) or 0.0)
    except (TypeError, ValueError):
        return solidus
    if family != "SnBi" or bi < 23.0:
        return solidus
    lo, hi, mu = 134.0, 144.0, 139.0
    w = min(0.55, (bi - 18.0) / 18.0)  # Bi=23→0.28, Bi=25→0.39
    # [2026-09-25] Bi=23에서 가중이 0.28로 바로 켜지던 계단 제거(23→24.5에서 서서히),
    # Pb 동반 시 3원 공정(96℃) 쪽으로 내려가야 하므로 139 복도로 끌어올리지 않음.
    w *= _smoothstep01((bi - 23.0) / 1.5) * (1.0 - _snbi_eutectic_pin_release(norm))
    s = float(solidus)
    if s < lo:
        return s + (lo - s) * (0.35 * w)
    if s > hi:
        # 상한 밖: 공정부 쪽으로 완만히 복귀 (한 번에 139로 못 박지 않음)
        return s - (s - hi) * (0.45 * w) - (s - mu) * (0.12 * w)
    return s


def _snbi_highbi_lowcu_plateau(norm, family, solidus):
    """
    Sn–Bi 계열에서 Bi가 충분히 높고(Cu 영향이 과대평가되기 쉬운 구간),
    Cu < 0.7 wt% 에서는 고상선이 Sn–Bi 공정온도(≈138–139℃) 부근에서
    급격히 상승하지 않고 plateau 되도록 138℃ 근처로 '앵커'한다.

    목표:
    - Bi >= 20%, 0.5 <= Cu < 0.7% 구간: solidus ∈ [137.5, 138.5]
    - 연속성: hard step 대신 smoothstep 기반 가중(blend) 후 제한(clamp)
    """
    if family != "SnBi":
        return float(solidus), None

    try:
        bi = float(norm.get("Bi", 0) or 0.0)
        cu = float(norm.get("Cu", 0) or 0.0)
    except (TypeError, ValueError):
        return float(solidus), None

    # [2026-09-25 계산 로직 점검] 이전에는 Bi=20.00%·Cu=0.80%에서 켜고 끄는 하드 경계라
    # Sn80.01Bi19.99(159.4℃) → Sn80Bi20(139.0℃)처럼 0.01%에 20℃가 튀었다.
    # Bi 17→20%, Cu 0.8→1.0%에서 고정 강도를 서서히 바꾸고, Bi≥20·Cu≤0.8 안쪽은 기존과 동일.
    if bi < 17.0 or cu >= 1.0:
        return float(solidus), None

    s0 = float(solidus)
    # 실측 기반 앵커(대표 케이스: Sn-1Ag-25Bi-0.7Cu solidus ≈ 137.81℃)
    target = 137.8

    # Pb 동반 시 3원 공정(96℃) 쪽으로 내려가야 하므로 139 부근 고정을 그만큼 약화
    pb_release = 1.0 - _snbi_eutectic_pin_release(norm)
    cu_fade = 1.0 - _smoothstep01((cu - 0.80) / 0.20)       # 0.80→1.00 에서 해제

    # Bi가 높을수록(20→30) 앵커를 강하게
    bi_gate = _smoothstep01((bi - 20.0) / 10.0)
    # Cu 0.50~0.80 구간에서 plateau를 강하게 (경계에서 hard step 금지)
    cu_gate_lo = _smoothstep01((cu - 0.48) / 0.08)          # 0.48→0.56
    cu_gate_hi = 1.0 - _smoothstep01((cu - 0.80) / 0.04)    # 0.80→0.84 에서 약화
    w = 0.96 * bi_gate * cu_gate_lo * cu_gate_hi * pb_release

    s1 = s0 * (1.0 - w) + target * w

    # 공정 반응 pinning 복도: Cu 0.5~0.8 → 137.3~138.3, 그 밖 → 137~139 (Cu에 대해 연속 보간)
    tight = _smoothstep01((cu - 0.40) / 0.10) * (1.0 - _smoothstep01((cu - 0.80) / 0.10))
    lo = 137.0 + 0.3 * tight
    hi = 139.0 - 0.7 * tight
    s1c = min(max(s1, lo), hi)
    strength = _smoothstep01((bi - 17.0) / 3.0) * cu_fade * pb_release
    clamped = strength > 0.0 and abs(s1c - s1) > 1e-9
    s1 = s1 + (s1c - s1) * strength

    return float(s1), {
        "applied": True,
        "bi": round(bi, 3),
        "cu": round(cu, 3),
        "w": round(float(w), 4),
        "target": target,
        "clamped": clamped,
    }


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

    # SAC 모재(고-Sn, Ag+Cu, In 거의 없음)는 Bi를 첨가해도 SAC 경로가 정확하다.
    # 이진 Sn-Bi 경로는 SAC+Bi 액상선을 ~25℃ 과대평가하고 Bi=5% 분류 경계에서 액상선이
    # 불연속(점프)하므로(프로젝트 Anti-step 규칙 위반), In이 거의 없는(≤2%) SAC 모재는
    # SnBi로 라우팅하지 않고 SAC로 유지한다.
    # (In 동반 고-Bi(예 Bi10 In6, Bi14 In11)는 Sn-In 반응이 지배 → 기존대로 SnBi.)
    sac_matrix_lowin = (sn >= 78 and ag > 0 and cu > 0 and inp <= 2.0 and zn <= 1.0)

    # Binary trace systems need a stable route at the threshold.  Treat a
    # composition containing only Sn+that element as the corresponding binary
    # even below the historical commercial cut-off; otherwise a 0.01 wt%
    # change can jump through the generic CALPHAD branch.
    pure_sn_pb = (
        pb > 0 and ag == 0 and cu == 0 and bi == 0 and inp == 0 and zn == 0 and sb == 0
    )
    pure_sn_zn = (
        zn > 0 and ag == 0 and cu == 0 and bi == 0 and inp == 0 and pb == 0 and sb == 0
    )
    pure_sn_sb = (
        sb > 0 and ag == 0 and cu == 0 and bi == 0 and inp == 0 and pb == 0 and zn == 0
    )

    # Define this before the broad Bi classifier so the transition cannot be
    # swallowed by the SnBi return path once Sn falls below the SAC cutoff.
    sac_bi_transition = (
        sn >= 76.0 and ag > 0 and cu > 0 and inp <= 2.0 and zn <= 1.0
        and 16.0 <= bi <= 20.0
    )

    # Pb 1% 이상은 SnPb 경로(저-Pb Sn97.8Pb2.2 등 상용 커버리지).
    # [2026-09-25] 단, Bi가 Pb보다 많고 5% 초과면 Sn-Bi 경로(3원 보정 포함)로 보낸다.
    # 이전에는 Sn42Bi58에 Pb 1%만 섞여도 Sn-Pb 표로 가서 고상 139→182℃로 튀었다.
    if pure_sn_pb or (pb >= 1 and (pb >= bi or bi <= 5)):
        return "SnPb"
    if sac_bi_transition:
        return "SAC_BI_TRANSITION"
    # Bi > 5%: Sn-Bi 계열. (Bi ≤ 5%인 SAC+Bi/In 첨가는 SAC 경로.)
    # 과거 inp==0 일 때만 SnBi로 두면 Bi≥In 인 고Bi+In(예: Bi10 In6 …)이 neither SAC nor SnBi 가 되어
    # other+L4로 고상·액상이 과대(≈250℃+) 평가된다.
    # In 상한(과거 8%)는 Ag–Cu 저함량·고Bi–In(예 In 11, Bi 14)이 SAC·SnBi 모두 아니게
    # other→L4 단독 ~250℃ 과대평가되던 구간. SnBi L2+In 보정이 커버하므로 14%까지 완화.
    # [2026-09-25] `pb == 0` 조건 제거: Pb 0.05% 불순물로 Sn80Bi20이 other(+57℃)로 떨어졌다.
    # Pb는 SnBi L2의 3원 보정(_sn_pb_bi_base)이 처리한다.
    if bi > 5 and not sac_matrix_lowin:
        if inp == 0:
            return "SnBi"
        if inp <= 14.0 and bi >= inp:
            return "SnBi"
    # Sn-In: Bi 미량(≤1%)까진 허용. In≥5이면 In 강하가 지배하므로 SnIn 경로.
    # (단, Ag>0 + In≥5는 Sn-Ag 반응도 병존 → SnAg 경로에서 In/Bi 보정 처리.)
    # [2026-09-25] `pb == 0 and ag == 0` → Pb 1% 미만(위에서 Pb≥1은 SnPb), Ag 1% 미만 허용.
    # 이전에는 Sn48In52(117℃)에 Ag·Pb 0.05%만 섞여도 other로 떨어져 +29℃.
    if inp > 5 and bi <= 1 and ag < 1.0:
        return "SnIn"
    # Sn-Zn-Bi 3원계 (Bi ≤ 5%): Sn8Zn3Bi 등 상용 조성 — Bi 없음을 요구하던 기존 조건이
    # 54°C 규모 오차 발생시켜 완화.
    if (zn > 3 and bi <= 5) or pure_sn_zn:
        return "SnZn"
    # SAC 4원계 커버리지:
    # - 이전(bi < 3)은 boundary에서 Bi=3.0%를 "other"로 떨궈 L2(상태도)를 죽이고
    #   L4(CALPHAD)가 지배하게 만듦 → 고상선 +20~30°C 과대평가 원인.
    # - Sn-Ag-Cu-Bi(Bi ≤ 5%) 상용 조성은 SAC 반응이 주도하고 Bi가 공정 depression을
    #   제공하는 구조라 SAC 경로에서 처리하는 편이 훨씬 정확.
    # - In 첨가 SAC(In≤~8%): 분류만 inp==0으로 막히면 family=="other"가 되어 L4만 지배하고
    #   실측(예: Ag3.5 Bi0.5 Cu0.8 In6 Sn89 → 고상~202℃/액상~206℃)과 크게 어긋남.
    #   하단 SAC 상태도에는 이미 In/Bi 보정식이 있으므로 inp≤8은 SAC로 본다.
    # - 저Ag·Cu 유지 + Bi≤12·In≤14·Bi<In 인 경우: SnBi(Bi≥In)에 안 걸려 other+L4(과대)로
    #   떨어지기 쉬움(예: Sn79 Ag1 Cu1 Bi8 In11). SAC 5원 보정이 더 물리적으로 일관.
    #   (고Bi+고In에서 Bi≥In 은 위 SnBi 분기가 우선.)
    # In 거의 없는 SAC 모재는 Bi 12~18%까지도 SAC로 유지(Sn>=78 이 상한을 자연 한정).
    # 그렇지 않으면 Bi 12~18 구간이 other→L4 로 떨어져 과대평가된다.
    if sac_matrix_lowin and bi <= 18.0:
        return "SAC"
    if sn >= 78 and ag > 0 and cu > 0 and bi <= 12.0 and inp <= 14.0:
        return "SAC"
    if sn > 80 and ag > 0 and cu == 0:
        return "SnAg"
    if sn > 80 and cu > 0 and ag == 0:
        return "SnCu"
    if sb > 3 or pure_sn_sb:
        return "SnSb"
    return "other"


def _prediction_uncertainty(
    norm,
    family,
    best_dist,
    unk_pct_global,
    layers_for_weights,
    db_exact_match,
    measured_anchor_detail,
):
    """
    수치 신뢰도 힌트(오차 ℃ 아님).
    UI/API에서 '참고용' 구간을 표시할 때 사용.
    """
    out = {
        "classification_boundary_sn_sac_bi": False,
        "extrapolation_heuristic": False,
        "dominant_calphad_layer": False,
        "reason_codes": [],
    }
    if db_exact_match:
        out["reason_codes"].append("db_exact_match")
        return out
    if measured_anchor_detail:
        out["reason_codes"].append("measured_anchor")
        return out

    bi = float(norm.get("Bi") or 0)
    sn = float(norm.get("Sn") or 0)
    ag = float(norm.get("Ag") or 0)
    cu = float(norm.get("Cu") or 0)
    inp = float(norm.get("In") or 0)
    pb = float(norm.get("Pb") or 0)

    if pb == 0 and sn > 80 and ag > 0 and cu > 0 and inp <= 8 and 4.2 <= bi <= 6.2:
        out["classification_boundary_sn_sac_bi"] = True
        out["reason_codes"].append("near_sn_sac_bi_classification")

    tw = sum(w for _, _, w, _ in layers_for_weights)
    l4w = sum(w for _, _, w, lbl in layers_for_weights if str(lbl).startswith("L4:"))
    if tw > 1e-9 and (l4w / tw) >= 0.38:
        out["dominant_calphad_layer"] = True
        out["reason_codes"].append("calphad_weight_high")

    bd = float(best_dist)
    unk = float(unk_pct_global or 0)
    if family == "other" or bd >= 12.0 or unk >= 0.05 or out["dominant_calphad_layer"]:
        out["extrapolation_heuristic"] = True
        if family == "other":
            out["reason_codes"].append("family_other")
        if bd >= 12.0:
            out["reason_codes"].append("db_far")
        if unk >= 0.05:
            out["reason_codes"].append("unknown_noncore")

    return out


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

    # High-Bi SAC additions cross from an Ag-Cu-Sn matrix to the Sn-Bi
    # eutectic.  Keep the two physically meaningful curves but blend them over
    # a finite composition corridor instead of selecting one with a hard
    # classifier threshold.
    if family == "SAC_BI_TRANSITION":
        sac = _phase_diagram_predict(norm, "SAC")
        snbi = _phase_diagram_predict(norm, "SnBi")
        if sac is None or snbi is None:
            return None
        w = _smoothstep01((float(bi) - 16.0) / 4.0)
        sol = float(sac[0]) * (1.0 - w) + float(snbi[0]) * w
        liq = float(sac[1]) * (1.0 - w) + float(snbi[1]) * w
        confidence = float(sac[2]) * (1.0 - w) + float(snbi[2]) * w
        return sol, liq, confidence

    # ── Sn-Bi 계 ─────────────────────────────────────────────────────────────
    if family == "SnBi":
        # 유효 Bi 비율: Bi/(Sn+Bi) 기준
        # Pb가 없으면 Sn-Bi 이원 표 그대로. Pb 동반 시 Sn-Pb-Bi 3원 보정(3원 공정 96℃).
        sol, liq, g_pb = _sn_pb_bi_base(sn, pb, bi)
        # Sn-Bi 공정(139℃) 바닥 — Pb 동반 시 3원 공정 쪽으로 함께 내려간다.
        eut = 139.0 - (139.0 - SN_PB_BI_TERNARY_EUTECTIC["T"]) * g_pb

        # Ag 존재 시 삼원계 공정점(139°C) 인력 보정
        # Sn-Ag-Bi 삼원계: Bi≥10%, Ag≥1%에서 solidus 139°C 공정점으로 빠르게 수렴 (문헌)
        # 기존 (ag/3·bi/20) 계수는 Sn3Ag15Bi(실측 139°C)에서 pull≈0.75에 그쳐 +10°C
        # 오차. 실측 정합을 위해 수렴 속도(ag/2.5·bi/15) 및 최대 가중(0.97) 상향.
        if ag >= 1.0 and bi >= 10.0:
            pull  = min(1.0, (ag / 2.5) * (bi / 15.0))
            sol   = sol * (1.0 - pull * 0.97) + eut * (pull * 0.97)
        elif ag > 0:
            # 소량 Ag: liquidus 소폭 상승만
            liq_adj = min(ag * 12.5, 20.0)
            liq    += liq_adj
            sol     = max(sol, eut)

        if cu > 0:
            liq += cu * 3.5
            # 고 Bi(≥20%) + Cu>0.5%: 미량 Cu가 액상선을 더 올림 (실측 Sn-1Ag-25Bi-0.7Cu 액상선 ~197.68℃에 맞춘 기울기)
            if bi >= 20.0 and cu > 0.5:
                liq += (cu - 0.5) * 13.3
        if sb > 0:
            liq += sb * 2.0
        # In 동시 첨가(Bi≥In 분류 구간): Sn-In 반응으로 고상·액상 추가 하강.
        # 고Bi일수록 동일 wt% In의 고상 추가 하강이 과대일 수 있어 Bi/(Sn+Bi) 기준 eff_bi로 완화한다.
        if inp > 0:
            denom_sb = sn + bi
            eff_bi_pct = (bi / denom_sb * 100.0) if denom_sb > 1e-9 else float(bi)
            damp_hi_bi = _smoothstep01((eff_bi_pct - 7.0) / 24.0)
            ds_in = inp * (1.85 - 0.38 * damp_hi_bi)
            dl_in = inp * (2.15 - 0.42 * damp_hi_bi)
            sol -= ds_in
            liq -= dl_in
            sol = max(sol, 128.0 - (128.0 - SN_PB_BI_TERNARY_EUTECTIC["T"]) * g_pb)
        # Bi가 높고 Cu가 낮은 구간에서 고상선 plateau 앵커 (Cu 과대상승 방지)
        sol, _ = _snbi_highbi_lowcu_plateau(norm, family, sol)
        return sol, liq, 0.92

    # ── Sn-In 계 ─────────────────────────────────────────────────────────────
    if family == "SnIn":
        denom  = sn + inp
        eff_in = (inp / denom * 100) if denom > 0 else inp
        sol, liq = _interp(eff_in, SN_IN_PHASE)
        # [2026-09-25] Zn 동반 시 Sn-Zn 이원 강하를 더한다(가산 근사). SnZn 경로의 In 항과
        # 같은 식이라 In=5% 분류 경계(SnZn↔SnIn)에서 값이 일치한다. 이전에는 Zn을 무시해
        # Sn89Zn6In5가 In 5.00→5.02%에서 고상 200→220℃로 튀었다.
        if zn > 0:
            s_zn, l_zn = _interp(zn, SN_ZN_PHASE)
            sol, liq = _combine_sn_in_zn(sol, liq, s_zn, l_zn)
        if ag > 0:
            liq += ag * 5.0
        if bi > 0:
            sol  = max(sol - bi * 1.5, min(117.0, sol))
            liq  = max(liq - bi * 0.8, sol)
        return sol, liq, 0.90

    # ── Sn-Pb 계 ─────────────────────────────────────────────────────────────
    if family == "SnPb":
        # Bi가 없으면 Sn-Pb 이원 표 그대로. Bi 동반 시 Sn-Pb-Bi 3원 보정.
        sol, liq, _g = _sn_pb_bi_base(sn, pb, bi)
        # [2026-09-25] Ag: Sn-Pb 공정 183 → Sn62Pb36Ag2 179℃(3원 공정). Sn쪽·공정 부근만 적용하고
        # Pb-rich(Pb/(Sn+Pb) 60→80%)에서는 서서히 해제(Pb-Ag 거동이 다름).
        if ag > 0:
            eff_pb = (pb / (sn + pb) * 100.0) if (sn + pb) > 0 else 100.0
            sn_side = 1.0 - _smoothstep01((eff_pb - 60.0) / 20.0)
            d_ag = 2.0 * min(float(ag), 2.0) * sn_side
            sol -= d_ag
            liq -= d_ag
        return sol, max(liq, sol), 0.92

    # ── Sn-Zn 계 ─────────────────────────────────────────────────────────────
    if family == "SnZn":
        sol, liq = _interp(zn, SN_ZN_PHASE)
        # [2026-09-25] In 동반 시 Sn-In 이원 강하를 더한다(SnIn 경로의 Zn 항과 같은 식).
        if inp > 0:
            eff_in = (inp / (sn + inp) * 100.0) if (sn + inp) > 0 else 100.0
            s_in, l_in = _interp(eff_in, SN_IN_PHASE)
            sol, liq = _combine_sn_in_zn(s_in, l_in, sol, liq)
        # Sn-Zn-Bi 3원계 Bi depression: 상업 조성 Sn8Zn3Bi(실측 190/197) 정합.
        # 기존 liquidus만 depression하던 식에 solidus 하강도 추가.
        if bi > 0:
            sol -= bi * 2.7
            liq -= bi * 2.0
        return sol, liq, 0.82

    # ── SAC 삼원계 ────────────────────────────────────────────────────────────
    if family == "SAC":
        # Solidus: SAC 공정점 217°C + Cu>1wt% 시 소폭 상승 — Cu≈1% 경계를 smoothstep으로 (계단 완화)
        uplift = max(0.0, float(cu) - 1.0) * 3.0
        sac_edge = _smoothstep01((float(cu) - 0.88) / 0.26)
        sol = SAC_TERNARY_EUTECTIC["solidus"] + uplift * sac_edge

        # Liquidus: Sn-Ag 상태도 기반 + Cu 보정
        _, liq_ag = _interp(ag, SN_AG_PHASE)
        liq = liq_ag
        if cu > 0.7:
            liq += (cu - 0.7) * 9.0

        # Bi 소량 첨가 효과 (SAC 4원계: Bi ≤ 5%)
        # In 동시 첨가(inp≤8, SAC 분류) 시 고상·액상 간격은 주로 아래 In 블록 계수로 맞추고,
        # 본 Bi 항은 Bi 단독·저-In SAC+Bi(Sn3Ag0.5Cu3Bi 등) 실측에 맞춘 미량 depression이다.
        # Bi+In 동시일 때 액상선만 미세 추가 하강(Δ 과대 완화 — DSC 간격 정밀화).
        # - 정상 SAC(Ag≈3%)에서는 Ag3Sn/Cu6Sn5 IMC 그물이 Bi의 solidus 하강을 일부 완화
        #   (계수 ≈ 1.8 °C/%Bi) → Sn3.0Ag0.5Cu3Bi 실측 209°C와 정합.
        # - 저-Ag(Ag < 1.5%: SAC0307+Bi, Sn-Cu-Bi 계열) 쪽은 Ag3Sn 기여가 작고
        #   Sn-Cu-Bi 삼원 공정 반응이 지배 → depression이 조금 더 강함
        #   (문헌·실측 기준 ≈ 2.6 °C/%Bi)
        #   예: Sn-0.3Ag-0.5Cu-3Bi 실측 solidus ≈ 208°C.
        if bi > 0:
            bi_sol_coef = 2.6 if ag < 1.5 else 1.8
            sol -= bi * bi_sol_coef
            liq -= bi * 0.9
            # 저-Ag + Bi에서 Cu가 액상선을 약간 더 끌어올림 (Cu6Sn5 재용해 지연)
            if ag < 1.5 and cu > 0:
                liq -= bi * 0.25 * min(1.0, cu / 0.7)
            # 고-Bi(>6%) SAC+Bi: 1차 용융 개시가 Sn-Bi 공정(~139℃) 쪽으로 부드럽게 하강한다.
            # 하드 분류 전환(SnBi 경로) 없이 연속적으로 처리해 Bi=5% 경계 액상선 점프를 제거.
            if bi > 6.0:
                w = _smoothstep01((bi - 6.0) / 12.0)   # Bi 6→0, 18→1
                sol = sol * (1.0 - 0.82 * w) + 139.0 * (0.82 * w)
            if inp > 0 and bi > 0:
                liq -= min(float(bi), 5.0) * float(inp) * 0.022

        # In 저~중량 첨가 (SAC 5원 근처: Ag–Cu–Sn–Bi–In 공존)
        # 실측 예: Ag3.5 Bi0.5 Cu0.8 In6 Sn89 → 고상≈202℃ 액상≈206℃ (Δ≈4℃).
        # 과거 inp==0 분류 때문에 other+L4 과대평가되던 구간은 _classify에서 SAC로 보정하고,
        # 여기서는 DSC 상 고상·액상 간격에 맞추도록 계수 분리(SnAg 계열과 역할 분담).
        if inp > 0:
            sol -= inp * 2.35
            liq -= inp * 2.58
            # [2026-09-25] 바닥 190℃는 저-Bi SAC+In용. Bi가 많으면(2→8%) Sn-Bi 공정 쪽으로 풀어준다.
            # 이전에는 앞 Bi 블록이 139℃ 쪽으로 내린 고상선을 190으로 되돌려, Bi=In 분류 경계
            # (Sn79 Ag1 Cu1 Bi9.5 In9.5)에서 고상 +22℃ 점프, 탐색에 고상 189℃ 가짜 후보가 나왔다.
            sol  = max(sol, _in_floor_relaxed_by_bi(190.0, bi))

        # Sb 첨가 효과
        if sb > 0:
            liq += sb * 2.5

        # Sn-Bi 공정 고상선(≈139℃) 아래로는 내려가지 않음
        sol = max(sol, 139.0)
        if liq < sol:
            liq = sol + 1.0
        return sol, liq, 0.90

    # ── Sn-Ag 이원계 (± In, Bi 소량) ────────────────────────────────────────
    if family == "SnAg":
        sol, liq = _interp(ag, SN_AG_PHASE)
        if sb > 0:
            liq += sb * 2.0
        # Sn-Ag-In 저·중 In(≤~10%): Sn-rich 영역에서 In은 solidus를 공격적으로 낮춤
        # (Ag3Sn 형성이 Sn-In 공정점 반응을 완전히 차단하지 못함).
        # Sn3.5Ag0.5Bi3In(실측 207/214), Sn3.5Ag0.5Bi8In(실측 198/210) 정합 계수.
        if inp > 0:
            sol -= inp * 3.0
            liq -= inp * 1.4
            sol  = max(sol, _in_floor_relaxed_by_bi(190.0, bi))
        # Sn-Ag-Bi 소량(Bi ≤ 5%): Ag3Sn IMC와 Bi-solidus-depression의 공존.
        # Bi>5%(In>Bi라 SnBi가 아닌 경우)는 바닥 170℃를 Sn-Bi 공정 쪽으로 푼다.
        if bi > 0:
            sol -= bi * 2.5
            liq -= bi * 1.2
            floor_bi = 170.0 - (170.0 - 139.0) * _smoothstep01((float(bi) - 5.0) / 5.0)
            sol  = max(sol, floor_bi)
        return sol, liq, 0.85

    # ── Sn-Cu 이원계 ─────────────────────────────────────────────────────────
    if family == "SnCu":
        sol, liq = _interp(cu, SN_CU_PHASE)
        # [2026-09-25] Sb: Sn-Sb 이원 상승분을 더한다(가산 근사, 고상선 포함). SnSb 경로의 Cu 항과
        # 같은 식이라 미량 Cu 첨가로 SnSb→SnCu 분류가 바뀌어도 값이 이어진다.
        # (이전: liq += sb*1.5만 반영, 고상선은 Sb 무시 → Sn93.7Sb6.3에 Cu 0.05%로 −4.5℃)
        if sb > 0:
            s_sb, l_sb = _interp(sb, SN_SB_PHASE)
            sol += s_sb - SN_SB_PHASE[0][1]
            liq += l_sb - SN_SB_PHASE[0][2]
        return sol, max(liq, sol), 0.85

    # ── Sn-Sb 계 ─────────────────────────────────────────────────────────────
    if family == "SnSb":
        sol, liq = _interp(sb, SN_SB_PHASE)
        if cu > 0:
            s_cu, l_cu = _interp(cu, SN_CU_PHASE)
            sol += s_cu - SN_CU_PHASE[0][1]
            liq += l_cu - SN_CU_PHASE[0][2]
        return sol, max(liq, sol), 0.82

    return None


# ─────────────────────────────────────────────────────────────────────────────
# L2 분류 경계 완충 [2026-09-25 계산 로직 점검]
#   _classify는 조건 분기라 경계에서 계열이 바뀌면 상태도 식 전체가 바뀐다.
#   경계 앞뒤 폭 안에서는 양쪽 계열의 L2를 smoothstep으로 섞어 0.01% 차이로 값이 튀지 않게 한다.
#   양쪽 계열은 경계 바로 바깥 조성을 _classify에 넣어 정한다(분류 규칙은 한 곳에만 둠).
# ─────────────────────────────────────────────────────────────────────────────
# (축, 경계값, 반폭 wt%) — "A-B"는 A−B 차이 축(A+B 합은 유지)
_L2_CORRIDORS = (
    ("Bi-In", 0.0, 1.0),   # SnBi(Bi≥In) ↔ SAC/SnAg(Bi<In)
    ("Pb-Bi", 0.0, 1.0),   # SnPb(Pb≥Bi) ↔ SnBi(Bi>Pb)
    ("In", 5.0, 0.5),      # SnZn ↔ SnIn
    ("Ag", 1.0, 0.5),      # SnIn(Ag<1) ↔ 그 외
    ("Pb", 1.0, 0.5),      # Pb 1% 경계
    ("Bi", 5.0, 0.5),      # Bi 5% 경계(SAC 모재가 아닌 경우)
)


def _shift_axis(norm, axis, value):
    """축 값을 value로 옮긴 조성(차이는 Sn으로 보상, Sn이 모자라면 None)."""
    c = {k: float(v) for k, v in norm.items()}
    if "-" in axis:
        a, b = axis.split("-", 1)
        va, vb = c.get(a, 0.0), c.get(b, 0.0)
        tot = va + vb
        na = (tot + value) / 2.0
        nb = (tot - value) / 2.0
        if na < 0.0 or nb < 0.0:
            return None
        c[a], c[b] = na, nb
        return c
    cur = c.get(axis, 0.0)
    delta = float(value) - cur
    sn = c.get("Sn", 0.0) - delta
    if value < 0.0 or sn < 0.0:
        return None
    c[axis] = float(value)
    c["Sn"] = sn
    return c


def _axis_value(norm, axis):
    if "-" in axis:
        a, b = axis.split("-", 1)
        return float(norm.get(a, 0) or 0.0) - float(norm.get(b, 0) or 0.0)
    return float(norm.get(axis, 0) or 0.0)


def _l2_family_parts(norm, family):
    """
    L2 계열 구성: [(계열, 가중, L2결과 또는 None)]. 보통은 [(family, 1.0, L2)] 한 개.
    분류 경계 폭 안에서는 경계 양쪽 계열 두 개(가중 합 1). 두 번째 값은 완충 메타(없으면 None).
    하류의 계열별 가중(L2·L3·L4)도 이 가중으로 섞어야 경계에서 연속이 된다.
    """
    for axis, thr, half in _L2_CORRIDORS:
        if "-" in axis:
            a, b = axis.split("-", 1)
            if float(norm.get(a, 0) or 0) <= 0 or float(norm.get(b, 0) or 0) <= 0:
                continue
        x = _axis_value(norm, axis)
        if abs(x - thr) >= half:
            continue
        lo_c = _shift_axis(norm, axis, thr - half)
        hi_c = _shift_axis(norm, axis, thr + half)
        if lo_c is None or hi_c is None:
            continue
        fam_lo, fam_hi = _classify(lo_c), _classify(hi_c)
        if fam_lo == fam_hi:
            continue
        w = _smoothstep01((x - (thr - half)) / (2.0 * half))
        parts = [
            (fam_lo, 1.0 - w, _phase_diagram_predict(norm, fam_lo)),
            (fam_hi, w, _phase_diagram_predict(norm, fam_hi)),
        ]
        meta = {"axis": axis, "families": [fam_lo, fam_hi], "weight_hi": round(w, 4)}
        return [p for p in parts if p[1] > 0.0], meta
    return [(family, 1.0, _phase_diagram_predict(norm, family))], None


def _phase_diagram_predict_smooth(norm, family):
    """
    _phase_diagram_predict + 분류 경계 완충(값만).
    반환: (sol, liq, conf, blend_meta 또는 None). L2가 없으면 (None, None, 0.0, meta).
    한쪽 계열에 L2가 없으면(other) 신뢰도는 가중만큼 줄이고 값은 있는 쪽을 쓴다.
    """
    parts, meta = _l2_family_parts(norm, family)
    have = [(wt, r) for _f, wt, r in parts if r is not None]
    wsum = sum(wt for wt, _r in have)
    if wsum <= 1e-12:
        return None, None, 0.0, meta
    sol = sum(float(r[0]) * wt for wt, r in have) / wsum
    liq = sum(float(r[1]) * wt for wt, r in have) / wsum
    conf = sum(float(r[2]) * wt for wt, r in have)
    return sol, liq, conf, meta


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


def _anchor_binary_eutectic_mixtures(norm, family, sol, liq):
    """
    Sn-Cu / Sn-Zn / Sn-Sb 공정부 근처에서 L1 DB 이웃·KNN 혼합으로 생기는
    고상·액상 과대 보정을 완화(ASM 공정점에 맞춤).
    """
    try:
        cu = float(norm.get("Cu", 0) or 0.0)
        zn = float(norm.get("Zn", 0) or 0.0)
        sb = float(norm.get("Sb", 0) or 0.0)
        inp = float(norm.get("In", 0) or 0.0)
    except (TypeError, ValueError):
        return float(sol), float(liq)
    s = float(sol)
    l = float(liq)
    # [2026-09-25] 창 끝에서 가중이 0이 되기 전에 조건이 끊겨 0.01%에 최대 2.8℃ 튀던 것을 수정
    # (페이드아웃이 끝나는 지점까지 창을 넓힘). 또 다른 용질이 있으면 이원 공정점 앵커를 약화해,
    # 미량 원소로 계열이 바뀌어도 앵커가 갑자기 켜지거나 꺼지지 않게 한다.
    if family == "SnCu" and 0.63 <= cu <= 0.84:
        w = _smoothstep01((cu - 0.63) / 0.12) * (1.0 - _smoothstep01((cu - 0.78) / 0.06))
        w *= 1.0 - _smoothstep01(sb / 1.0)
        tgt = 227.0
        bs = 0.50 * w
        bl = (0.70 + 0.27 * w) * _smoothstep01((cu - 0.63) / 0.12) * (1.0 - _smoothstep01((cu - 0.78) / 0.06))
        bl *= 1.0 - _smoothstep01(sb / 1.0)
        s = s * (1.0 - bs) + tgt * bs
        l = l * (1.0 - bl) + tgt * bl
    elif family == "SnZn" and 8.2 <= zn <= 10.05:
        w = _smoothstep01((zn - 8.2) / 0.35) * (1.0 - _smoothstep01((zn - 9.8) / 0.25))
        w *= 1.0 - _smoothstep01(inp / 1.0)
        ts, tl = 198.5, 198.5
        b = 0.52 * w
        s = s * (1.0 - b) + ts * b
        l = l * (1.0 - b) + tl * b
    elif family in ("SnSb", "SnCu") and 8.8 <= sb <= 11.55:
        w = _smoothstep01((sb - 8.8) / 0.45) * (1.0 - _smoothstep01((sb - 11.2) / 0.35))
        w *= 1.0 - _smoothstep01(cu / 0.3)
        ts, tl = 240.0, 246.0
        b = 0.93 * w
        s = s * (1.0 - b) + ts * b
        l = l * (1.0 - b) + tl * b
    return s, l


# solder_db 행과의 composition_distance 가 이 값 이하면 **DB 직접 일치**로 본다.
# (부동소수점·정규화 잔차 허용) → L2/L3/L4·plateau·물리 보정 없이 DB 고상/액상 그대로 사용.
DB_EXACT_MATCH_EPS = 1e-4


def _pct(norm, key):
    try:
        return float(norm.get(key, 0) or 0.0)
    except Exception:
        return 0.0


# analyzer.AlloyAnalyzer.KNOWN_CORE_ELEMENTS 와 동기화(Au·Ga 등 주기표 금속은 미지 원소로 집계).
KNOWN_CORE_ELEMENTS = frozenset({"Sn", "Ag", "Cu", "Bi", "In", "Sb", "Ni", "Zn", "Pb"})


def _unknown_noncore_total_pct(norm):
    """핵심 솔더 원소 외 wt% 합계(Au, Ge, Ga 등 — 모델·실측 앵커 대상 아님)."""
    if not isinstance(norm, dict):
        return 0.0
    total = 0.0
    for k, v in norm.items():
        if k in KNOWN_CORE_ELEMENTS:
            continue
        try:
            fv = float(v or 0.0)
        except Exception:
            fv = 0.0
        if fv > 0.0:
            total += fv
    return float(total)


def _norm_core_scaled(norm):
    """
    미지 금속을 제외한 KNOWN_CORE 성분만 남겨 100wt%로 재규격화.
    Au 등으로 Sn이 희석된 입력에서도 DB·상태도 기준점이 '솔더 매트릭스'를 가리키도록 함.
    """
    if not isinstance(norm, dict):
        return {}
    core = {}
    for k in KNOWN_CORE_ELEMENTS:
        if k not in norm:
            continue
        try:
            v = float(norm[k] or 0.0)
        except Exception:
            v = 0.0
        if v > 0.0:
            core[k] = v
    s = sum(core.values())
    if s <= 1e-12:
        return {}
    return {k: (v / s) * 100.0 for k, v in core.items()}


def _composition_distance_import():
    try:
        from .utils import composition_distance
    except ImportError:
        from test7.utils import composition_distance
    return composition_distance


def _unknown_blend_baseline_sol_liq(norm, db_prepared, family):
    """
    미지 금속 보수 블렌드가 당길 목표 (solidus, liquidus).

    우선순위 — 사용자 BD(실측 DB) 우선, 다음으로 계열 상태도:
      1) core 재규격화 조성과 가장 가까운 DB 행의 고상·액상 (실측값)
      2) 동일 family의 상태도(L2) 예측 — 핵심 조성 기준
      3) CALPHAD 근사 (L2 없는 other 등)

    Returns
    -------
    (solidus, liquidus, meta_dict)
    """
    meta = {}
    core = _norm_core_scaled(norm)
    query = core if core else norm

    cdist = _composition_distance_import()
    if db_prepared:
        bd = 9999.0
        best = None
        for item in db_prepared:
            d = cdist(query, item["comp"])
            if d < bd:
                bd, best = d, item
        if best is not None:
            meta["baseline_source"] = "db_core_neighbor"
            meta["db_neighbor_dist_core"] = round(bd, 4)
            meta["db_neighbor_name"] = best["name"]
            return float(best["solidus"]), float(best["liquidus"]), meta

    norm_ph = core if core else norm
    ph = _phase_diagram_predict(norm_ph, family)
    if ph is not None and ph[0] is not None:
        meta["baseline_source"] = "phase_diagram_family"
        meta["phase_confidence"] = round(float(ph[2]), 4)
        return float(ph[0]), float(ph[1]), meta

    ca = _calphad_approx(norm_ph, family)
    meta["baseline_source"] = "calphad_approx_fallback"
    return float(ca[0]), float(ca[1]), meta


def _min_db_distance_core(norm, db_prepared):
    """미지 금속 블렌드 β 계산용 — 핵심 조성 기준 최근접 DB 거리."""
    if not db_prepared:
        return None
    cq = _norm_core_scaled(norm)
    q = cq if cq else norm
    cdist = _composition_distance_import()
    return min(cdist(q, item["comp"]) for item in db_prepared)


def _knn_reference_temperatures(
    l2_sol: Optional[float],
    l2_liq: Optional[float],
    knn_raw: List[Tuple[float, Any]],
) -> Tuple[Optional[float], Optional[float]]:
    """
    KNN 온도 OR-밴드 기준: L2 상태도가 있으면 우선, 없는 축은 조성 최근접 상위 이웃들의
    고상·액상 평균으로 보완해 200℃대 등 목표 융점대에 가까운 다른 DB 계열을 끌어올 수 있게 함.
    """
    rs = float(l2_sol) if l2_sol is not None else None
    rl = float(l2_liq) if l2_liq is not None else None
    if not knn_raw:
        return rs, rl
    n = min(6, len(knn_raw))
    avg_s = sum(float(x[1]["solidus"]) for x in knn_raw[:n]) / float(n)
    avg_l = sum(float(x[1]["liquidus"]) for x in knn_raw[:n]) / float(n)
    if rs is None:
        rs = avg_s
    if rl is None:
        rl = avg_l
    return rs, rl


def _knn_pool_with_temp_or_band(
    norm: Dict[str, Any],
    db_prepared: List[Any],
    knn_raw: List[Tuple[float, Any]],
    ref_sol: Optional[float],
    ref_liq: Optional[float],
) -> Tuple[List[Tuple[float, Any]], Dict[str, Any]]:
    """
    L3용 이웃: 조성 거리 상위 + ref 고상/액상 ±밴드에서 **한 축만** 맞아도(OR) 추가.
    정렬은 조성 거리에서 온도 정렬 보너스를 빼 스코어가 낮을수록 우선.
    """
    from .utils import composition_distance as cdist

    meta: Dict[str, Any] = {"knn_temp_band_c": None, "knn_temp_pool_extra": 0, "knn_pool_names": []}
    if not knn_raw:
        return [], meta
    try:
        temp_band = float(os.getenv("MELTING_KNN_TEMP_BAND_C", "28") or "28")
    except Exception:
        temp_band = 28.0
    try:
        max_extra = int(os.getenv("MELTING_KNN_TEMP_EXTRA_MAX", "16") or "16")
    except Exception:
        max_extra = 16
    meta["knn_temp_band_c"] = round(temp_band, 2)

    pool: Dict[str, Tuple[float, Any]] = {}
    for d, item in knn_raw[:7]:
        pool[str(item.get("name", ""))] = (float(d), item)

    extra = 0
    for item in db_prepared:
        if extra >= max_extra:
            break
        nm = str(item.get("name", ""))
        if nm in pool:
            continue
        try:
            s = float(item["solidus"])
            l = float(item["liquidus"])
        except Exception:
            continue
        d_t = float("inf")
        if ref_sol is not None:
            d_t = min(d_t, abs(s - ref_sol))
        if ref_liq is not None:
            d_t = min(d_t, abs(l - ref_liq))
        if d_t <= temp_band:
            pool[nm] = (float(cdist(norm, item["comp"])), item)
            extra += 1
    meta["knn_temp_pool_extra"] = extra

    scored: List[Tuple[float, float, Any]] = []
    for d_comp, item in pool.values():
        try:
            s = float(item["solidus"])
            l = float(item["liquidus"])
        except Exception:
            continue
        d_t = float("inf")
        if ref_sol is not None:
            d_t = min(d_t, abs(s - ref_sol))
        if ref_liq is not None:
            d_t = min(d_t, abs(l - ref_liq))
        align = 0.0
        if d_t < float("inf") and temp_band > 1e-9:
            align = max(0.0, (temp_band - min(d_t, temp_band)) / temp_band) * 7.5
        scored.append((float(d_comp) - align, float(d_comp), item))
    scored.sort(key=lambda x: x[0])
    limit = 6
    out = [(dc, it) for _, dc, it in scored[:limit]]
    if not out:
        out = [(d, it) for d, it in knn_raw[:5]]
    meta["knn_pool_names"] = [str(x[1].get("name", "")) for x in out]
    return out, meta


def _near_pct(val, target, tol):
    """실측 앵커용 — 표시 wt% 라운딩 차이 허용."""
    try:
        return abs(float(val) - float(target)) <= tol
    except Exception:
        return False


def _measured_anchor_sn88_ag35_cu05_in8(norm):
    """
    실측 정합 앵커.

    사용자 제공 조성 Sn88 Ag3.5 Cu0.5 In8(wt%) 고상선 198℃, 액상선 210℃.
    `_classify` 상 Cu>0 이면서 In>0 인 SAC 분기(`/ inp==0`)에 안 들어가 `other`로 떨어져
    앙상블값이 실측과 어긋나는 경우가 있어, 실측 고정값으로 맞춘다.

    미지 금속(Au 등) 첨가 시에는 적용하지 않음 — 오류처럼 보이는 고정 온도 출력 방지.
    """
    if not norm or not isinstance(norm, dict):
        return None

    if _unknown_noncore_total_pct(norm) > 1e-12:
        return None

    junk = ("Bi", "Pb", "Sb", "Zn", "Ni")
    if any(_pct(norm, k) > 0.06 for k in junk):
        return None

    sn = _pct(norm, "Sn")
    ag = _pct(norm, "Ag")
    cu = _pct(norm, "Cu")
    inp = _pct(norm, "In")

    core_sum = sn + ag + cu + inp
    if core_sum < 99.2 or core_sum > 100.8:
        return None

    if not (_near_pct(sn, 88.0, 0.45) and _near_pct(ag, 3.5, 0.22) and _near_pct(cu, 0.5, 0.18) and _near_pct(inp, 8.0, 0.35)):
        return None

    others = sum(_pct(norm, k) for k in norm.keys() if k not in ("Sn", "Ag", "Cu", "In"))
    if others > 0.12:
        return None

    return {
        "label": "Sn88Ag3.5Cu0.5In8",
        "solidus": 198.0,
        "liquidus": 210.0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 외부 CALPHAD / 미니 서버 게이트 (선택)
# ─────────────────────────────────────────────────────────────────────────────
def _external_calphad_http(norm):
    """
    환경변수 MELTING_CALPHAD_URL 이 설정된 경우에만 호출.

    Request : POST JSON { "comp": { "Sn": 96.5, "Ag": 3.5, ... } }  (wt%)
    Response: JSON { "solidus": float, "liquidus": float, "confidence"?: float 0~1 }

    실패·타임아웃 시 None (기존 L4 근사만 사용).
    """
    url = (os.getenv("MELTING_CALPHAD_URL") or "").strip()
    if not url:
        return None
    try:
        import json as _json
        import urllib.request

        timeout = float(os.getenv("MELTING_CALPHAD_TIMEOUT", "4") or "4")
        payload = _json.dumps({"comp": norm}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        j = _json.loads(body)
        if not isinstance(j, dict):
            return None
        sol = float(j["solidus"])
        liq = float(j["liquidus"])
        if not (math.isfinite(sol) and math.isfinite(liq)):
            return None
        raw_c = j.get("confidence", j.get("conf", 0.85))
        conf = float(raw_c) if raw_c is not None else 0.85
        if not math.isfinite(conf):
            return None
        conf = max(0.05, min(1.0, conf))
        return sol, liq, conf
    except Exception:
        return None


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

    Notes
    -----
    DB 행과 조성이 **정확히 일치**하면(`db_exact_match`) 해당 행의 고상·액상이 곧
    출력 기준(실측 DB 우선). 그 외 조성만 앙상블·앵커·블렌드가 적용된다.
    """
    from .utils import composition_distance

    unk_pct_global = _unknown_noncore_total_pct(norm)
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

    db_exact_match = best_item is not None and best_dist <= DB_EXACT_MATCH_EPS
    ext_calphad_detail = None
    l2_blend_meta = None
    knn_augment_meta: Optional[Dict[str, Any]] = None
    knn_ref_sol: Optional[float] = None
    knn_ref_liq: Optional[float] = None

    if db_exact_match:
        # DB 직접 일치: 모델(L2/L3/L4)·plateau·물리 보정·AI를 섞지 않음
        final_sol = float(best_item["solidus"])
        final_liq = float(best_item["liquidus"])
        layers = [(final_sol, final_liq, 1.0, "L1:DB_exact")]
        l6_delta_sol, l6_delta_liq = 0.0, 0.0
        l6_applied = False
        snbi_plateau_detail = {
            "applied": False,
            "reason": "db_exact_match",
            "best_dist": round(best_dist, 6),
            "eps": DB_EXACT_MATCH_EPS,
        }

    else:
        prof = get_ensemble_profile(family)
        # L1: 최근접 DB 행 — _db_neighbor_gate 로 거리에 따라 0~1 부드럽게 섞어 L2/L3와 앙상블
        l1_sol, l1_liq, l1_w = None, None, 0.0
        if best_item is not None:
            l1_sol = float(best_item["solidus"])
            l1_liq = float(best_item["liquidus"])
            gate = _db_neighbor_gate(best_dist)
            l1_w = math.exp(-best_dist * 6.0) * (4.0 + 22.0 * gate)
            # 성분 거리가 커도 최근접 solder_db 융점을 0으로 만들면 other+L4만 남는 경우가 있음 —
            # Sn 매트릭스 핵심 조성에서는 완만한 바닥 가중으로 닻을 유지.
            if (
                unk_pct_global <= 1e-9
                and _pct(norm, "Sn") >= 45.0
                and float(best_dist) < 42.0
            ):
                l1_w = max(l1_w, 0.18 / (1.0 + float(best_dist) * 0.11))

        # ─── L2: 상태도 보간 ─────────────────────────────────────────────────
        l2_sol, l2_liq, l2_conf, l2_blend_meta = _phase_diagram_predict_smooth(norm, family)
        # 계열 구성(보통 1개, 분류 경계 폭 안에서는 2개) — 아래 계열별 가중을 이 비율로 섞는다.
        l2_parts, _ = _l2_family_parts(norm, family)

        def _is_simple(fam):
            return fam in ("SnBi", "SnIn", "SnPb", "SAC", "SAC_BI_TRANSITION", "SnAg",
                           "SnCu", "SnSb", "SnZn")

        is_simple = _is_simple(family)
        l2_w = 0.0
        for _fam, _wt, _r in l2_parts:
            if _r is not None:
                l2_w += _wt * float(_r[2]) * (
                    float(prof["l2_simple_mult"]) if _is_simple(_fam) else float(prof["l2_other_mult"])
                )
        snbi_frac = sum(_wt for _fam, _wt, _r in l2_parts if _fam == "SnBi")

        ref_sol, ref_liq = _knn_reference_temperatures(l2_sol, l2_liq, knn_raw)
        knn5, knn_augment_meta = _knn_pool_with_temp_or_band(
            norm, db_prepared, knn_raw, ref_sol, ref_liq
        )
        knn_ref_sol, knn_ref_liq = ref_sol, ref_liq

        # ─── L3: KNN 가중 보간 ───────────────────────────────────────────────
        if knn5:
            try:
                tw = float(os.getenv("MELTING_KNN_TEMP_WEIGHT", "1.35") or "1.35")
            except Exception:
                tw = 1.35
            band = float((knn_augment_meta or {}).get("knn_temp_band_c") or 28.0)

            def _l3_w(d_comp: float, item: Any) -> float:
                d_t = float("inf")
                if ref_sol is not None:
                    d_t = min(d_t, abs(float(item["solidus"]) - ref_sol))
                if ref_liq is not None:
                    d_t = min(d_t, abs(float(item["liquidus"]) - ref_liq))
                boost = 1.0
                if d_t < float("inf") and band > 1e-9:
                    boost = 1.0 + tw * max(0.0, (band - min(d_t, band)) / band)
                return (1.0 / (d_comp + 1e-6)) * boost

            w_total = sum(_l3_w(d, it) for d, it in knn5)
            l3_sol = sum(float(it["solidus"]) * _l3_w(d, it) for d, it in knn5) / w_total
            l3_liq = sum(float(it["liquidus"]) * _l3_w(d, it) for d, it in knn5) / w_total
            knn_d0 = float(knn5[0][0])
            try:
                knn_decay = float(os.getenv("MELTING_KNN_D0_DECAY", "0.38") or "0.38")
            except Exception:
                knn_decay = 0.38
            l3_conf = math.exp(-knn_d0 * knn_decay)
            if knn_d0 > 3.0:
                l3_conf = max(
                    l3_conf, 0.07 + 0.31 * math.exp(-(knn_d0 - 3.0) * 0.11)
                )
            # 이원계+L2가 있을 때 KNN(L3) 비중이 크면 공정부 근처에서 액상선이 과대(예: Sn-Cu 227→231)
            l3_mult = 0.0
            for _fam, _wt, _r in l2_parts:
                l3_mult += _wt * (
                    float(prof["l3_knn_with_l2_simple"])
                    if _is_simple(_fam) and _r is not None
                    else float(prof["l3_knn_default"])
                )
            l3_w = l3_conf * l3_mult
            # Sn-Bi 계열: DB 이웃이 멀면(KNN 거리↑) 성분이 달라 이웃 고상·액상이 왜곡되기 쉬움 → L3 추가 억제.
            if snbi_frac > 0.0:
                d0 = float(knn5[0][0])
                if d0 > 5.5:
                    l3_w *= (1.0 - snbi_frac) + snbi_frac * math.exp(-(d0 - 5.5) * 0.11)
        else:
            l3_sol, l3_liq, l3_w = 217.0, 221.0, 0.1

        # Sn-Bi(-Ag-Cu-In): DB에 서로 비슷한 거리의 행이 여럿일 때 L1(최근접 1행)만으로 수렴하는 현상 완화.
        # (l3_knn_with_l2_simple 기본값이 매우 작아 L3가 사실상 무시되기 쉬움 → 근접 2번째 이웃이 있으면 KNN 비중 상향)
        if best_item is not None and snbi_frac > 0.0 and knn5 and len(knn5) >= 2:
            d0 = float(knn5[0][0])
            d1 = float(knn5[1][0])
            if d0 > 1e-9 and d0 < 4.5 and d1 <= d0 * 1.55:
                tight = max(0.0, min(1.0, (1.55 - d1 / d0) / 0.55)) * snbi_frac
                l1_w *= 1.0 - 0.35 * tight
                l3_w *= 1.0 + 2.0 * tight
                l3_w = min(l3_w, float(prof["l3_knn_default"]) * 2.3)

        # ─── L4: CALPHAD ───────────────────────────────────────────────────────
        l4_sol, l4_liq, l4_conf = _calphad_approx(norm, family)
        # 상태도(L2)가 있으면 CALPHAD는 보조만. SnBi(신뢰도 0.92)는 Bi 공정 인력 합산이 과추정되기 쉬워 제외.
        # [2026-09-25] 이전 `l2_conf > 0.85`·`family == "SnBi"` 하드 조건은 분류 경계에서 L4를
        # 켰다 껐다 해 점프를 만들었다. 계열 구성별로 신뢰도 0.85→0.90에서 서서히 끄고 섞는다.
        # (완충 구간 밖의 단일 계열은 기존과 동일: 신뢰도 0.82·0.85 → 켜짐, 0.90·0.92 → 꺼짐)
        l4_mult = 0.0
        for _fam, _wt, _r in l2_parts:
            if _r is not None:
                fade = 1.0 - _smoothstep01((float(_r[2]) - 0.85) / 0.05)
                l4_mult += _wt * float(prof["l4_if_l2_weak_mult"]) * fade
            else:
                m = float(prof["l4_if_no_l2_mult"])
                if _fam == "other" and best_item is not None:
                    bd = float(best_dist)
                    m *= min(1.0, 2.6 / (1.0 + max(0.0, bd - 2.0) * 0.11))
                l4_mult += _wt * m
        l4_w = l4_conf * l4_mult

        # ─── 앙상블 ───────────────────────────────────────────────────────────
        layers = []
        if l1_sol is not None and l1_w > 1e-6:
            layers.append((l1_sol, l1_liq, l1_w, "L1:DB_neighbor"))
        if l2_sol is not None:
            layers.append((l2_sol, l2_liq, l2_w, "L2:phase_diagram"))
        layers.append((l3_sol, l3_liq, l3_w, "L3:knn"))
        if l4_w > 0:
            layers.append((l4_sol, l4_liq, l4_w, "L4:calphad"))

        ext = _external_calphad_http(norm)
        if ext is not None:
            es, el, ec = ext
            ew = float(prof.get("l4_external_weight", 0.0))
            if ew > 1e-12:
                layers.append((es, el, ew * ec, "L4e:ext_calphad"))
                ext_calphad_detail = {"applied": True, "weight": round(ew * ec, 4)}

        total_w = sum(w for _, _, w, _ in layers)
        if total_w == 0:
            final_sol, final_liq = 217.0, 221.0
        else:
            final_sol = sum(s * w for s, _, w, _ in layers) / total_w
            final_liq = sum(l * w for _, l, w, _ in layers) / total_w

        final_sol, final_liq = _anchor_binary_eutectic_mixtures(norm, family, final_sol, final_liq)

        # ─── L6: AI 델타 보정 ────────────────────────────────────────────────
        l6_delta_sol, l6_delta_liq = 0.0, 0.0
        l6_applied = False
        # 미지 원소 첨가 시 화학계 미포함 → AI 델타가 오히려 오차를 키울 수 있음
        if ai_engine is not None and best_dist > 3.0 and family == "other" and unk_pct_global <= 1e-12:
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

        # ─── Physics-informed: Sn–Bi 고상선 절벽/과대상승 완화 ───
        final_sol = _physics_sn_bi_rich_solidus(norm, family, final_sol)
        if family == "SAC_BI_TRANSITION":
            # The SnBi low-Cu plateau engages at 20 wt% Bi.  Match that
            # endpoint continuously so the final 20.00→20.01% step does not
            # reintroduce a classifier-layer jump after the phase blend.
            try:
                bi_value = float(norm.get("Bi") or 0.0)
                cu_value = float(norm.get("Cu") or 0.0)
            except (TypeError, ValueError):
                bi_value, cu_value = 0.0, 999.0
            if 19.0 <= bi_value <= 20.0 and cu_value <= 0.8:
                endpoint_weight = _smoothstep01(bi_value - 19.0)
                final_sol = final_sol * (1.0 - endpoint_weight) + 138.3 * endpoint_weight
        final_sol, snbi_plateau_detail = _snbi_highbi_lowcu_plateau(norm, family, final_sol)

    # db_exact_match 이면 위 블록에서 이미 최종값 확정 (물리/ plateau 미적용)

    layers_snapshot = list(layers)

    measured_anchor_detail = None
    # DB 직접 일치는 실측 DB가 기준 — 문서/특수 앵커로 덮어쓰지 않음.
    ma = None if db_exact_match else _measured_anchor_sn88_ag35_cu05_in8(norm)
    if ma:
        final_sol = float(ma["solidus"])
        final_liq = float(ma["liquidus"])
        measured_anchor_detail = ma
        layers = [(final_sol, final_liq, 1.0, "Lx:measured_anchor")]

    unknown_blend_detail = None
    # 미지 원소가 극미량이라도 모델 화학계 밖 → 고신뢰 숫자처럼 보이지 않게 약하게 당김.
    # 기준점(bs, bl): BD 실측(DB 이웃, 핵심 성분 재규격화) → 계열 상태도(L2) → CALPHAD.
    if (measured_anchor_detail is None and unk_pct_global >= 0.05 and not db_exact_match):
        bs, bl, blend_meta = _unknown_blend_baseline_sol_liq(norm, db_prepared, family)
        t = min(1.0, unk_pct_global / 7.0)
        bd_core = _min_db_distance_core(norm, db_prepared)
        bd_for_beta = float(best_dist) if bd_core is None else float(bd_core)
        d = min(1.0, bd_for_beta / 30.0)
        beta = min(0.58, 0.1 + 0.36 * t + 0.24 * t * d)
        final_sol = final_sol * (1.0 - beta) + bs * beta
        final_liq = final_liq * (1.0 - beta) + bl * beta
        unknown_blend_detail = {
            "applied": True,
            "beta": round(beta, 4),
            "baseline_sol_liq": (round(bs, 2), round(bl, 2)),
            "reason": "unknown_noncore_metals",
            **blend_meta,
        }

    # ─── 물리 제약 ───────────────────────────────────────────────────────────
    if final_liq < final_sol:
        final_liq = final_sol + 1.0
    if not db_exact_match:
        final_sol = max(50.0, min(420.0, final_sol))
        final_liq = max(50.0, min(520.0, final_liq))

    # ─── 피크 온도 (IPC-J-STD-020E 권역과 정합되도록 오프셋; JIS 조립·시험은 TM-650·Z3198 등과 병행 검토) ──
    delta_t     = final_liq - final_sol
    peak_offset = 20.0 if delta_t < 5 else 25.0
    final_peak  = final_liq + peak_offset

    prediction_uncertainty = _prediction_uncertainty(
        norm,
        family,
        best_dist,
        unk_pct_global,
        layers_snapshot,
        db_exact_match,
        measured_anchor_detail,
    )

    detail = {
        "family":    family,
        "engine_version": MELTING_ENGINE_VERSION,
        "prediction_uncertainty": prediction_uncertainty,
        "layers":    [(name, round(s,2), round(l,2), round(w,3))
                      for s, l, w, name in layers],
        "best_dist": round(best_dist, 3),
        "best_name": best_item["name"] if best_item else "N/A",
        "l6_applied": l6_applied,
        "l6_delta":  (round(l6_delta_sol,2), round(l6_delta_liq,2)),
        "forced_db": bool(db_exact_match),
        "db_exact_match": bool(db_exact_match),
        "db_exact_match_eps": DB_EXACT_MATCH_EPS,
        "db_neighbor_gate": round(_db_neighbor_gate(best_dist), 4) if best_item else 0.0,
    }
    if knn_augment_meta is not None:
        detail["knn_temp_or_augment"] = {
            **knn_augment_meta,
            "ref_solidus_c": knn_ref_sol,
            "ref_liquidus_c": knn_ref_liq,
        }
    if snbi_plateau_detail:
        detail["snbi_cu_plateau_anchor"] = snbi_plateau_detail
    if measured_anchor_detail:
        detail["measured_anchor"] = measured_anchor_detail
    if unk_pct_global > 1e-12:
        detail["unknown_noncore_pct"] = round(unk_pct_global, 4)
    if unknown_blend_detail:
        detail["unknown_metals_melting_blend"] = unknown_blend_detail
    if l2_blend_meta:
        detail["l2_family_corridor"] = l2_blend_meta
    if ext_calphad_detail:
        detail["external_calphad"] = ext_calphad_detail

    return round(final_sol, 1), round(final_liq, 1), round(final_peak, 1), detail
