# db_regression.py (Fixed v2.4)
# parse_alloy: 하이픈 표기 + solder_db 연속 BD명(Sn3.0Ag0.5Cu, Sn63Pb37, Sn0.7Cu 등)

from .SOLDER_PROPERTIES_DB import SOLDER_PROPERTIES_DB
from .solder_properties import rows_for_alloy
from .utils import composition_distance
import math
import re
import statistics

# 전단 IDW: 근접 블렌드 불가 시에도 유사 BD로 추정 (합금족 정렬)
_SHEAR_IDW_MAX_DIST = 12.0
_SHEAR_IDW_DIST_FLOOR = 0.35
_SHEAR_IDW_DIST_POWER = 1.6

# 인장 DB는 합금명별 고유 후보를 유지하되, 먼 후보가 희소 합금족의 값을
# 끌어내리지 않도록 최근접 거리 주변의 국소 이웃만 사용합니다.
_TENSILE_NEIGHBOR_LIMIT = 5
_TENSILE_NEIGHBOR_ABS_MARGIN = 0.25
_TENSILE_NEIGHBOR_REL_FACTOR = 1.20


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
    rows = rows_for_alloy(alloy_name)

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
def _unique_alloy_candidates(input_comp):
    """SOLDER_PROPERTIES_DB 합금별 최소 거리·조성."""
    by_name: dict = {}
    for row in SOLDER_PROPERTIES_DB:
        db_comp = parse_alloy(row["alloy"])
        if not db_comp:
            continue
        dist = float(composition_distance(input_comp, db_comp))
        name = row["alloy"]
        if name not in by_name or dist < by_name[name]["dist"]:
            by_name[name] = {"dist": dist, "comp": db_comp}
    return by_name


def _tensile_neighbor_cutoff(best_dist):
    best = max(0.0, float(best_dist))
    return max(
        best + _TENSILE_NEIGHBOR_ABS_MARGIN,
        best * _TENSILE_NEIGHBOR_REL_FACTOR,
    )


def _select_tensile_candidates(candidates):
    """정렬된 ``(합금명, 거리)``에서 실제 인장 기여 이웃을 선택합니다."""
    ranked = sorted(candidates, key=lambda item: float(item[1]))
    exact = [item for item in ranked if float(item[1]) <= 1e-4]
    if exact:
        return exact[:_TENSILE_NEIGHBOR_LIMIT]
    if not ranked:
        return []
    cutoff = _tensile_neighbor_cutoff(ranked[0][1])
    return [
        item
        for item in ranked[:_TENSILE_NEIGHBOR_LIMIT]
        if float(item[1]) <= cutoff
    ]


def _shear_family_weight(input_comp, db_comp, dist):
    """Bi·Ag 정렬로 SAC vs SAC+Bi 전단 혼입을 줄임."""
    bi_in = float(input_comp.get("Bi", 0) or 0.0)
    bi_db = float(db_comp.get("Bi", 0) or 0.0)
    ag_in = float(input_comp.get("Ag", 0) or 0.0)
    ag_db = float(db_comp.get("Ag", 0) or 0.0)

    w_dist = 1.0 / (float(dist) + _SHEAR_IDW_DIST_FLOOR) ** _SHEAR_IDW_DIST_POWER

    if bi_in >= 0.3:
        if bi_db < 0.3:
            w_family = 0.08
        else:
            w_family = 2.8 * math.exp(-abs(bi_in - bi_db) / 1.8)
            w_family *= math.exp(-abs(ag_in - ag_db) / 2.5)
    else:
        if bi_db >= 1.0:
            w_family = 0.15
        else:
            w_family = 1.0 * math.exp(-abs(ag_in - ag_db) / 3.5)

    return w_dist * w_family


