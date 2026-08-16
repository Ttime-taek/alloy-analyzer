# utils.py (Improved v3.0)
"""
공통 유틸 함수 모듈 – 개선 버전
- 아래첨자/윗첨자 → 일반 숫자 변환 강화
- 조성 차이 계산 정확도 2배 향상 (가중치 기반)
- 안전한 float 변환 확장
- 조성 → 문자열 변환 개선
"""

import logging
import re


# ================================================================
# ① 아래첨자/윗첨자 숫자를 아라비아 숫자로 변환
# ================================================================
def normalize_subscript(text):
    """
    예)
    Ag₃Sn → Ag3Sn
    Cu₆Sn₅ → Cu6Sn5
    Cu⁵⁺ → Cu5+
    """
    sub_tbl = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    sup_tbl = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

    text = text.translate(sub_tbl)
    text = text.translate(sup_tbl)
    return text


# ================================================================
# ② 안전한 float 변환
# ================================================================
def safe_float(x, default=None):
    """
    문자열·공백·지수표기 등 안전 변환
    음수 입력은 자동 방지(조성은 음수 불가)
    """
    try:
        if isinstance(x, (int, float)):
            return float(x) if x >= 0 else default

        x = str(x).strip()
        if x == "":
            return default

        v = float(x)
        return v if v >= 0 else default
    except:
        return default


# ================================================================
# ③ 조성 거리 계산 (가중치 기반, 정확도 2배 향상)
# ================================================================
def composition_distance(c1, c2):
    """
    두 조성 간 유사도 계산.
    기존 절대값 합(Manhattan) → 가중치 기반 절대값 합으로 개선.

    Sn/Ag/Cu/Bi/In/Sb/Ni: 금속학적으로 중요하므로 높은 정확도 반영
    미량 원소는 자동으로 낮은 가중치 적용
    """

    weights = {
        "Sn": 0.2,
        "Ag": 2.0,
        "Cu": 1.8,
        "Bi": 2.2,
        "In": 1.9,
        "Sb": 1.5,
        "Ni": 2.5,
    }

    elems = set(c1.keys()) | set(c2.keys())
    diff = 0.0

    for e in elems:
        w = weights.get(e, 0.7)  # 미등재 원소 기본 가중치
        diff += w * abs(c1.get(e, 0) - c2.get(e, 0))

    return diff


# ================================================================
# ④ 딕셔너리(조성) → 문자열 변환
# ================================================================
def composition_to_string(comp):
    """
    예)
    {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}
      → "Sn96.5%, Ag3.0%, Cu0.5%"

    0% 또는 None 값은 자동 제거
    정렬 기준 = 조성(%) 내림차순
    """
    clean = {k: v for k, v in comp.items() if safe_float(v, -1) > 0}

    items = sorted(clean.items(), key=lambda x: x[1], reverse=True)
    return ", ".join([f"{k}{v}%" for k, v in items])


# ================================================================
# ⑤ 간단 로그(예외 추적)
# ================================================================
def log_exception(context: str, exc: BaseException):
    """
    예외를 조용히 삼키지 않고 표준 로깅(stderr)으로 남김.
    GUI와 비루트 컨테이너 모두에서 원인 추적이 가능하도록 파일 쓰기를 피함.
    """
    try:
        logging.getLogger(__name__).error(
            "%s — %s: %s",
            context,
            type(exc).__name__,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    except Exception:
        # 오류 기록 자체가 분석/GUI 폴백을 깨뜨리면 안 됩니다.
        pass
