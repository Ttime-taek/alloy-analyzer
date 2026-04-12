# db_regression.py (Fixed v2.2)
# 수정: parse_alloy 하이픈/연속 포맷 모두 완벽 지원

from .SOLDER_PROPERTIES_DB import SOLDER_PROPERTIES_DB
from .utils import composition_distance
import re
import statistics


# ------------------------------------------------
# ① 합금 문자열 → 조성 dict 변환 (완전 수정)
# ------------------------------------------------
def parse_alloy(alloy_str):
    """
    지원 형식:
      - 'Sn-3.0Ag-0.5Cu'       (하이픈 표기: SOLDER_PROPERTIES_DB 기본 포맷)
      - 'Sn3.0Ag0.5Cu'          (연속 표기: solder_db.py 이름 포맷)
      - 'Sn-4.0Ag-0.5Cu-2.5Bi+α' (특수문자 포함)
    """
    # +α 등 특수 접미사 제거
    alloy_str = re.sub(r'\+.*$', '', alloy_str).strip()

    comp = {}
    total = 0.0

    if '-' in alloy_str:
        # ── 하이픈 포맷 처리 ──────────────────────────────────────
        # 'Sn-3.0Ag-0.5Cu' → 토큰 ['Sn', '3.0Ag', '0.5Cu']
        tokens = alloy_str.split('-')
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            # '3.0Ag' 형식 (숫자 먼저)
            m = re.match(r'^([0-9]+(?:\.[0-9]+)?)([A-Z][a-z]?)$', token)
            if m:
                v = float(m.group(1))
                elem = m.group(2)
                comp[elem] = v
                total += v
                continue
            # 'Sn96.5' 또는 'Sn' 형식 (원소 먼저)
            m2 = re.match(r'^([A-Z][a-z]?)([0-9]*(?:\.[0-9]+)?)$', token)
            if m2:
                elem = m2.group(1)
                val_str = m2.group(2)
                if val_str:
                    v = float(val_str)
                    comp[elem] = v
                    total += v
                # 숫자 없으면 잔량 원소 (Sn 단독) → 나중에 처리
    else:
        # ── 연속 표기 처리 ────────────────────────────────────────
        # 'Sn3.0Ag0.5Cu' → [('Sn','3.0'), ('Ag','0.5'), ('Cu','')]
        pattern = r'([A-Z][a-z]?)([0-9]+(?:\.[0-9]+)?)'
        for elem, val_str in re.findall(pattern, alloy_str):
            v = float(val_str)
            comp[elem] = v
            total += v

    # Sn이 없으면 잔량으로 추정
    if 'Sn' not in comp:
        sn_val = max(0.0, 100.0 - total)
        if sn_val > 0:
            comp['Sn'] = round(sn_val, 4)

    return comp


# ------------------------------------------------
# ② 특정 합금의 평균 + 표준편차 계산
# ------------------------------------------------
def get_statistics(alloy_name):
    rows = [r for r in SOLDER_PROPERTIES_DB if r["alloy"] == alloy_name]

    if not rows:
        return None

    result = {}
    props = ["tensile", "yield_strength", "elongation", "shear"]

    for p in props:
        values = [r[p] for r in rows if r[p] is not None]

        if len(values) == 0:
            result[p] = None
        elif len(values) == 1:
            result[p] = {"mean": values[0], "std": 0, "n": 1}
        else:
            result[p] = {
                "mean": statistics.mean(values),
                "std":  statistics.stdev(values),
                "n":    len(values)
            }

    return result


# ------------------------------------------------
# ③ 조성 유사도 기반 가중 예측
# ------------------------------------------------
def predict_from_db(input_comp):
    candidates = []

    for row in SOLDER_PROPERTIES_DB:
        db_comp = parse_alloy(row["alloy"])
        if not db_comp:
            continue
        dist = composition_distance(input_comp, db_comp)
        candidates.append((row["alloy"], dist))

    candidates.sort(key=lambda x: x[1])
    top = candidates[:5]

    predictions = {}
    props = ["tensile", "yield_strength", "elongation", "shear"]

    for p in props:
        weighted_values = []
        weights = []

        for alloy_name, dist in top:
            stats = get_statistics(alloy_name)
            if not stats or not stats[p]:
                continue

            mean = stats[p]["mean"]
            n    = stats[p]["n"]
            weight = (1 / (1 + dist)) * n

            weighted_values.append(mean * weight)
            weights.append(weight)

        predictions[p] = sum(weighted_values) / sum(weights) if weights else None

    return predictions


def predict_from_db_with_detail(input_comp):
    """
    predict_from_db()와 동일한 가중 예측 + 상위 유사 합금 목록(거리).
    analyzer.analyze_all 의 물성 DB 블렌딩·evidence에 사용.
    """
    candidates = []
    for row in SOLDER_PROPERTIES_DB:
        db_comp = parse_alloy(row["alloy"])
        if not db_comp:
            continue
        dist = composition_distance(input_comp, db_comp)
        candidates.append({"alloy": row["alloy"], "dist": float(dist)})
    candidates.sort(key=lambda x: x["dist"])
    top = candidates[:5]
    pred = predict_from_db(input_comp)
    return {"pred": pred or {}, "top": top}
