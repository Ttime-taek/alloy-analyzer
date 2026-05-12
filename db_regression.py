# db_regression.py (Fixed v2.3)
# parse_alloy: 하이픈 표기 + solder_db 연속 BD명(Sn3.0Ag0.5Cu, Sn63Pb37, Sn0.7Cu 등)

from .SOLDER_PROPERTIES_DB import SOLDER_PROPERTIES_DB
from .utils import composition_distance
import re
import statistics


# ------------------------------------------------
# ① 합금 문자열 → 조성 dict 변환 (완전 수정)
# ------------------------------------------------
_ELEM_ALT = r"(?:Pb|Sn|Ag|Cu|Bi|In|Sb|Zn|Ni|Ge)"


def parse_alloy(alloy_str):
    """
    지원 형식:
      - 'Sn-3.0Ag-0.5Cu' (하이픈 표기, wt% 합 ~100)
      - 'Sn3.0Ag0.5Cu', 'Sn0.7Cu', 'Sn63Pb37', 'Sn57.6Bi0.4Ag' (solder_db.py 연속 BD명)
      - 'Sn-4.0Ag-0.5Cu-2.5Bi+α' (+ 접미 제거 후 하이픈 파싱)
    """
    alloy_str = re.sub(r"\+.*$", "", alloy_str).strip()

    comp: dict = {}
    total = 0.0

    if "-" in alloy_str:
        tokens = alloy_str.split("-")
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            m = re.match(r"^([0-9]+(?:\.[0-9]+)?)([A-Z][a-z]?)$", token)
            if m:
                v = float(m.group(1))
                elem = m.group(2)
                comp[elem] = v
                total += v
                continue
            m2 = re.match(r"^([A-Z][a-z]?)([0-9]*(?:\.[0-9]+)?)$", token)
            if m2:
                elem = m2.group(1)
                val_str = m2.group(2)
                if val_str:
                    v = float(val_str)
                    comp[elem] = v
                    total += v
        if "Sn" not in comp:
            sn_val = max(0.0, 100.0 - total)
            if sn_val > 0:
                comp["Sn"] = round(sn_val, 4)
        return comp

    # ── 연속 BD명 (하이픈 없음) ─────────────────────────────────────────
    if not alloy_str.startswith("Sn"):
        return comp

    rest = alloy_str[2:]
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", rest):
        return {"Sn": float(rest)}

    # Sn63Pb37 → rest 63Pb37 (Sn wt%, Pb wt%)
    mb = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)Pb([0-9]+(?:\.[0-9]+)?)", rest)
    if mb:
        return {"Sn": float(mb.group(1)), "Pb": float(mb.group(2))}

    # (원소)(wt%) … 합이 ~100이면 그대로 (Sn63Pb37 전체 문자열 등)
    comp_en: dict = {}
    for m in re.finditer(rf"({_ELEM_ALT})([0-9]+(?:\.[0-9]+)?)", alloy_str):
        comp_en[m.group(1)] = float(m.group(2))
    if comp_en and abs(sum(comp_en.values()) - 100.0) < 0.55:
        return comp_en

    # Sn 접두 + (wt%)(원소) … , Sn 잔량 (Sn3.5Ag0.7Cu, Sn0.7Cu, Sn57.6Bi0.4Ag …)
    comp_ne: dict = {}
    tot = 0.0
    r = rest
    pat = re.compile(rf"^([0-9]+(?:\.[0-9]+)?)({_ELEM_ALT})")
    while r:
        m = pat.match(r)
        if not m:
            break
        v, el = float(m.group(1)), m.group(2)
        comp_ne[el] = v
        tot += v
        r = r[m.end() :]
    if comp_ne and tot < 99.99 and "Sn" not in comp_ne:
        comp_ne["Sn"] = round(100.0 - tot, 4)
        return comp_ne

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