def predict_shear_from_db(input_comp, max_dist=_SHEAR_IDW_MAX_DIST):
    """
    전단 전용 IDW — 합금족(Bi 유무·함량, Ag 근접) 가중.
    근접 물성 DB 블렌드(dist≤3)가 없을 때 표시·비교용.
    """
    by_name = _unique_alloy_candidates(input_comp)
    if not by_name:
        return None

    exact = [
        (name, item)
        for name, item in by_name.items()
        if float(item["dist"]) <= 1e-4
    ]
    if exact:
        weighted_values = []
        weights = []
        for name, item in exact:
            stats = get_statistics(name)
            if not stats or not stats.get("shear"):
                continue
            mean = float(stats["shear"]["mean"])
            n = int(stats["shear"]["n"] or 1)
            w = _shear_family_weight(input_comp, item["comp"], 0.0) * n
            if w <= 0.0:
                continue
            weighted_values.append(mean * w)
            weights.append(w)
        if weights:
            return sum(weighted_values) / sum(weights)

    best_dist = min(v["dist"] for v in by_name.values())
    if best_dist > float(max_dist):
        return None

    weighted_values = []
    weights = []

    for name, item in by_name.items():
        dist = float(item["dist"])
        if dist > float(max_dist):
            continue
        stats = get_statistics(name)
        if not stats or not stats.get("shear"):
            continue
        mean = float(stats["shear"]["mean"])
        n = int(stats["shear"]["n"] or 1)
        w = _shear_family_weight(input_comp, item["comp"], dist) * n
        if w <= 0.0:
            continue
        weighted_values.append(mean * w)
        weights.append(w)

    if not weights:
        return None
    return sum(weighted_values) / sum(weights)


def predict_shear_from_db_with_detail(input_comp, max_dist=_SHEAR_IDW_MAX_DIST, top_k=3):
    """전단 IDW 값 + 상위 기여 합금(근거 표시용)."""
    by_name = _unique_alloy_candidates(input_comp)
    if not by_name:
        return {"value": None, "best_dist": None, "top": []}

    # ``best_dist`` must describe the nearest row that can actually contribute
    # a shear value.  An exact alloy row with ``shear=None`` is not shear
    # evidence and must not make a remote IDW estimate look exact.
    valid_contributors = []
    for name, item in sorted(by_name.items(), key=lambda x: x[1]["dist"]):
        dist = float(item["dist"])
        stats = get_statistics(name)
        if not stats or not stats.get("shear"):
            continue
        mean = float(stats["shear"]["mean"])
        n = int(stats["shear"]["n"] or 1)
        w = _shear_family_weight(input_comp, item["comp"], dist) * n
        if w <= 0.0:
            continue
        valid_contributors.append(
            {
                "alloy": name,
                "dist": dist,
                "shear_mpa": mean,
                "weight": w,
            }
        )

    if not valid_contributors:
        return {"value": None, "best_dist": None, "top": []}

    best_dist = min(c["dist"] for c in valid_contributors)

    # Exact measured shear is authoritative.  Mixing remote rows here made the
    # detailed/evidence value disagree with the main exact-match DB mean.
    exact = [c for c in valid_contributors if c["dist"] <= 1e-4]
    if exact:
        measured = exact[0]
        return {
            "value": float(measured["shear_mpa"]),
            "best_dist": float(measured["dist"]),
            "top": [
                {
                    "alloy": measured["alloy"],
                    "dist": float(measured["dist"]),
                    "shear_mpa": float(measured["shear_mpa"]),
                    "weight_share": 1.0,
                }
            ],
        }

    contributors = [
        c for c in valid_contributors if c["dist"] <= float(max_dist)
    ]
    if not contributors:
        return {"value": None, "best_dist": float(best_dist), "top": []}

    total_w = sum(c["weight"] for c in contributors)
    value = sum(c["shear_mpa"] * c["weight"] for c in contributors) / total_w
    contributors.sort(key=lambda x: x["weight"], reverse=True)
    top = []
    for c in contributors[:top_k]:
        top.append(
            {
                "alloy": c["alloy"],
                "dist": c["dist"],
                "shear_mpa": c["shear_mpa"],
                "weight_share": float(c["weight"] / total_w) if total_w > 0 else 0.0,
            }
        )
    return {"value": float(value), "best_dist": float(best_dist), "top": top}


