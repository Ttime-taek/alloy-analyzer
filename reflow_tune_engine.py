# -*- coding: utf-8 -*-
"""
리플로우 튜닝 권장값·가드레일 검증 — 수치 원천: shared/reflow_tune_rules.json
gui.py 및 테스트에서 공통 사용.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


_RULES: Optional[Dict[str, Any]] = None


def rules_path() -> Path:
    return Path(__file__).resolve().parent / "shared" / "reflow_tune_rules.json"


def load_rules() -> Dict[str, Any]:
    global _RULES
    if _RULES is None:
        path = rules_path()
        with open(path, "r", encoding="utf-8") as f:
            _RULES = json.load(f)
    return _RULES


def reload_rules() -> None:
    """테스트용: 다음 load_rules 에서 디스크를 다시 읽음."""
    global _RULES
    _RULES = None


def _goal_profile_key(is_high_bi: bool, is_mid_bi: bool) -> str:
    if is_high_bi:
        return "high_bi"
    if is_mid_bi:
        return "mid_bi"
    return "default"


def _apply_recommend_ops(rec: Dict[str, float], ops: Any, ctx: Dict[str, Any]) -> None:
    """
    goalRecommendOps 한 줄 = [연산자, ...인자].
    Python / JS 인터프리터 시그니처를 반드시 동일하게 유지할 것.
    """
    if not isinstance(ops, list):
        return
    for raw in ops:
        if not raw or not isinstance(raw, (list, tuple)):
            continue
        op = list(raw)
        kind = str(op[0])
        if kind == "set":
            rec[str(op[1])] = float(op[2])
        elif kind == "max":
            k = str(op[1])
            rec[k] = max(float(rec[k]), float(op[2]))
        elif kind == "min":
            k = str(op[1])
            rec[k] = min(float(rec[k]), float(op[2]))
        elif kind == "add_then_min":
            k, a, c = str(op[1]), float(op[2]), float(op[3])
            rec[k] = min(c, float(rec[k]) + a)
        elif kind == "floor_after_add":
            k, a, f = str(op[1]), float(op[2]), float(op[3])
            rec[k] = max(f, float(rec[k]) + a)
        elif kind == "max_minus":
            k, m, fl = str(op[1]), float(op[2]), float(op[3])
            rec[k] = max(fl, float(rec[k]) - m)
        elif kind == "clamp":
            k, lo, hi = str(op[1]), float(op[2]), float(op[3])
            v = float(rec[k])
            rec[k] = max(lo, min(v, hi))
        elif kind == "min_add":
            k, a, c = str(op[1]), float(op[2]), float(op[3])
            rec[k] = min(c, float(rec[k]) + a)
        elif kind == "floor_after_subtract":
            k, s, fl = str(op[1]), float(op[2]), float(op[3])
            rec[k] = max(fl, float(rec[k]) - s)
        elif kind == "when_cat_equals":
            cat_need, sub = str(op[1]), op[2]
            if ctx.get("cat") == cat_need and isinstance(sub, list):
                _apply_recommend_ops(rec, sub, ctx)
        elif kind == "merge":
            d = op[1]
            if isinstance(d, dict):
                for kk, vv in d.items():
                    rec[str(kk)] = float(vv)
        else:
            raise ValueError(f"goalRecommendOps: unknown op {kind!r}")


def classify_preset(preset_name: str) -> Dict[str, Any]:
    """
    프리셋 문자열만으로 카테고리·고-Bi·중-Bi 판별 (gui.py 메서드와 동일 규칙).
    """
    name = (preset_name or "").strip()

    def _is_high_bi() -> bool:
        if not name:
            return False
        if name.startswith("78"):
            return True
        if "57.6Bi" in name:
            return True
        return False

    def _is_mid_bi() -> bool:
        if not name:
            return False
        if _is_high_bi():
            return False
        if name.startswith("73"):
            return True
        if "15Bi" in name or "25Bi" in name or "wide-paste" in name.lower():
            return True
        return False

    def _category() -> str:
        if not name or name == "AUTO":
            return "SAC"
        sac_keys = ("SAC", "Sn-Cu", "Sn-Ag", "86", "90", "51", "92")
        if any(name.startswith(k) for k in sac_keys):
            return "SAC"
        if "Bi" in name or name.startswith("78"):
            return "SnBi"
        if name.startswith("Sn-In"):
            return "SnIn"
        if name.startswith("Sn-Pb"):
            return "SnPb"
        return "범용"

    return {
        "cat": _category(),
        "is_high_bi": _is_high_bi(),
        "is_mid_bi": _is_mid_bi(),
    }


def recommend_tune_for_goal(goal: str, preset_name: str) -> Dict[str, float]:
    """합금 카테고리 + 튜닝 목표 → profile_tune(snake_case) 산출."""
    R = load_rules()
    bases: Dict[str, Dict[str, float]] = R["bases"]
    clf = classify_preset(preset_name)
    cat = clf["cat"]
    is_high_bi = clf["is_high_bi"]
    is_mid_bi = clf["is_mid_bi"]

    if is_high_bi:
        base = dict(bases["high_bi"])
    elif is_mid_bi:
        base = dict(bases["mid_bi"])
    elif cat == "SnBi":
        base = dict(bases["sn_bi"])
    elif cat == "SnPb":
        base = dict(bases["sn_pb"])
    else:
        base = dict(bases["default"])

    g = (goal or "없음").strip()
    rec = dict(base)

    if g != "없음":
        go = (R.get("goalRecommendOps") or {}).get(g)
        if isinstance(go, dict):
            pk = _goal_profile_key(is_high_bi, is_mid_bi)
            ops = go.get(pk)
            _apply_recommend_ops(rec, ops, {"cat": cat})

    for k, v in rec.items():
        rec[k] = float(round(float(v), 2))
    return rec


def validate_profile_tune(tune: dict, preset_name: str) -> Dict[str, List[str]]:
    """errors / warnings / oks — 메시지는 기존 gui.py와 동일 문구 유지."""
    R = load_rules()
    V = R["validation"]
    fatal_tal = V["tal_fatal_lt"]
    clf = classify_preset(preset_name)
    cat = clf["cat"]
    is_high_bi = clf["is_high_bi"]
    is_mid_bi = clf["is_mid_bi"]

    errors: List[str] = []
    warnings: List[str] = []
    oks: List[str] = []

    try:
        ramp = float(tune.get("ramp_rate", 1.5))
        preheat = float(tune.get("preheat_time", 90.0))
        tal = float(tune.get("over_liquidus_time", 25.0))
        cool = float(tune.get("cool_rate", 2.0))
        margin = float(tune.get("peak_margin", 20.0))
    except Exception:
        return {"errors": ["튜닝값 파싱 실패"], "warnings": [], "oks": []}

    if is_high_bi:
        hb = V["high_bi"]
        if tal < fatal_tal:
            errors.append(
                f"TAL {tal:.0f}s < 25s — 젖음 부족 위험(공급사 가이드 위반)"
            )
        elif tal < hb["tal_warn_lt"]:
            warnings.append(
                f"TAL {tal:.0f}s < 50s — 고-Bi 공급사 권장(50~100s) 미달"
            )
        elif tal > hb["tal_warn_gt"]:
            warnings.append(
                f"TAL {tal:.0f}s > 100s — 과열/취성·탈색 위험(고-Bi)"
            )
        else:
            oks.append(f"TAL {tal:.0f}s — 공급사 권장(50~100s) 영역")
    elif is_mid_bi:
        mb = V["mid_bi"]
        if tal < fatal_tal:
            errors.append(
                f"TAL {tal:.0f}s < 25s — 젖음 부족 위험(공급사 가이드 위반)"
            )
        elif tal < mb["tal_warn_lt"]:
            warnings.append(
                f"TAL {tal:.0f}s < 50s — 중-Bi 공급사 권장(50~80s) 미달"
            )
        elif tal > mb["tal_warn_gt"]:
            warnings.append(
                f"TAL {tal:.0f}s > 80s — wide-paste 합금 과도(슬럼프/취성 위험)"
            )
        else:
            oks.append(f"TAL {tal:.0f}s — 공급사 권장(50~80s) 영역")
    else:
        d = V["default"]
        tal_max = d["tal_max_sac"] if cat == "SAC" else (d["tal_max_sn_bi"] if cat == "SnBi" else d["tal_max_other"])
        if tal < fatal_tal:
            errors.append(
                f"TAL {tal:.0f}s < 25s — 젖음 부족 위험(공급사 가이드 위반)"
            )
        elif tal > tal_max:
            warnings.append(
                f"TAL {tal:.0f}s > {tal_max:.0f}s — IMC 과성장/보이드 위험"
            )
        else:
            oks.append(f"TAL {tal:.0f}s — 안전 범위")

    rp = V["ramp"]
    if ramp < rp["warn_lt"]:
        warnings.append(f"램프 {ramp:.2f}℃/s — 너무 느림(가열 불균일/잔사 위험)")
    elif ramp > rp["warn_gt"]:
        warnings.append(f"램프 {ramp:.2f}℃/s — 너무 빠름(슬럼프/스패터 위험)")
    elif rp["ok_low"] <= ramp <= rp["ok_high"]:
        oks.append(f"램프 {ramp:.2f}℃/s — 공급사 권장 대역")

    ph = V["preheat"]
    if is_high_bi or is_mid_bi:
        lbl = "고-Bi" if is_high_bi else "중-Bi"
        if preheat < ph["bi_fatal_lt"]:
            errors.append(
                f"예열 {preheat:.0f}s < 60s — {lbl} 공급사 권장(60~120s) 미달"
            )
        elif preheat > ph["bi_warn_gt"]:
            warnings.append(
                f"예열 {preheat:.0f}s > 120s — 산화/잔사 증가({lbl})"
            )
        elif ph["bi_ok_low"] <= preheat <= ph["bi_ok_high"]:
            oks.append(f"예열 {preheat:.0f}s — 공급사 권장(90s) 부근")
    else:
        if preheat < ph["std_fatal_lt"]:
            errors.append(f"예열 {preheat:.0f}s < 60s — 플럭스 활성 부족")
        elif preheat > ph["std_warn_gt"]:
            warnings.append(f"예열 {preheat:.0f}s > 140s — 산화/잔사 증가")
        elif ph["std_ok_low"] <= preheat <= ph["std_ok_high"]:
            oks.append(f"예열 {preheat:.0f}s — 공급사 권장(90s) 부근")

    pm = V["peak_margin"]
    if is_high_bi:
        if margin < pm["high_bi_fatal_lt"]:
            errors.append(f"피크 여유 {margin:.0f}℃ < 30℃ — 미접합 위험(고-Bi)")
        elif margin > pm["high_bi_warn_gt"]:
            warnings.append(f"피크 여유 {margin:.0f}℃ > 55℃ — 과열/취성 위험(고-Bi)")
        elif pm["high_bi_ok_low"] <= margin <= pm["high_bi_ok_high"]:
            oks.append(
                f"피크 여유 {margin:.0f}℃ — 공급사 권장(36~51℃, peak 175~190℃) 영역"
            )
    elif is_mid_bi:
        if margin < pm["mid_bi_fatal_lt"]:
            errors.append(f"피크 여유 {margin:.0f}℃ < 25℃ — 미접합 위험(중-Bi wide-paste)")
        elif margin > pm["mid_bi_warn_gt"]:
            warnings.append(f"피크 여유 {margin:.0f}℃ > 50℃ — 과열/IMC 과성장 위험(중-Bi)")
        elif pm["mid_bi_ok_low"] <= margin <= pm["mid_bi_ok_high"]:
            oks.append(
                f"피크 여유 {margin:.0f}℃ — 공급사 권장(30~44℃, peak 236~250℃) 영역"
            )
    else:
        if margin < pm["default_fatal_lt"]:
            errors.append(f"피크 여유 {margin:.0f}℃ < 10℃ — 미접합 위험")
        elif margin > pm["default_warn_gt"]:
            warnings.append(f"피크 여유 {margin:.0f}℃ > 40℃ — 과열/IMC 과성장 위험")

    cw = V["cool"]
    if cool > cw["warn_gt"]:
        warnings.append(f"냉각 {cool:.2f}℃/s > 4℃/s — 열충격/뒤틀림 위험")
    elif cool < cw["warn_lt"]:
        warnings.append(f"냉각 {cool:.2f}℃/s < 1℃/s — IMC 거대화 위험")

    return {"errors": errors, "warnings": warnings, "oks": oks}


def tuning_goal_options() -> List[str]:
    return list(load_rules().get("tuningGoalOptions", []))


def rules_version() -> int:
    return int(load_rules().get("version", 1))