# [2026-09-30 계산 로직 2차 점검 P1] 물성 DB 보간 커널.
# 이전: 정확일치면 그 합금 평균만, 0.0001만 벗어나도 가까운 5개를 1/(1+거리)로 섞어
#   (먼 합금까지 크게 반영) 값이 튀었다 — 순수 Sn 연신 45 → Ni 0.01 % 첨가 34.4 %,
#   SAC305 항복 39.5 → Ag +0.01 %에 36.9. 인장은 별도 컷오프로 이웃이 들고 날 때 계단.
# 이제: 가중 = 시험 수 / (거리 + ε)², 최근접 거리 d0에서 폭 max(1, 0.5·d0) 안에서만
#   매끈하게 0까지 줄임. 거리 → 0이면 그 합금 값으로 연속 수렴한다.
#   합금별 leave-one-out(DB 단독 예측) MAE: 인장 8.4 → 7.9, 항복 10.1 → 8.6,
#   연신 7.2 → 6.6, 전단 12.1 → 5.4.
_PROP_KERNEL_EPS = 0.02
_PROP_KERNEL_POWER = 2.0


def _prop_kernel_taper_width(best_dist):
    return max(1.0, 0.5 * max(0.0, float(best_dist)))


def _prop_kernel_weight(dist, best_dist, n):
    width = _prop_kernel_taper_width(best_dist)
    t = max(0.0, min(1.0, (float(dist) - float(best_dist)) / width))
    taper = 1.0 - t * t * (3.0 - 2.0 * t)
    if taper <= 0.0:
        return 0.0
    return float(n) * taper / (max(0.0, float(dist)) + _PROP_KERNEL_EPS) ** _PROP_KERNEL_POWER


def predict_from_db(input_comp):
    return predict_from_db_with_distances(input_comp)[0]


def predict_from_db_with_distances(input_comp):
    """
    물성별 DB 예측 + 그 물성 값을 가진 가장 가까운 합금까지의 거리.

    [2026-09-30] 가장 가까운 합금에 해당 물성이 없으면(예: Sn58Bi는 전단 없음) 값은 먼 합금에서
    오는데, 블렌드 가중치는 가까운 합금 거리로 정해져 먼 값을 과신했다. 분석기는 물성별 거리로
    가중치를 정한다.
    """
    by_name = _unique_alloy_candidates(input_comp)
    candidates = sorted(
        ((name, float(item["dist"])) for name, item in by_name.items()),
        key=lambda x: x[1],
    )

    predictions = {}
    nearest = {}
    props = ["tensile", "yield_strength", "elongation", "shear"]
    exact = [item for item in candidates if item[1] <= 1e-4]

    for p in props:
        weighted_values = []
        weights = []

        if exact:
            # 등록 합금은 그 합금의 시험 평균(정확일치 값). 커널도 거리 0에서 같은 값으로 수렴한다.
            selected = [(name, dist, 1.0) for name, dist in exact]
            nearest[p] = float(exact[0][1])
        else:
            usable = []
            for alloy_name, dist in candidates:
                stats = get_statistics(alloy_name)
                if stats and stats[p]:
                    usable.append((alloy_name, dist))
            if not usable:
                predictions[p] = None
                nearest[p] = None
                continue
            d0 = usable[0][1]
            nearest[p] = float(d0)
            selected = [(name, dist, None) for name, dist in usable]

        for alloy_name, dist, fixed_w in selected:
            stats = get_statistics(alloy_name)
            if not stats or not stats[p]:
                continue

            mean = stats[p]["mean"]
            n    = stats[p]["n"]
            weight = float(n) if fixed_w is not None else _prop_kernel_weight(dist, d0, n)
            if weight <= 0.0:
                continue

            weighted_values.append(mean * weight)
            weights.append(weight)

        predictions[p] = sum(weighted_values) / sum(weights) if weights else None
        if predictions[p] is None:
            nearest[p] = None

    return predictions, nearest


def predict_from_db_with_detail(input_comp):
    """
    predict_from_db()와 동일한 가중 예측 + 상위 유사 합금 목록(거리).
    analyzer.analyze_all 의 물성 DB 블렌딩·evidence에 사용.
    """
    by_name = _unique_alloy_candidates(input_comp)
    candidates = sorted(
        (
            {"alloy": name, "dist": float(item["dist"])}
            for name, item in by_name.items()
        ),
        key=lambda x: x["dist"],
    )
    top = candidates[:5]
    tensile_top = [
        {"alloy": name, "dist": dist}
        for name, dist in _select_tensile_candidates(
            [(item["alloy"], item["dist"]) for item in candidates]
        )
    ]
    pred, nearest = predict_from_db_with_distances(input_comp)
    return {"pred": pred or {}, "top": top, "tensile_top": tensile_top, "nearest_by_prop": nearest}
