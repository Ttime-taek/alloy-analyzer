# gui.py (v6.4)
# ① 합금 비교 모드   — 2개 조성 나란히 분석 + 물성 차이 표
# ② 물성 레이더 차트 — 6축 육각형 방사형 차트
# ③ 즐겨찾기         — JSON 로컬 저장/불러오기
# ④ 리플로우 조건    — IPC-J-STD-020E 기준 자동 계산
# ⑤ RoHS/REACH 체크 — 10대 규제물질 스크리닝

import os
import sys

# `python gui.py` 로 더블클릭/직접 실행할 때 상대 import가 동작하도록 처리
# (`python -m test7.gui` 는 기존과 동일)
if __name__ == "__main__" and not __package__:
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _parent_dir = os.path.dirname(_pkg_dir)
    if _parent_dir not in sys.path:
        sys.path.insert(0, _parent_dir)
    __package__ = os.path.basename(_pkg_dir)

import tkinter as tk
from tkinter import simpledialog, messagebox, scrolledtext, filedialog, ttk
import threading
import queue
import json
import math
import random
import time
import webbrowser

from .solder_db import SOLDER_DB
from .analyzer import AlloyAnalyzer
from .ai_engine import AIEngine
from .app_meta import about_text_gui, header_banner_text, window_title
from .db_regression import predict_from_db
from .report import ReportBuilder
from .utils import composition_to_string, log_exception

# ── 색상 팔레트 ───────────────────────────────────────────────────────────────
UI_BG     = "#1f2937"
PANEL_BG  = "#374151"
BTN_BG    = "#4b5563"
BTN_HOVER = "#6b7280"
TEXT_BG   = "#111827"
TEXT_FG   = "#e5e7eb"
HEADER_BG = "#2563eb"
HEADER_FG = "white"

# ── RoHS/REACH 규제 물질 DB ───────────────────────────────────────────────────
ROHS_DB = {
    "Pb": {"name": "납 (Lead)",          "limit_ppm": 1000, "regulation": "RoHS Annex II"},
    "Hg": {"name": "수은 (Mercury)",      "limit_ppm": 1000, "regulation": "RoHS Annex II"},
    "Cd": {"name": "카드뮴 (Cadmium)",    "limit_ppm": 100,  "regulation": "RoHS Annex II"},
    "Cr": {"name": "6가 크롬 (Cr6+)",     "limit_ppm": 1000, "regulation": "RoHS Annex II"},
    "Bi": {"name": "비스무트 (Bismuth)",   "limit_ppm": None, "regulation": "REACH SVHC 후보 (용도별)"},
    "Sb": {"name": "안티몬 (Antimony)",    "limit_ppm": None, "regulation": "REACH SVHC 후보"},
    "In": {"name": "인듐 (Indium)",        "limit_ppm": None, "regulation": "REACH 희소금속 모니터링"},
    "Tl": {"name": "탈륨 (Thallium)",      "limit_ppm": 1000, "regulation": "REACH SVHC"},
    "Se": {"name": "셀레늄 (Selenium)",    "limit_ppm": None, "regulation": "REACH 환경 모니터링"},
    "Te": {"name": "텔루륨 (Tellurium)",   "limit_ppm": None, "regulation": "REACH 환경 모니터링"},
}


def calc_reflow_profile(solidus, liquidus, peak):
    """IPC-J-STD-020E 기준 리플로우 프로파일 자동 계산"""
    delta_t     = liquidus - solidus
    preheat_max = min(solidus - 20, 150)
    preheat_min = preheat_max - 30
    soak_time   = 60 if delta_t > 5 else 40
    tl_time     = max(30, int(20 + delta_t * 2))
    return {
        "preheat_min": round(preheat_min, 1),
        "preheat_max": round(preheat_max, 1),
        "soak_start":  round(preheat_max, 1),
        "soak_end":    round(solidus - 5, 1),
        "soak_time":   soak_time,
        "tl_time":     tl_time,
        "ramp_up":     3.0,
        "cool_rate":   4.0,
        "peak_min":    round(liquidus + 20, 1),
        "peak_max":    round(liquidus + 40, 1),
        "recommended_peak": round(peak, 1),
    }


def add_hover(btn):
    def on_enter(_e):
        if btn["state"] != tk.DISABLED:
            btn["bg"] = BTN_HOVER
    def on_leave(_e):
        if btn["state"] != tk.DISABLED:
            btn["bg"] = BTN_BG
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)


def get_korean_font():
    """OS별 한글 폰트 자동 감지"""
    try:
        import matplotlib.font_manager as fm
        import platform
        candidates = {
            "Windows": [
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/NanumGothic.ttf",
                "C:/Windows/Fonts/gulim.ttc",
            ],
            "Darwin": [
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                "/Library/Fonts/NanumGothic.ttf",
                "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            ],
            "Linux": [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
            ],
        }
        for path in candidates.get(platform.system(), []):
            if os.path.exists(path):
                return fm.FontProperties(fname=path)
        for f in fm.fontManager.ttflist:
            if any(k in f.name for k in ["CJK", "Gothic", "Nanum", "Malgun", "Noto"]):
                return fm.FontProperties(fname=f.fname)
    except Exception:
        pass
    return None


# =============================================================================
class AlloyGUI:

    FAVORITES_FILE = "favorites.json"
    PROFILE_SETTINGS_FILE = "profile_settings.json"

    def __init__(self, api_key=""):
        self.comp           = {}
        self.mode           = "eng"
        self.literature_mode = "fast"  # initialized as StringVar after Tk root is created
        self.last_result    = None
        self.compare_comp   = {}
        self.compare_result = None
        self._full_result_win = None
        self._full_result_btn = None
        self._analysis_live_enabled = False
        self._analysis_started_ts = 0.0
        self._last_progress_msg = ""
        self._progress_events = queue.Queue()
        self._progress_current = 0.0
        self._progress_target = 0.0
        self._active_progress_msg = ""
        self._spinner_idx = 0
        self._last_heartbeat_sec = -1

        self.ai       = AIEngine(api_key=api_key)
        self.analyzer = AlloyAnalyzer(SOLDER_DB, ai_engine=self.ai)
        self.reporter = ReportBuilder()

        self.root = tk.Tk()
        self.root.title(window_title())
        self.root.geometry("1700x980")
        self.root.configure(bg=UI_BG)
        self.literature_mode = tk.StringVar(value="fast")

        # 상단 상태/AI 표시용
        self.top_status_var = tk.StringVar(value="대기 중")
        self.ai_status_var = tk.StringVar(value=self._make_ai_status_text())
        self.ai_request_badge_var = tk.StringVar(value="○ 요청 대기")
        self.ai_usage_var = tk.StringVar(value="AI 세션: 요청 0 / AI 0 / 폴백 0")
        self.ai_quota_badge_var = tk.StringVar(value="쿼터 정상")

        self.buttons    = {}
        self._link_targets = {}
        self.graph_btn  = None
        self.radar_btn  = None
        self.reflow_btn = None
        self.profile48_btn = None
        self.imc3d_btn = None
        # Reflow profile presets / tuning (peak-based template)
        self.profile_preset = tk.StringVar(value="AUTO")
        self.profile_tune = {
            "ramp_rate": 1.5,          # C/s
            "preheat_time": 90.0,      # sec (90±30 reference)
            "over_liquidus_time": 25.0,# sec (>=25 reference)
            "cool_rate": 2.0,          # C/s
            "peak_margin": 20.0,       # C above liquidus
        }
        # 튜닝 목표(공급사 가이드 기반 자동 권장값 산출용)
        # 없음 / 젖음(B) / 보이드(C) / B+C / 슬럼프억제 / IMC최소
        self.profile_goal = tk.StringVar(value="없음")
        self.imc_substrate = tk.StringVar(value="Cu-OSP")
        self.imc_tal_mode = tk.StringVar(value="AUTO(profile)")
        self.imc_tal_ref = tk.StringVar(value="Liquidus")
        self.imc_tal_delta_c = tk.StringVar(value="3")
        self.imc_tal_sec = tk.StringVar(value="35")
        self.imc_view_style = tk.StringVar(value="표준")
        self.imc_demo_preset = tk.StringVar(value="AUTO")
        self.imc_tal_entry = None
        self.imc_tal_delta_entry = None
        self._load_profile_settings()
        self.build_ui()
        self._update_ai_result_mode_label()
        self.root.after(120, self._drain_progress_events)
        self.root.after(60, self._animate_progress_bar)
        self.root.after(200, self._tick_live_status)

    def _profile_settings_path(self):
        try:
            return os.path.join(os.path.dirname(__file__), self.PROFILE_SETTINGS_FILE)
        except Exception:
            return self.PROFILE_SETTINGS_FILE

    def _load_profile_settings(self):
        path = self._profile_settings_path()
        try:
            if not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            preset = data.get("profile_preset")
            if isinstance(preset, str) and preset.strip():
                self.profile_preset.set(preset.strip())
            goal = data.get("profile_goal")
            valid_goal = {"없음", "젖음(B)", "보이드(C)", "B+C", "슬럼프억제", "IMC최소"}
            if isinstance(goal, str) and goal.strip() in valid_goal:
                self.profile_goal.set(goal.strip())
            tune = data.get("profile_tune")
            if isinstance(tune, dict):
                for k in list(self.profile_tune.keys()):
                    if k in tune:
                        try:
                            self.profile_tune[k] = float(tune.get(k))
                        except Exception:
                            pass
            lit = data.get("literature_mode")
            if isinstance(lit, str) and lit.strip().lower() in ("fast", "deep"):
                self.literature_mode.set(lit.strip().lower())
            sub = data.get("imc_substrate")
            valid_sub = {"Cu-OSP", "ENIG(Ni/Au)", "ImmAg", "ImmSn"}
            if isinstance(sub, str) and sub.strip() in valid_sub:
                self.imc_substrate.set(sub.strip())
            tal_mode = data.get("imc_tal_mode")
            valid_mode = {"AUTO(profile)", "기판기본", "사용자입력"}
            if isinstance(tal_mode, str) and tal_mode.strip() in valid_mode:
                self.imc_tal_mode.set(tal_mode.strip())
            tal_ref = data.get("imc_tal_ref")
            valid_ref = {"Liquidus", "Liquidus+3C", "Liquidus+Δ"}
            if isinstance(tal_ref, str) and tal_ref.strip() in valid_ref:
                self.imc_tal_ref.set(tal_ref.strip())
            tal_delta = data.get("imc_tal_delta_c")
            if tal_delta is not None:
                try:
                    dv = float(tal_delta)
                    dv = max(0.0, min(30.0, dv))
                    self.imc_tal_delta_c.set(f"{dv:.1f}".rstrip("0").rstrip("."))
                except Exception:
                    pass
            tal = data.get("imc_tal_sec")
            if tal is not None:
                try:
                    tv = float(tal)
                    tv = max(5.0, min(180.0, tv))
                    self.imc_tal_sec.set(f"{tv:.0f}")
                except Exception:
                    pass
            imc_view = data.get("imc_view_style")
            if isinstance(imc_view, str) and imc_view.strip() in {"표준", "발표"}:
                self.imc_view_style.set(imc_view.strip())
            demo_preset = data.get("imc_demo_preset")
            if isinstance(demo_preset, str) and demo_preset.strip() in {"AUTO", "SAC305", "Sn-Bi", "Sn-In", "Sn-Pb"}:
                self.imc_demo_preset.set(demo_preset.strip())
        except Exception:
            return

    def _save_profile_settings(self):
        path = self._profile_settings_path()
        try:
            try:
                tal_v = float(self.imc_tal_sec.get() or 35.0)
            except Exception:
                tal_v = 35.0
            tal_v = max(5.0, min(180.0, tal_v))
            self.imc_tal_sec.set(f"{tal_v:.0f}")
            try:
                dlt = float(self.imc_tal_delta_c.get() or 3.0)
            except Exception:
                dlt = 3.0
            dlt = max(0.0, min(30.0, dlt))
            self.imc_tal_delta_c.set(f"{dlt:.1f}".rstrip("0").rstrip("."))
            data = {
                "profile_preset": (self.profile_preset.get() or "AUTO").strip(),
                "profile_goal": (self.profile_goal.get() or "없음").strip(),
                "profile_tune": dict(self.profile_tune),
                "literature_mode": (
                    self.literature_mode.get()
                    if hasattr(self.literature_mode, "get")
                    else str(self.literature_mode)
                )
                or "fast",
                "imc_substrate": (self.imc_substrate.get() or "Cu-OSP").strip(),
                "imc_tal_mode": (self.imc_tal_mode.get() or "AUTO(profile)").strip(),
                "imc_tal_ref": (self.imc_tal_ref.get() or "Liquidus").strip(),
                "imc_tal_delta_c": dlt,
                "imc_tal_sec": tal_v,
                "imc_view_style": (self.imc_view_style.get() or "표준").strip(),
                "imc_demo_preset": (self.imc_demo_preset.get() or "AUTO").strip(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            return

    # ─────────────────────────────────────────────────────────────────────────
    # 프로파일 튜닝 강화: 합금 카테고리 / 목표 기반 권장값 / 가드레일 검증
    # ─────────────────────────────────────────────────────────────────────────
    def _alloy_category_from_preset(self, preset_name: str) -> str:
        """프리셋 이름을 합금 카테고리로 매핑 — shared/reflow_tune_rules.json 로직(reflow_tune_engine)."""
        try:
            from reflow_tune_engine import classify_preset

            return str(classify_preset(preset_name).get("cat") or "범용")
        except Exception:
            return "범용"

    def _is_high_bi_preset(self, preset_name: str) -> bool:
        try:
            from reflow_tune_engine import classify_preset

            return bool(classify_preset(preset_name).get("is_high_bi"))
        except Exception:
            return False

    def _is_mid_bi_preset(self, preset_name: str) -> bool:
        try:
            from reflow_tune_engine import classify_preset

            return bool(classify_preset(preset_name).get("is_mid_bi"))
        except Exception:
            return False

    def _recommend_tune_for_goal(self, goal: str, preset_name: str) -> dict:
        """합금 + 목표 → 권장 profile_tune(shared/reflow_tune_rules.json 기반)."""
        from reflow_tune_engine import recommend_tune_for_goal as _rec

        return _rec(goal, preset_name)

    def _validate_profile_tune(self, tune: dict, preset_name: str) -> dict:
        """가드레일 검증 — reflow_tune_engine.validate_profile_tune."""
        from reflow_tune_engine import validate_profile_tune as _val

        return _val(tune, preset_name)

    def _get_tal_threshold_c(self, liquidus_c: float):
        ref = (self.imc_tal_ref.get() or "Liquidus").strip()
        liq = float(liquidus_c or 0.0)
        delta = 0.0
        if ref == "Liquidus+3C":
            delta = 3.0
        elif ref == "Liquidus+Δ":
            try:
                delta = float(self.imc_tal_delta_c.get() or 3.0)
            except Exception:
                delta = 3.0
            delta = max(0.0, min(30.0, delta))
            self.imc_tal_delta_c.set(f"{delta:.1f}".rstrip("0").rstrip("."))
        return liq + delta, ref

    def _imc_default_tal(self, substrate: str) -> float:
        s = str(substrate or "").strip()
        if s == "ENIG(Ni/Au)":
            return 40.0
        if s == "ImmAg":
            return 35.0
        if s == "ImmSn":
            return 30.0
        return 30.0  # Cu-OSP

    def _estimate_tal_from_profile(self, result) -> float:
        """
        리플로우 시간-온도 곡선에서 Liquidus 초과 구간을 적분해 TAL을 계산.
        """
        try:
            prof = self._build_peak_profile_curve(result)
            tal_thr, _ref = self._get_tal_threshold_c(float(prof["liquidus"]))
            tal = self._calc_tal_above_liquidus(prof["time"], prof["temp"], tal_thr)
            return max(5.0, min(180.0, float(tal)))
        except Exception:
            try:
                tal = float(self.profile_tune.get("over_liquidus_time", 35.0) or 35.0)
            except Exception:
                tal = 35.0
            return max(5.0, min(180.0, tal))

    def _calc_tal_above_liquidus(self, time_pts, temp_pts, threshold_c) -> float:
        """선형 보간된 time-temp 구간에서 T > threshold_c 인 시간을 적분."""
        if not isinstance(time_pts, list) or not isinstance(temp_pts, list):
            return 0.0
        if len(time_pts) != len(temp_pts) or len(time_pts) < 2:
            return 0.0
        liq = float(threshold_c or 0.0)
        tal = 0.0
        for i in range(len(time_pts) - 1):
            t0 = float(time_pts[i])
            t1 = float(time_pts[i + 1])
            y0 = float(temp_pts[i])
            y1 = float(temp_pts[i + 1])
            if t1 <= t0:
                continue
            dt = t1 - t0
            if y0 > liq and y1 > liq:
                tal += dt
                continue
            if y0 <= liq and y1 <= liq:
                continue
            # 교차점 1개(선형 구간) 가정
            if abs(y1 - y0) < 1e-12:
                continue
            f = (liq - y0) / (y1 - y0)
            f = max(0.0, min(1.0, f))
            tc = t0 + dt * f
            if y0 > liq >= y1:
                tal += max(0.0, tc - t0)
            elif y0 <= liq < y1:
                tal += max(0.0, t1 - tc)
        return tal

    def _calc_time_in_range(self, time_pts, temp_pts, low_c, high_c) -> float:
        """
        선형 보간 구간에서 low_c <= T <= high_c 인 체류시간을 적분.
        (교차점이 0~2개일 수 있으므로 각 구간 분할 후 중첩 길이를 합산)
        """
        if not isinstance(time_pts, list) or not isinstance(temp_pts, list):
            return 0.0
        if len(time_pts) != len(temp_pts) or len(time_pts) < 2:
            return 0.0
        lo = float(min(low_c, high_c))
        hi = float(max(low_c, high_c))
        if hi <= lo:
            return 0.0
        tot = 0.0
        for i in range(len(time_pts) - 1):
            t0 = float(time_pts[i])
            t1 = float(time_pts[i + 1])
            y0 = float(temp_pts[i])
            y1 = float(temp_pts[i + 1])
            if t1 <= t0:
                continue
            dt = t1 - t0
            dy = y1 - y0
            # 구간 내 경계 교차점 후보 (파라미터 s in [0,1])
            ss = [0.0, 1.0]
            if abs(dy) > 1e-12:
                for b in (lo, hi):
                    s = (b - y0) / dy
                    if 0.0 < s < 1.0:
                        ss.append(s)
            ss = sorted(set(ss))
            for a, b in zip(ss[:-1], ss[1:]):
                sm = 0.5 * (a + b)
                ym = y0 + dy * sm
                if lo <= ym <= hi:
                    tot += (b - a) * dt
        return tot

    def _profile_metrics_for_result(self, result):
        """결과 1건에서 TAL/S~L/Peak-5 체류시간 지표를 계산."""
        try:
            r = result if isinstance(result, dict) else {}
            solidus = float(r.get("solidus", 0.0) or 0.0)
            liquidus = float(r.get("liquidus", 0.0) or 0.0)
            peak = float(r.get("peak", 0.0) or 0.0)
            prof = self._build_peak_profile_curve(r)
            tal_thr, tal_ref = self._get_tal_threshold_c(liquidus)
            tal = self._calc_tal_above_liquidus(prof["time"], prof["temp"], tal_thr)
            tsl = self._calc_time_in_range(prof["time"], prof["temp"], solidus, liquidus)
            tpk = self._calc_tal_above_liquidus(prof["time"], prof["temp"], peak - 5.0)
            return {
                "tal_s": float(tal),
                "tal_ref": str(tal_ref),
                "tal_thr_c": float(tal_thr),
                "tsl_s": float(tsl),
                "tpk_s": float(tpk),
            }
        except Exception:
            return {}

    def _build_peak_profile_curve(self, result):
        """
        show_peak_profile와 동일한 규칙으로 리플로우 keypoint를 구성.
        반환: dict(time,temp,preset_name,...) + liquidus
        """
        r = result if isinstance(result, dict) else {}
        solidus = float(r.get("solidus", 0.0) or 0.0)
        liquidus = float(r.get("liquidus", 0.0) or 0.0)
        peak_in = float(r.get("peak", 0.0) or 0.0)
        md = r.get("melting_detail") if isinstance(r.get("melting_detail"), dict) else {}
        family = (md.get("family") or "").strip()

        presets = {
            "SAC":              {"ramp_rate": 1.6, "preheat_time": 90.0, "over_liquidus_time": 45.0, "cool_rate": 3.0, "peak_margin": 25.0},
            "86(Sn-0.3Ag-0.7Cu)": {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 25.0, "cool_rate": 3.0, "peak_margin": 25.0, "reflow_thr": 227.0, "peak_min": 240.0, "peak_max": 255.0},
            "90(Sn-1.0Ag-0.7Cu)": {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 25.0, "cool_rate": 3.0, "peak_margin": 25.0, "reflow_thr": 224.0, "peak_min": 240.0, "peak_max": 255.0},
            "51(Sn-3Ag-0.5Cu-3Bi)": {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 25.0, "cool_rate": 3.0, "peak_margin": 30.0, "peak_min": 230.0, "peak_max": 255.0},
            "92(Sn-0.3Ag-0.5Cu-3Bi)": {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 25.0, "cool_rate": 3.0, "peak_margin": 30.0, "peak_min": 235.0, "peak_max": 255.0},
            "78(Sn-0.4Ag-57.6Bi)": {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 75.0, "cool_rate": 2.5, "peak_margin": 35.0, "preheat_start": 100.0, "preheat_end": 125.0, "reflow_thr": 140.0, "peak_min": 175.0, "peak_max": 190.0},
            "73(Sn-3Ag-15Bi-0.03In)": {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 65.0, "cool_rate": 2.5, "peak_margin": 35.0, "preheat_start": 100.0, "preheat_end": 125.0, "reflow_thr": 206.0, "peak_min": 236.0, "peak_max": 250.0},
            "Sn-Bi(저융점)":     {"ramp_rate": 1.3, "preheat_time": 80.0, "over_liquidus_time": 30.0, "cool_rate": 2.5, "peak_margin": 20.0},
            "Sn-In(저융점)":     {"ramp_rate": 1.3, "preheat_time": 80.0, "over_liquidus_time": 30.0, "cool_rate": 2.5, "peak_margin": 20.0},
            "Sn-Pb":            {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 40.0, "cool_rate": 3.0, "peak_margin": 25.0},
            "Sn-Cu":            {"ramp_rate": 1.6, "preheat_time": 90.0, "over_liquidus_time": 45.0, "cool_rate": 3.0, "peak_margin": 25.0},
            "Sn-Ag":            {"ramp_rate": 1.6, "preheat_time": 90.0, "over_liquidus_time": 45.0, "cool_rate": 3.0, "peak_margin": 25.0},
            "범용":             {"ramp_rate": 1.5, "preheat_time": 90.0, "over_liquidus_time": 25.0, "cool_rate": 2.0, "peak_margin": 20.0},
        }

        preset_name = (self.profile_preset.get() or "AUTO").strip()
        if preset_name == "AUTO":
            norm = r.get("norm") if isinstance(r.get("norm"), dict) else {}
            ag = float(norm.get("Ag", 0.0) or 0.0)
            cu = float(norm.get("Cu", 0.0) or 0.0)
            bi = float(norm.get("Bi", 0.0) or 0.0)
            inp = float(norm.get("In", 0.0) or 0.0)
            if bi >= 40.0 and family == "SnBi":
                preset_name = "78(Sn-0.4Ag-57.6Bi)"
            elif 10.0 <= bi < 40.0 and ag >= 1.0 and cu < 0.3:
                # 73 타입(Sn-3Ag-15Bi-0.03In 등) — wide-paste 중-Bi
                preset_name = "73(Sn-3Ag-15Bi-0.03In)"
            elif bi < 1.0 and inp < 1.0 and abs(cu - 0.7) <= 0.25:
                if abs(ag - 0.3) <= 0.35:
                    preset_name = "86(Sn-0.3Ag-0.7Cu)"
                elif abs(ag - 1.0) <= 0.35:
                    preset_name = "90(Sn-1.0Ag-0.7Cu)"
            elif bi >= 2.0 and abs(cu - 0.5) <= 0.35:
                preset_name = "51(Sn-3Ag-0.5Cu-3Bi)" if ag >= 2.0 else "92(Sn-0.3Ag-0.5Cu-3Bi)"
            elif family == "SAC":
                preset_name = "SAC"
            elif family == "SnBi":
                preset_name = "Sn-Bi(저융점)"
            elif family == "SnIn":
                preset_name = "Sn-In(저융점)"
            elif family == "SnPb":
                preset_name = "Sn-Pb"
            elif family == "SnCu":
                preset_name = "Sn-Cu"
            elif family == "SnAg":
                preset_name = "Sn-Ag"
            else:
                preset_name = "범용"

        pset = presets.get(preset_name, presets["범용"])
        ramp_rate = float(self.profile_tune.get("ramp_rate", pset["ramp_rate"]))
        cool_rate = float(self.profile_tune.get("cool_rate", pset["cool_rate"]))
        preheat_time = float(self.profile_tune.get("preheat_time", pset["preheat_time"]))
        over_liquidus_time = float(self.profile_tune.get("over_liquidus_time", pset["over_liquidus_time"]))
        peak_margin = float(self.profile_tune.get("peak_margin", pset["peak_margin"]))

        t_ambient = 25.0
        t_pre_start = float(pset.get("preheat_start", 150.0))
        t_pre_end = float(pset.get("preheat_end", min(190.0, max(t_pre_start + 20.0, solidus - 5.0))))
        t_reflow_thr = float(pset.get("reflow_thr", max(liquidus, t_pre_end + 15.0)))
        peak = max(peak_in, liquidus + max(10.0, peak_margin))
        if "peak_min" in pset:
            peak = max(float(pset["peak_min"]), peak)
        if "peak_max" in pset:
            peak = min(float(pset["peak_max"]), peak)

        dt_a = max(25.0, (t_pre_start - t_ambient) / ramp_rate)
        dt_b = max(60.0, min(140.0, preheat_time))
        dt_c = max(15.0, (t_reflow_thr - t_pre_end) / ramp_rate)
        dt_d = max(10.0, (peak - t_reflow_thr) / ramp_rate)
        dt_e = max(25.0, min(120.0, over_liquidus_time))
        t_cool_end = min(160.0, max(80.0, t_pre_end))
        dt_f = max(30.0, (peak - t_cool_end) / cool_rate)

        t0 = 0.0
        tA = t0 + dt_a
        tB = tA + dt_b
        tC = tB + dt_c
        tD = tC + dt_d
        tE = tD + dt_e
        tF = tE + dt_f

        time = [t0, tA, tB, tC, tD, tE, tF]
        temp = [t_ambient, t_pre_start, t_pre_end, t_reflow_thr, peak, peak - 5.0, t_cool_end]
        return {
            "time": time,
            "temp": temp,
            "preset_name": preset_name,
            "ramp_rate": ramp_rate,
            "cool_rate": cool_rate,
            "peak_margin": peak_margin,
            "dt_b": dt_b,
            "dt_e": dt_e,
            "t_pre_start": t_pre_start,
            "t_pre_end": t_pre_end,
            "t_reflow_thr": t_reflow_thr,
            "peak": peak,
            "t0": t0,
            "tA": tA,
            "tB": tB,
            "tC": tC,
            "tE": tE,
            "tF": tF,
            "liquidus": liquidus,
        }

    def _on_imc_substrate_changed(self):
        try:
            mode = (self.imc_tal_mode.get() or "").strip()
            if mode == "기판기본":
                self.imc_tal_sec.set(f"{self._imc_default_tal(self.imc_substrate.get()):.0f}")
        except Exception:
            pass
        self._refresh_imc_tal_ui()
        self._save_profile_settings()

    def _refresh_imc_tal_ui(self):
        try:
            mode = (self.imc_tal_mode.get() or "").strip()
            if mode == "기판기본":
                self.imc_tal_sec.set(f"{self._imc_default_tal(self.imc_substrate.get()):.0f}")
            elif mode == "AUTO(profile)":
                if isinstance(self.last_result, dict):
                    self.imc_tal_sec.set(f"{self._estimate_tal_from_profile(self.last_result):.0f}")
            if self.imc_tal_entry is not None:
                self.imc_tal_entry.config(state=(tk.NORMAL if mode == "사용자입력" else tk.DISABLED))
            if self.imc_tal_delta_entry is not None:
                ref = (self.imc_tal_ref.get() or "").strip()
                self.imc_tal_delta_entry.config(state=(tk.NORMAL if ref == "Liquidus+Δ" else tk.DISABLED))
        except Exception:
            pass

    def _on_imc_tal_mode_changed(self):
        self._refresh_imc_tal_ui()
        self._save_profile_settings()

    def _on_imc_tal_ref_changed(self):
        self._refresh_imc_tal_ui()
        self._save_profile_settings()

    # ─────────────────────────────────────────────────────────────────────────
    def _make_ai_status_text(self):
        ai_detail = str(getattr(self.ai, "status_detail", "") or "").strip()
        if getattr(self.ai, "available", False):
            return f"AI: 활성 ({ai_detail or '연결됨'})"
        return f"AI: 비활성 (로컬 규칙만 사용, {ai_detail or '원인 미상'})"

    def _refresh_ai_status_ui(self):
        try:
            self.ai_status_var.set(self._make_ai_status_text())
        except Exception:
            pass
        self._refresh_ai_usage_ui()

    def _refresh_ai_usage_ui(self):
        snap = {}
        try:
            fn = getattr(self.ai, "get_usage_snapshot", None)
            if callable(fn):
                snap = fn() or {}
        except Exception:
            snap = {}
        calls = int(snap.get("full_analysis_calls", 0) or 0)
        ai_used = int(snap.get("full_analysis_ai_used", 0) or 0)
        fallbacks = int(snap.get("full_analysis_fallbacks", 0) or 0)
        qerr = int(snap.get("ask_quota_errors", 0) or 0)
        self.ai_usage_var.set(f"AI 세션: 요청 {calls} / AI {ai_used} / 폴백 {fallbacks}")
        try:
            if getattr(self, "ai_usage_label", None):
                self.ai_usage_label.config(fg=("#cbd5e1" if calls > 0 else "#94a3b8"))
        except Exception:
            pass
        if qerr > 0:
            self.ai_quota_badge_var.set(f"쿼터 경고 (429): {qerr}")
            qbg, qfg = "#991b1b", "#fee2e2"
        else:
            self.ai_quota_badge_var.set("쿼터 정상")
            qbg, qfg = "#14532d", "#dcfce7"
        try:
            if getattr(self, "ai_quota_badge_label", None):
                self.ai_quota_badge_label.config(
                    bg=qbg,
                    fg=qfg,
                    highlightbackground=qbg,
                    highlightcolor=qbg,
                )
        except Exception:
            pass
        try:
            if getattr(self, "ai_status_label", None):
                self.ai_status_label.config(
                    fg=("#22c55e" if getattr(self.ai, "available", False) else "#f97316")
                )
        except Exception:
            pass

    def _refresh_ai_engine(self, force=False):
        """
        실행 중 키가 추가된 경우를 위해 AI 엔진을 재평가한다.
        """
        try:
            if force or not getattr(self.ai, "available", False):
                self.ai = AIEngine(api_key=(getattr(self.ai, "api_key", "") or ""))
                self.analyzer.ai = self.ai
        except Exception:
            pass
        self._refresh_ai_status_ui()
        return bool(getattr(self.ai, "available", False))

    def _update_ai_result_mode_label(self):
        try:
            detail = str(getattr(self.ai, "status_detail", "") or "").strip()
            lm = (self.literature_mode.get() if hasattr(self.literature_mode, "get") else str(self.literature_mode)).strip().lower()
            lm_txt = "정밀" if lm == "deep" else "빠름"
            if getattr(self.ai, "available", False):
                txt = f"AI 모드: Gemini / 문헌:{lm_txt} ({detail or '연결됨'})"
            else:
                txt = f"AI 모드: 로컬 폴백 / 문헌:{lm_txt} ({detail or '원인 미상'})"
            self.ai_result_mode_var.set(txt)
        except Exception:
            pass

    def _set_ai_request_badge(self, used=None, compare_pair=None):
        """
        상단 배지: "이번 요청 AI 반영됨 / 로컬 폴백" 상태를 표시.
        compare_pair=(a_used, b_used)가 주어지면 비교 분석 상태로 표시.
        """
        text = "○ 요청 대기"
        bg = "#475569"
        fg = "white"
        try:
            if isinstance(compare_pair, (list, tuple)) and len(compare_pair) >= 2:
                a_used = bool(compare_pair[0])
                b_used = bool(compare_pair[1])
                if a_used and b_used:
                    text = "✓ 비교 A/B: AI+DB 하이브리드 분석"
                    bg = "#16a34a"
                elif (not a_used) and (not b_used):
                    text = "⚠ 비교 A/B: DB/규칙 기반 분석"
                    bg = "#ea580c"
                else:
                    text = "~ 비교 A/B: 하이브리드/DB 혼합"
                    bg = "#2563eb"
            elif used is True:
                text = "✓ 이번 요청: AI+DB 하이브리드 분석"
                bg = "#16a34a"
            elif used is False:
                text = "⚠ 이번 요청: DB/규칙 기반 분석"
                bg = "#ea580c"
            self.ai_request_badge_var.set(text)
        except Exception:
            return
        try:
            if getattr(self, "ai_request_badge_label", None):
                self.ai_request_badge_label.config(
                    bg=bg,
                    fg=fg,
                    highlightbackground=bg,
                    highlightcolor=bg,
                )
        except Exception:
            pass

    def _reset_live_progress_log(self, title="분석"):
        self._analysis_live_enabled = True
        self._analysis_started_ts = time.time()
        self._last_progress_msg = ""
        self._active_progress_msg = "분석 시작..."
        self._spinner_idx = 0
        self._last_heartbeat_sec = -1
        self._progress_current = 0.0
        self._progress_target = 0.0
        def _ui():
            try:
                self.live_elapsed_var.set("경과 0.0s")
                self.live_progress_box.config(state=tk.NORMAL)
                self.live_progress_box.delete("1.0", tk.END)
                self.live_progress_box.insert(tk.END, f"[0.0s] {title} 시작\n")
                self.live_progress_box.config(state=tk.DISABLED)
            except Exception:
                pass
        try:
            self.root.after(0, _ui)
        except Exception:
            pass

    def _append_live_progress_log(self, msg):
        if not self._analysis_live_enabled:
            return
        text = str(msg or "").strip()
        if not text:
            return
        if text == self._last_progress_msg:
            return
        self._last_progress_msg = text
        elapsed = max(0.0, float(time.time() - float(self._analysis_started_ts or 0.0)))
        line = f"[{elapsed:0.1f}s] {text}\n"
        try:
            self.live_progress_box.config(state=tk.NORMAL)
            self.live_progress_box.insert(tk.END, line)
            self.live_progress_box.see(tk.END)
            self.live_progress_box.config(state=tk.DISABLED)
        except Exception:
            pass

    def _finish_live_progress_log(self, ok=True):
        if not self._analysis_live_enabled:
            return
        elapsed = max(0.0, float(time.time() - float(self._analysis_started_ts or 0.0)))
        tail = "완료" if ok else "중단/실패"
        def _ui():
            try:
                self.live_elapsed_var.set(f"경과 {elapsed:0.1f}s")
                self.live_progress_box.config(state=tk.NORMAL)
                self.live_progress_box.insert(tk.END, f"[{elapsed:0.1f}s] {tail}\n")
                self.live_progress_box.see(tk.END)
                self.live_progress_box.config(state=tk.DISABLED)
                self.progress_label.config(text=tail)
                self.top_status_var.set(tail)
            except Exception:
                pass
        try:
            self.root.after(0, _ui)
        except Exception:
            pass
        self._analysis_live_enabled = False
        self._active_progress_msg = ""

    # ─────────────────────────────────────────────────────────────────────────
    def set_progress(self, percent, msg=""):
        try:
            p = int(float(percent))
        except Exception:
            p = 0
        p = max(0, min(100, p))
        try:
            self._progress_events.put_nowait((p, str(msg or "")))
        except Exception:
            pass

    def _animate_progress_bar(self):
        try:
            cur = float(self._progress_current or 0.0)
            tgt = float(self._progress_target or 0.0)
            if self._analysis_live_enabled and tgt < 96.0:
                elapsed = max(0.0, float(time.time() - float(self._analysis_started_ts or 0.0)))
                # 장시간 단계에서 멈춰 보이지 않도록 완만하게 목표치를 자연 증가
                creep_floor = min(95.0, 8.0 + elapsed * 2.6)
                tgt = max(tgt, creep_floor)
            if cur < tgt:
                gap = tgt - cur
                step = 0.8 if gap < 4 else (1.6 if gap < 15 else 2.8)
                cur = min(tgt, cur + step)
            elif cur > tgt:
                cur = max(tgt, cur - 4.0)
            self._progress_current = cur
            self.progress_var.set(int(round(cur)))
        except Exception:
            pass
        try:
            self.root.after(60, self._animate_progress_bar)
        except Exception:
            pass

    def _tick_live_status(self):
        try:
            if self._analysis_live_enabled:
                elapsed = max(0.0, float(time.time() - float(self._analysis_started_ts or 0.0)))
                spinner = ("|", "/", "-", "\\")
                self._spinner_idx = (self._spinner_idx + 1) % len(spinner)
                sp = spinner[self._spinner_idx]
                base = (self._active_progress_msg or "분석 진행 중...").strip()
                status_text = f"{base}  {sp}  {elapsed:0.1f}s"
                try:
                    self.progress_label.config(text=status_text)
                except Exception:
                    pass
                try:
                    self.top_status_var.set(status_text)
                except Exception:
                    pass
                # 2초마다 같은 단계라도 heartbeat 로그를 남겨 정지처럼 보이지 않게 함
                now_sec = int(elapsed)
                if now_sec % 2 == 0 and now_sec != self._last_heartbeat_sec and now_sec > 0:
                    self._last_heartbeat_sec = now_sec
                    self._append_live_progress_log(f"{base} (진행중, {elapsed:0.1f}s)")
        except Exception:
            pass
        try:
            self.root.after(200, self._tick_live_status)
        except Exception:
            pass

    def _drain_progress_events(self):
        try:
            if self._analysis_live_enabled:
                elapsed = max(0.0, float(time.time() - float(self._analysis_started_ts or 0.0)))
                try:
                    self.live_elapsed_var.set(f"경과 {elapsed:0.1f}s")
                except Exception:
                    pass
            while True:
                p, msg = self._progress_events.get_nowait()
                self._progress_target = float(max(0, min(100, p)))
                self._active_progress_msg = msg or self._active_progress_msg
                try:
                    self.progress_label.config(text=msg)
                except Exception:
                    pass
                self._append_live_progress_log(msg)
                try:
                    self.top_status_var.set(msg or "대기 중")
                except Exception:
                    pass
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.root.after(120, self._drain_progress_events)
        except Exception:
            pass

    def _make_disabled_btn(self, parent, text, cmd, width=14):
        b = tk.Button(parent, text=text, command=cmd,
                      bg="#1e3a5f", fg="#aaaaaa",
                      width=width, height=2,
                      font=("Segoe UI", 9, "bold"),
                      state=tk.DISABLED)
        b.pack(side="left", padx=4)
        return b

    def _enable_result_btns(self):
        for btn in (self.graph_btn, self.radar_btn, self.reflow_btn, self.profile48_btn, self.imc3d_btn):
            if btn:
                btn.config(state=tk.NORMAL, bg="#2563eb", fg="white")

    # ─────────────────────────────────────────────────────────────────────────
    # UI 구성
    # ─────────────────────────────────────────────────────────────────────────
    def _show_about(self):
        win = tk.Toplevel(self.root)
        win.title("프로그램 정보")
        win.configure(bg=PANEL_BG)
        win.geometry("640x480")
        win.minsize(400, 320)
        tk.Label(
            win,
            text="프로그램 정보",
            bg=PANEL_BG,
            fg="white",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))
        tk.Label(
            win,
            text="데모·보고용으로 버전·처리 방식·면책을 확인할 수 있습니다.",
            bg=PANEL_BG,
            fg="#9ca3af",
            font=("Segoe UI", 9),
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        box = scrolledtext.ScrolledText(
            win,
            wrap=tk.WORD,
            font=("Malgun Gothic", 10) if os.name == "nt" else ("Segoe UI", 10),
            bg=TEXT_BG,
            fg=TEXT_FG,
            insertbackground=TEXT_FG,
            relief=tk.FLAT,
            padx=10,
            pady=10,
        )
        box.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        box.insert("1.0", about_text_gui())
        box.config(state=tk.DISABLED)
        bf = tk.Frame(win, bg=PANEL_BG)
        bf.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(
            bf,
            text="닫기",
            command=win.destroy,
            bg="#2563eb",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=4,
        ).pack(side="right")

    def build_ui(self):
        menubar = tk.Menu(self.root)
        help_m = tk.Menu(menubar, tearoff=0)
        help_m.add_command(label="프로그램 정보…", command=self._show_about)
        menubar.add_cascade(label="도움말", menu=help_m)
        self.root.config(menu=menubar)

        tk.Label(self.root,
                 text=header_banner_text(),
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Segoe UI", 20, "bold"), pady=10).pack(fill="x")

        # 상단 상태/AI 표시줄
        top_bar = tk.Frame(self.root, bg="#0f172a")
        top_bar.pack(fill="x")
        tk.Label(top_bar,
                 textvariable=self.top_status_var,
                 bg="#0f172a", fg="#e5e7eb",
                 font=("Segoe UI", 11),
                 pady=4).pack(side="left", padx=(10, 8))
        self.ai_status_label = tk.Label(
            top_bar,
            textvariable=self.ai_status_var,
            bg="#0f172a",
            fg=("#22c55e" if getattr(self.ai, "available", False) else "#f97316"),
            font=("Segoe UI", 10, "bold"),
            pady=4,
        )
        self.ai_status_label.pack(side="right", padx=(8, 8))
        self.ai_quota_badge_label = tk.Label(
            top_bar,
            textvariable=self.ai_quota_badge_var,
            bg="#14532d",
            fg="#dcfce7",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#14532d",
        )
        self.ai_quota_badge_label.pack(side="right", padx=(0, 6), pady=3)
        self.ai_request_badge_label = tk.Label(
            top_bar,
            textvariable=self.ai_request_badge_var,
            bg="#475569",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=4,
            relief="solid",
            bd=2,
            highlightthickness=1,
            highlightbackground="#475569",
        )
        self.ai_request_badge_label.pack(side="right", padx=(0, 6), pady=3)
        self.ai_usage_label = tk.Label(
            top_bar,
            textvariable=self.ai_usage_var,
            bg="#0f172a",
            fg="#94a3b8",
            font=("Segoe UI", 9),
            pady=4,
        )
        self.ai_usage_label.pack(side="left", padx=(6, 10))

        main_frame = tk.Frame(self.root, bg=UI_BG)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 왼쪽 패널 ────────────────────────────────────────────────────────
        left = tk.LabelFrame(main_frame, text="조성 입력 (주기율표)",
                             bg=PANEL_BG, fg="white",
                             font=("Segoe UI", 13, "bold"), padx=10, pady=10)
        left.pack(side="left", fill="y")

        # 주기율표: 금속 원소만(기본) 또는 전체 토글
        self.periodic_metal_only = tk.BooleanVar(value=True)
        tk.Checkbutton(
            left,
            text="금속만 보기",
            variable=self.periodic_metal_only,
            command=lambda: self._refresh_periodic_table(),
            bg=PANEL_BG,
            fg="white",
            selectcolor=PANEL_BG,
            activebackground=PANEL_BG,
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=20, sticky="w", pady=(0, 6))

        # 주기율표 영역은 별도 프레임에 생성(리프레시 시 spacer Label 누적 방지)
        self.ptable_frame = tk.Frame(left, bg=PANEL_BG)
        self.ptable_frame.grid(row=1, column=0, columnspan=20, sticky="w")
        self.build_periodic_table(self.ptable_frame)

        self.sum_label = tk.Label(left, text="총합: 0.00 %",
                                  bg=PANEL_BG, fg="white",
                                  font=("Segoe UI", 12, "bold"))
        self.sum_label.grid(row=9, column=0, columnspan=20, pady=(10, 2))

        # Sn 자동완성 행
        auto_f = tk.Frame(left, bg=PANEL_BG)
        auto_f.grid(row=10, column=0, columnspan=20, pady=(0, 4))
        tk.Label(auto_f, text="Sn 잔량 자동완성:",
                 bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        tk.Button(auto_f, text="Sn = 100 - 나머지",
                  command=self.auto_complete_sn,
                  bg="#064e3b", fg="white", width=18, height=1,
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=2)

        # 메인 버튼 행
        btn_f = tk.Frame(left, bg=PANEL_BG)
        btn_f.grid(row=11, column=0, columnspan=20, pady=4)
        for name, cmd in [
            ("분석 실행",     self.run_analysis_thread),
            ("연구소 모드",   lambda: self.set_mode("lab")),
            ("엔지니어 모드", lambda: self.set_mode("eng")),
            ("CSV 저장",     self.save_csv),
            ("초기화",       self.reset),
        ]:
            b = tk.Button(btn_f, text=name, command=cmd,
                          bg=BTN_BG, fg="white", width=12, height=2,
                          font=("Segoe UI", 10, "bold"))
            b.pack(side="left", padx=4)
            add_hover(b)

        # 분석 후 활성화 버튼 행
        extra_f = tk.Frame(left, bg=PANEL_BG)
        extra_f.grid(row=12, column=0, columnspan=20, pady=4)
        self.graph_btn  = self._make_disabled_btn(extra_f, "📈 융점 그래프",  self.show_melting_graph)
        self.radar_btn  = self._make_disabled_btn(extra_f, "🕸 레이더 차트",  self.show_radar_chart)
        self.reflow_btn = self._make_disabled_btn(extra_f, "🔥 리플로우 조건", self.show_reflow_conditions)
        self.profile48_btn = self._make_disabled_btn(extra_f, "📄 자동 프로파일", self.show_peak_profile, width=14)
        self.imc3d_btn = self._make_disabled_btn(extra_f, "🧱 IMC 3D", self.show_imc_3d_structure, width=10)

        # 유틸 버튼 행
        util_f = tk.Frame(left, bg=PANEL_BG)
        util_f.grid(row=13, column=0, columnspan=20, pady=4)
        for name, cmd, color in [
            ("⭐ 즐겨찾기 저장",    self.save_favorite,       "#78350f"),
            ("📂 즐겨찾기 불러오기", self.load_favorite,       "#1e3a5f"),
            ("⚖ 합금 비교",        self.open_compare_window, "#4c1d95"),
            ("🛡 RoHS 체크",       self.show_rohs_check,     "#7f1d1d"),
        ]:
            b = tk.Button(util_f, text=name, command=cmd,
                          bg=color, fg="white", width=16, height=2,
                          font=("Segoe UI", 9, "bold"))
            b.pack(side="left", padx=4)

        # ── 오른쪽 패널 ──────────────────────────────────────────────────────
        right = tk.LabelFrame(main_frame, text="분석 결과",
                              bg=PANEL_BG, fg="white",
                              font=("Segoe UI", 13, "bold"))
        right.pack(side="right", fill="both", expand=True, padx=10)

        # 결과 보기 옵션 (요약/상세 토글)
        self._last_render_raw = ""
        self._last_render_summary = None
        self.view_show_phase = tk.BooleanVar(value=True)
        self.view_show_imc = tk.BooleanVar(value=True)
        self.view_show_risk = tk.BooleanVar(value=True)
        self.view_show_roles = tk.BooleanVar(value=True)
        self.view_show_dopant = tk.BooleanVar(value=True)
        self.reco_goal = tk.StringVar(value="균형")
        self.wetting_temp_mode = tk.StringVar(value="AUTO(Liq+30)")
        self.result_font_size = tk.IntVar(value=13)
        self.result_font_family = tk.StringVar(value="Malgun Gothic")
        self.ai_result_mode_var = tk.StringVar(value="AI 모드: -")

        # 상단 옵션은 2줄로 분리(창 폭이 좁을 때 젖음 온도/검색이 안 보이는 문제 방지)
        opt_wrap = tk.Frame(right, bg=PANEL_BG)
        opt_wrap.pack(fill="x", padx=10, pady=(10, 0))
        opt_row1 = tk.Frame(opt_wrap, bg=PANEL_BG)
        opt_row1.pack(fill="x")
        opt_row_ai = tk.Frame(opt_wrap, bg=PANEL_BG)
        opt_row_ai.pack(fill="x", pady=(4, 0))
        opt_row2 = tk.Frame(opt_wrap, bg=PANEL_BG)
        opt_row2.pack(fill="x", pady=(4, 0))
        opt_row3 = tk.Frame(opt_wrap, bg=PANEL_BG)
        opt_row3.pack(fill="x", pady=(4, 0))
        opt_row4 = tk.Frame(opt_wrap, bg=PANEL_BG)
        opt_row4.pack(fill="x", pady=(4, 0))

        tk.Label(opt_row1, text="보기:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        tk.Label(
            opt_row_ai,
            textvariable=self.ai_result_mode_var,
            bg=PANEL_BG,
            fg="#93c5fd",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 10))

        tk.Label(opt_row_ai, text="문헌:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        lit_menu = ttk.Combobox(
            opt_row_ai,
            textvariable=self.literature_mode,
            values=["fast", "deep"],
            state="readonly",
            width=6,
        )
        lit_menu.pack(side="left", padx=(0, 10))
        lit_menu.bind(
            "<<ComboboxSelected>>",
            lambda _e: (self._update_ai_result_mode_label(), self._save_profile_settings()),
        )

        def _mk_chk(text, var):
            c = tk.Checkbutton(
                opt_row1, text=text, variable=var,
                command=self._rerender_last_result,
                bg=PANEL_BG, fg="white", selectcolor=PANEL_BG,
                activebackground=PANEL_BG, activeforeground="white",
                font=("Segoe UI", 9, "bold")
            )
            c.pack(side="left", padx=6)
            return c

        _mk_chk("상분석", self.view_show_phase)
        _mk_chk("IMC", self.view_show_imc)
        _mk_chk("리스크", self.view_show_risk)
        _mk_chk("원소역할", self.view_show_roles)
        _mk_chk("도펀트", self.view_show_dopant)

        # 추천 목표 선택 (비교 보고서/도펀트 추천에 반영)
        tk.Label(opt_row1, text="추천 목표:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(16, 6))
        goal_menu = ttk.Combobox(
            opt_row1,
            textvariable=self.reco_goal,
            values=["균형", "강도", "젖음", "저융점"],
            state="readonly",
            width=7,
        )
        goal_menu.pack(side="left", padx=(0, 6))
        goal_menu.bind("<<ComboboxSelected>>", lambda _e: self._rerender_compare_or_last())

        # 프로파일 프리셋 (금속/합금 계열별)
        tk.Label(opt_row1, text="프로파일:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(16, 6))
        preset_menu = ttk.Combobox(
            opt_row1,
            textvariable=self.profile_preset,
            values=[
                "AUTO",
                "SAC",
                "86(Sn-0.3Ag-0.7Cu)",
                "90(Sn-1.0Ag-0.7Cu)",
                "51(Sn-3Ag-0.5Cu-3Bi)",
                "92(Sn-0.3Ag-0.5Cu-3Bi)",
                "78(Sn-0.4Ag-57.6Bi)",
                "Sn-Bi(저융점)",
                "Sn-In(저융점)",
                "Sn-Pb",
                "Sn-Cu",
                "Sn-Ag",
                "범용",
            ],
            state="readonly",
            width=12,
        )
        preset_menu.pack(side="left", padx=(0, 6))
        preset_menu.bind("<<ComboboxSelected>>", lambda _e: (self._save_profile_settings(), self._rerender_compare_or_last()))

        # 프로파일 튜닝 버튼은 창 폭에 따라 가려질 수 있어 2줄(하단)에도 배치

        # 젖음 온도 선택 (PDF: 250~290C 온도별 측정치 반영)
        tk.Label(opt_row2, text="젖음 온도:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        wet_menu = ttk.Combobox(
            opt_row2,
            textvariable=self.wetting_temp_mode,
            values=["AUTO(Liq+30)", "250", "260", "270", "280", "290"],
            state="readonly",
            width=9,
        )
        wet_menu.pack(side="left", padx=(0, 10))
        wet_menu.bind("<<ComboboxSelected>>", lambda _e: self._rerender_compare_or_last())

        tk.Label(opt_row2, text="기판:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        sub_menu = ttk.Combobox(
            opt_row2,
            textvariable=self.imc_substrate,
            values=["Cu-OSP", "ENIG(Ni/Au)", "ImmAg", "ImmSn"],
            state="readonly",
            width=11,
        )
        sub_menu.pack(side="left", padx=(0, 8))
        sub_menu.bind("<<ComboboxSelected>>", lambda _e: self._on_imc_substrate_changed())

        tk.Label(opt_row2, text="IMC뷰:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        imc_view_menu = ttk.Combobox(
            opt_row2,
            textvariable=self.imc_view_style,
            values=["표준", "발표"],
            state="readonly",
            width=6,
        )
        imc_view_menu.pack(side="left", padx=(0, 8))
        imc_view_menu.bind("<<ComboboxSelected>>", lambda _e: self._save_profile_settings())

        # IMC는 입력 조성 강제 반영(프리셋 미사용)

        tk.Label(opt_row3, text="TAL:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        tal_mode_menu = ttk.Combobox(
            opt_row3,
            textvariable=self.imc_tal_mode,
            values=["AUTO(profile)", "기판기본", "사용자입력"],
            state="readonly",
            width=10,
        )
        tal_mode_menu.pack(side="left", padx=(0, 6))
        tal_mode_menu.bind("<<ComboboxSelected>>", lambda _e: self._on_imc_tal_mode_changed())

        tk.Label(opt_row3, text="기준:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 3))
        tal_ref_menu = ttk.Combobox(
            opt_row3,
            textvariable=self.imc_tal_ref,
            values=["Liquidus", "Liquidus+3C", "Liquidus+Δ"],
            state="readonly",
            width=9,
        )
        tal_ref_menu.pack(side="left", padx=(0, 4))
        tal_ref_menu.bind("<<ComboboxSelected>>", lambda _e: self._on_imc_tal_ref_changed())

        tk.Label(opt_row3, text="ΔC:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 2))
        tal_delta_entry = tk.Entry(
            opt_row3,
            textvariable=self.imc_tal_delta_c,
            width=4,
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            relief="flat",
        )
        tal_delta_entry.pack(side="left", padx=(0, 6))
        self.imc_tal_delta_entry = tal_delta_entry
        tal_delta_entry.bind("<FocusOut>", lambda _e: self._save_profile_settings())

        tk.Label(opt_row3, text="s:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 2))
        tal_entry = tk.Entry(
            opt_row3,
            textvariable=self.imc_tal_sec,
            width=5,
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            relief="flat",
        )
        tal_entry.pack(side="left", padx=(0, 8))
        self.imc_tal_entry = tal_entry
        tal_entry.bind("<FocusOut>", lambda _e: self._save_profile_settings())
        self._refresh_imc_tal_ui()

        tk.Button(
            opt_row3, text="튜닝",
            command=lambda: self.open_profile_tuner(),
            bg="#4c1d95", fg="white", width=5, height=1,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 12))

        # 결과창 글꼴 크기 조절
        tk.Label(opt_row3, text="글자:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        tk.Button(
            opt_row3, text="A-",
            command=lambda: self._adjust_result_font(-1),
            bg="#374151", fg="white", width=3, height=1,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            opt_row3, text="A+",
            command=lambda: self._adjust_result_font(+1),
            bg="#374151", fg="white", width=3, height=1,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 8))

        # 결과 유틸: 복사/검색
        tk.Button(
            opt_row4, text="복사",
            command=self.copy_result_to_clipboard,
            bg="#065f46", fg="white", width=6, height=1,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            opt_row4, text="출처복사",
            command=self.copy_sources_to_clipboard,
            bg="#0f766e", fg="white", width=8, height=1,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 8))

        # 결과창 전체화면 버튼은 상태 영역으로 이동(폭이 좁아도 항상 보이도록)

        self.find_var = tk.StringVar(value="")
        tk.Label(opt_row4, text="검색:", bg=PANEL_BG, fg="#9ca3af",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        find_entry = tk.Entry(opt_row4, textvariable=self.find_var, width=20,
                              bg="#0b1220", fg="#e5e7eb", insertbackground="#e5e7eb",
                              relief="flat")
        find_entry.pack(side="left", padx=(0, 6))
        tk.Button(
            opt_row4, text="다음",
            command=self.find_next_in_result,
            bg="#1e3a5f", fg="white", width=6, height=1,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))
        find_entry.bind("<Return>", lambda _e: self.find_next_in_result())

        # 진행 상태/실시간 로그 영역(항상 보이도록 결과창 위쪽에 고정)
        status_frame = tk.Frame(right, bg=PANEL_BG)
        status_frame.pack(fill="x", padx=10, pady=(8, 4))

        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(
            status_frame, maximum=100, variable=self.progress_var, length=600)
        self.progress_bar.pack(fill="x", pady=(0, 4))

        self.progress_label = tk.Label(
            status_frame, text="대기 중", bg=PANEL_BG, fg="white",
            font=("Segoe UI", 11))
        self.progress_label.pack(anchor="w", pady=(0, 4))

        # 웹과 동일한 스타일의 실시간 진행 로그
        live_wrap = tk.Frame(status_frame, bg=PANEL_BG)
        live_wrap.pack(fill="x")
        live_head = tk.Frame(live_wrap, bg=PANEL_BG)
        live_head.pack(fill="x")
        tk.Label(
            live_head,
            text="실시간 진행 로그",
            bg=PANEL_BG,
            fg="#93c5fd",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")
        self.live_elapsed_var = tk.StringVar(value="경과 00s")
        tk.Label(
            live_head,
            textvariable=self.live_elapsed_var,
            bg=PANEL_BG,
            fg="#a5b4fc",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 0))
        self._full_result_btn = tk.Button(
            live_head,
            text="결과 전체화면",
            command=self.toggle_full_result_window,
            bg="#374151",
            fg="white",
            width=12,
            height=1,
            font=("Segoe UI", 9, "bold"),
        )
        self._full_result_btn.pack(side="right")
        live_frame = tk.Frame(live_wrap, bg="#0b1220", bd=1, relief="solid")
        live_frame.pack(fill="x", pady=(3, 0))
        live_y = tk.Scrollbar(live_frame, orient="vertical")
        self.live_progress_box = tk.Text(
            live_frame,
            height=6,
            wrap="word",
            bg="#0b1220",
            fg="#cbd5e1",
            insertbackground="#cbd5e1",
            font=("Consolas", 9),
            yscrollcommand=live_y.set,
            state=tk.DISABLED,
        )
        live_y.config(command=self.live_progress_box.yview)
        live_y.pack(side="right", fill="y")
        self.live_progress_box.pack(side="left", fill="x", expand=True)

        # 결과창: 줄바꿈 없이 + 가로/세로 스크롤 (표/비교 결과 잘림 방지)
        result_frame = tk.Frame(right, bg=PANEL_BG)
        result_frame.pack(fill="both", expand=True, padx=10, pady=6)

        yscroll = tk.Scrollbar(result_frame, orient="vertical")
        xscroll = tk.Scrollbar(result_frame, orient="horizontal")

        self.result_box = tk.Text(
            result_frame,
            bg=TEXT_BG, fg=TEXT_FG,
            font=(self.result_font_family.get(), self.result_font_size.get()),
            wrap="none",
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
            undo=False,
        )
        yscroll.config(command=self.result_box.yview)
        xscroll.config(command=self.result_box.xview)

        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.result_box.pack(side="left", fill="both", expand=True)

        # 탭 스톱(픽셀) 기반 정렬: 한글 폰트 fallback에도 열 정렬 유지
        try:
            self.result_box.config(tabs=("120", "460", "780", "1040"))
        except Exception:
            pass
        try:
            self.result_box.config(spacing1=2, spacing3=2)
        except Exception:
            pass
        self._init_result_tags()
        self._apply_result_font()

    # ─────────────────────────────────────────────────────────────────────────
    # 결과 전체화면 토글
    # ─────────────────────────────────────────────────────────────────────────
    def toggle_full_result_window(self):
        # 이미 떠 있으면 닫기
        if self._full_result_win is not None and self._full_result_win.winfo_exists():
            try:
                self._full_result_win.destroy()
            except Exception:
                pass
            self._full_result_win = None
            return

        # 새 전체화면 창 생성
        win = tk.Toplevel(self.root)
        win.title("결과 전체화면 보기")
        win.configure(bg=UI_BG)
        try:
            win.state("zoomed")
        except Exception:
            pass

        frame = tk.Frame(win, bg=PANEL_BG)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        yscroll = tk.Scrollbar(frame, orient="vertical")
        xscroll = tk.Scrollbar(frame, orient="horizontal")

        box = tk.Text(
            frame,
            bg=TEXT_BG,
            fg=TEXT_FG,
            wrap="none",
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        yscroll.config(command=box.yview)
        xscroll.config(command=box.xview)

        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        box.pack(side="left", fill="both", expand=True)

        # 기존 결과 렌더링 로직과 동일한 스타일/정렬을 유지하기 위해
        # _render_result_text에서 저장해 둔 raw_text/summary를 활용해 재렌더링
        try:
            prev_box = self.result_box
            self.result_box = box
            # 메인 결과창과 동일한 탭/폰트/태그 설정
            try:
                box.config(tabs=("120", "460", "780", "1040"))
            except Exception:
                pass
            self._init_result_tags()
            self._apply_result_font()
            raw_text = getattr(self, "_last_render_raw", "")
            summary = getattr(self, "_last_render_summary", None)
            # 요약/본문 그대로 다시 그리기
            self._render_result_text(raw_text, summary=summary)
            box.config(state=tk.DISABLED)
        except Exception:
            try:
                # 폴백: 최소한 내용 텍스트만 복사
                raw = self.result_box.get("1.0", tk.END)
                box.insert(tk.END, raw)
                box.config(state=tk.DISABLED)
            except Exception:
                pass
        finally:
            # 기존 result_box 참조 복원
            try:
                self.result_box = prev_box
            except Exception:
                pass

        def _on_close():
            self._full_result_win = None
            if self._full_result_btn is not None:
                self._full_result_btn.config(text="결과 전체화면")
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)
        self._full_result_win = win

    # ─────────────────────────────────────────────────────────────────────────
    # 주기율표
    # ─────────────────────────────────────────────────────────────────────────
    def _refresh_periodic_table(self):
        # Destroy periodic table area only (sum_label 등 다른 위젯은 유지)
        frame = getattr(self, "ptable_frame", None)
        if frame is None:
            return
        try:
            for w in list(frame.winfo_children()):
                try:
                    w.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        self.buttons = {}
        self.build_periodic_table(frame)

    def build_periodic_table(self, frame):
        # Show only useful metals by default (faster alloy input)
        try:
            metal_only = bool(self.periodic_metal_only.get())
        except Exception:
            metal_only = True

        metal_elements = [
            # solder core
            "Sn", "Ag", "Cu", "Bi", "In", "Sb", "Ni", "Zn", "Pb",
            # RoHS / common additives
            "Hg", "Cd", "Cr", "Tl", "Al", "Ga", "Ge",
            "Fe", "Co", "Mn", "Mo",
            "Pd", "Pt", "Au",
            # chalcogens (from RoHS DB)
            "Se", "Te",
        ]

        if metal_only:
            # Keep "periodic table feel": keep original positions and leave blanks
            metal_set = set(metal_elements)
            table = [
                ["H",  "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "He"],
                ["Li", "Be", "",   "",   "",   "",   "",   "",   "",   "",   "",   "B",  "C",  "N",  "O",  "F",  "Ne"],
                ["Na", "Mg", "",   "",   "",   "",   "",   "",   "",   "",   "",   "Al", "Si", "P",  "S",  "Cl", "Ar"],
                ["K",  "Ca", "Sc", "Ti", "V",  "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr"],
                ["Rb", "Sr", "Y",  "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I",  "Xe"],
                ["Cs", "Ba", "La", "Hf", "Ta", "W",  "Re",  "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn"],
            ]

            start_row = 0
            for r, row in enumerate(table):
                for c, elem in enumerate(row):
                    if not elem:
                        continue
                    if elem not in metal_set:
                        # create a blank spacer to preserve the grid spacing
                        tk.Label(frame, text="", bg=PANEL_BG, width=5, height=2).grid(row=r + start_row, column=c, padx=2, pady=2)
                        continue
                    b = tk.Button(
                        frame,
                        text=elem,
                        width=5,
                        height=2,
                        bg=BTN_BG,
                        fg="white",
                        font=("Segoe UI", 10, "bold"),
                        command=lambda e=elem: self.enter_comp(e),
                    )
                    b.grid(row=r + start_row, column=c, padx=2, pady=2)
                    self.buttons[elem] = b
                    add_hover(b)
                    b.bind("<Button-3>", lambda e, el=elem: self.show_elem_menu(e, el))
            return

        # Full periodic table (fallback)
        table = [
            ["H",  "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "He"],
            ["Li", "Be", "",   "",   "",   "",   "",   "",   "",   "",   "",   "B",  "C",  "N",  "O",  "F",  "Ne"],
            ["Na", "Mg", "",   "",   "",   "",   "",   "",   "",   "",   "",   "Al", "Si", "P",  "S",  "Cl", "Ar"],
            ["K",  "Ca", "Sc", "Ti", "V",  "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr"],
            ["Rb", "Sr", "Y",  "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I",  "Xe"],
            ["Cs", "Ba", "La", "Hf", "Ta", "W",  "Re",  "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn"],
        ]
        for r, row in enumerate(table):
            for c, elem in enumerate(row):
                if not elem:
                    continue
                b = tk.Button(
                    frame,
                    text=elem,
                    width=5,
                    height=2,
                    bg=BTN_BG,
                    fg="white",
                    font=("Segoe UI", 10, "bold"),
                    command=lambda e=elem: self.enter_comp(e),
                )
                b.grid(row=r, column=c, padx=2, pady=2)
                self.buttons[elem] = b
                add_hover(b)
                b.bind("<Button-3>", lambda e, el=elem: self.show_elem_menu(e, el))

    # ─────────────────────────────────────────────────────────────────────────
    # 결과창 렌더링 (가독성/시안성 강화)
    # ─────────────────────────────────────────────────────────────────────────
    def _init_result_tags(self):
        # Tags for self.result_box
        t = self.result_box
        try:
            t.tag_config("SEP", foreground="#9ca3af")
            t.tag_config("TITLE", foreground="#e5e7eb")
            t.tag_config("SECTION", foreground="#93c5fd", background="#0b1220")
            t.tag_config("KEY", foreground="#fbbf24", background="#0b1220")
            t.tag_config("GOOD", foreground="#34d399")
            t.tag_config("WARN", foreground="#fbbf24")
            t.tag_config("BAD", foreground="#f87171")
            t.tag_config("MUTED", foreground="#9ca3af")
            t.tag_config("SEARCH", background="#7c3aed", foreground="#ffffff")
            t.tag_config("LINK", foreground="#60a5fa", underline=1)
        except Exception:
            pass

        # hyperlink behavior
        try:
            t.tag_bind("LINK", "<Enter>", lambda _e: t.config(cursor="hand2"))
            t.tag_bind("LINK", "<Leave>", lambda _e: t.config(cursor=""))
            t.tag_bind("LINK", "<Button-1>", self._open_link_at_cursor)
        except Exception:
            pass

    def _open_link_at_cursor(self, event=None):
        try:
            box = self.result_box
            idx = box.index("@%d,%d" % (event.x, event.y)) if event else box.index(tk.INSERT)
            tags = box.tag_names(idx)
            for tg in tags:
                if tg.startswith("SRC_") and tg in self._link_targets:
                    url = self._link_targets.get(tg)
                    if url:
                        webbrowser.open(url)
                        return
        except Exception:
            return

    def _apply_result_font(self):
        # Apply font consistently to widget + tags
        try:
            fam = self.result_font_family.get() or "Malgun Gothic"
            size = int(self.result_font_size.get() or 12)
            size = max(9, min(20, size))
            self.result_box.config(font=(fam, size))
            self.result_box.config(insertbackground="#e5e7eb")
            # tags
            self.result_box.tag_config("TITLE", font=(fam, max(size + 2, 12), "bold"))
            self.result_box.tag_config("SECTION", font=(fam, size, "bold"))
            self.result_box.tag_config("KEY", font=(fam, size, "bold"))
        except Exception:
            pass

    def _adjust_result_font(self, delta):
        try:
            cur = int(self.result_font_size.get() or 12)
            self.result_font_size.set(max(9, min(20, cur + int(delta))))
            self._apply_result_font()
        except Exception:
            return

    # ─────────────────────────────────────────────────────────────────────────
    # 프로파일 튜너(슬라이더/입력)
    # ─────────────────────────────────────────────────────────────────────────
    def open_profile_tuner(self):
        try:
            win = tk.Toplevel(self.root)
        except Exception as e:
            try:
                messagebox.showerror("오류", f"튜닝창 생성 실패: {e}")
            except Exception:
                pass
            return
        win.title("자동 프로파일 튜닝")
        win.configure(bg=UI_BG)
        win.geometry("640x740")

        tk.Label(
            win,
            text="Peak 기반 자동 프로파일 튜닝",
            bg=HEADER_BG, fg=HEADER_FG,
            font=("Segoe UI", 13, "bold"), pady=8
        ).pack(fill="x")

        # ─── 상단: 튜닝 목표 + 권장값 적용 ───
        goal_bar = tk.Frame(win, bg=UI_BG, padx=12, pady=8)
        goal_bar.pack(fill="x")

        tk.Label(goal_bar, text="튜닝 목표:", bg=UI_BG, fg="#e5e7eb",
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        try:
            from reflow_tune_engine import tuning_goal_options

            goal_options = tuning_goal_options()
        except Exception:
            goal_options = ["없음", "젖음(B)", "보이드(C)", "B+C", "슬럼프억제", "IMC최소"]
        try:
            from tkinter import ttk as _ttk
            goal_combo = _ttk.Combobox(
                goal_bar, textvariable=self.profile_goal,
                values=goal_options, state="readonly", width=14,
            )
            goal_combo.pack(side="left", padx=8)
        except Exception:
            tk.OptionMenu(goal_bar, self.profile_goal, *goal_options).pack(side="left", padx=8)

        body = tk.Frame(win, bg=UI_BG, padx=12, pady=4)
        body.pack(fill="both", expand=True)

        # 슬라이더 변수/엔트리 참조 모음 — 권장값 적용/검증 갱신용
        sliders: dict = {}

        def _resolved_preset_for_tune():
            """AUTO일 때 분석 결과로 실제 프리셋을 해석(가드레일·권장값 정확도)."""
            preset_name = (self.profile_preset.get() or "AUTO").strip()
            lr = getattr(self, "last_result", None)
            if isinstance(lr, dict):
                try:
                    prof = self._build_peak_profile_curve(lr)
                    return (prof.get("preset_name") or preset_name).strip()
                except Exception:
                    pass
            return preset_name

        def _refresh_validation(*_):
            try:
                tune = {k: float(sliders[k]["var"].get()) for k in sliders}
            except Exception:
                return
            preset_name = _resolved_preset_for_tune()
            res = self._validate_profile_tune(tune, preset_name)
            try:
                vbox.configure(state="normal")
                vbox.delete("1.0", tk.END)
                errs = res.get("errors") or []
                warns = res.get("warnings") or []
                oks = res.get("oks") or []
                if errs or warns:
                    pass
                elif oks:
                    vbox.insert(
                        tk.END,
                        "✅ 가드레일 통과 — 오류·경고 없음 (아래 ✓ 참고).\n\n",
                        "OK",
                    )
                else:
                    vbox.insert(
                        tk.END,
                        "검증 결과 없음 — AUTO는 분석 1회 후 확정되는 프리셋 기준으로 검증되거나,"
                        " 수동 프로필을 선택하세요.\n\n",
                        "WARN",
                    )
                for m in errs:
                    vbox.insert(tk.END, f"❌ {m}\n", "ERR")
                for m in warns:
                    vbox.insert(tk.END, f"⚠ {m}\n", "WARN")
                for m in oks:
                    vbox.insert(tk.END, f"✓ {m}\n", "OK")
                vbox.configure(state="disabled")
            except Exception:
                pass

        def add_row(label, key, frm, to, step=0.1):
            row = tk.Frame(body, bg=UI_BG)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=UI_BG, fg="#e5e7eb",
                     font=("Segoe UI", 10, "bold"), width=22, anchor="w").pack(side="left")
            v = tk.DoubleVar(value=float(self.profile_tune.get(key, frm)))

            def on_change(_=None):
                try:
                    self.profile_tune[key] = float(v.get())
                except Exception:
                    return
                _refresh_validation()

            s = tk.Scale(
                row, from_=frm, to=to, resolution=step,
                orient="horizontal", variable=v,
                length=260,
                bg=UI_BG, fg="#9ca3af", highlightthickness=0,
                troughcolor="#111827",
                activebackground="#2563eb",
                command=lambda _x: on_change(),
            )
            s.pack(side="left", padx=8)
            ent = tk.Entry(row, width=8, bg="#0b1220", fg="#e5e7eb",
                           insertbackground="#e5e7eb", relief="flat")
            ent.insert(0, f"{v.get():.2f}")
            ent.pack(side="left")

            def sync_from_entry(_e=None):
                try:
                    vv = float(ent.get().strip())
                    v.set(vv)
                    on_change()
                except Exception:
                    pass

            ent.bind("<Return>", sync_from_entry)
            ent.bind("<FocusOut>", sync_from_entry)

            def update_entry(*_):
                try:
                    ent.delete(0, tk.END)
                    ent.insert(0, f"{float(v.get()):.2f}")
                except Exception:
                    pass

            v.trace_add("write", update_entry)
            sliders[key] = {"var": v, "ent": ent, "min": frm, "max": to}

        add_row("램프업 속도 (℃/s)", "ramp_rate", 1.0, 2.0, step=0.05)
        add_row("예열 시간 (sec)", "preheat_time", 60, 140, step=1)
        add_row("액상선 이상 유지 (sec)", "over_liquidus_time", 25, 120, step=1)
        add_row("냉각 속도 (℃/s)", "cool_rate", 1.5, 4.0, step=0.05)
        add_row("피크 여유 (Liquidus+℃)", "peak_margin", 10, 55, step=1)

        # ─── 검증 결과 영역 ───
        v_wrap = tk.LabelFrame(win, text=" 가드레일 검증 ", bg=UI_BG, fg="#93c5fd",
                               font=("Segoe UI", 10, "bold"), padx=8, pady=4)
        v_wrap.pack(fill="both", expand=False, padx=12, pady=(8, 4))
        vbox = tk.Text(v_wrap, height=6, bg="#0b1220", fg="#e5e7eb",
                       insertbackground="#e5e7eb", relief="flat", wrap="word")
        vbox.pack(fill="both", expand=True)
        vbox.tag_config("ERR", foreground="#f87171")
        vbox.tag_config("WARN", foreground="#fbbf24")
        vbox.tag_config("OK", foreground="#86efac")
        vbox.configure(state="disabled")

        # ─── 권장값 적용 결과 (변경 전/후 diff) ───
        d_wrap = tk.LabelFrame(win, text=" 권장값 적용 변경 내역 ", bg=UI_BG, fg="#86efac",
                               font=("Segoe UI", 10, "bold"), padx=8, pady=4)
        d_wrap.pack(fill="both", expand=False, padx=12, pady=(0, 4))
        diff_box = tk.Text(d_wrap, height=5, bg="#0b1220", fg="#e5e7eb",
                           insertbackground="#e5e7eb", relief="flat", wrap="word")
        diff_box.pack(fill="both", expand=True)
        diff_box.tag_config("HEAD", foreground="#86efac",
                            font=("Segoe UI", 10, "bold"))
        diff_box.configure(state="disabled")

        def apply_recommended():
            preset_name = _resolved_preset_for_tune()
            goal = (self.profile_goal.get() or "없음").strip()
            rec = self._recommend_tune_for_goal(goal, preset_name)
            labels = {
                "ramp_rate": "1차 램프(℃/s)",
                "preheat_time": "프리히트(s)",
                "over_liquidus_time": "TAL(s)",
                "cool_rate": "냉각(℃/s)",
                "peak_margin": "피크 여유(℃)",
            }
            int_keys = {"preheat_time", "over_liquidus_time", "peak_margin"}
            diff_lines = []
            for k, v in rec.items():
                if k not in sliders:
                    continue
                try:
                    lo = sliders[k]["min"]
                    hi = sliders[k]["max"]
                    after = max(float(lo), min(float(hi), float(v)))
                    before = float(self.profile_tune.get(k, after))
                    sliders[k]["var"].set(after)
                    self.profile_tune[k] = after
                    if abs(after - before) > 0.005:
                        if k in int_keys:
                            diff_lines.append(
                                f"  · {labels.get(k,k)}: {before:.0f} → {after:.0f} "
                                f"({after-before:+.0f})"
                            )
                        else:
                            diff_lines.append(
                                f"  · {labels.get(k,k)}: {before:.2f} → {after:.2f} "
                                f"({after-before:+.2f})"
                            )
                except Exception:
                    pass
            _refresh_validation()
            try:
                diff_box.configure(state="normal")
                diff_box.delete("1.0", tk.END)
                head = f"권장값 적용됨 — 목표: {goal} · 프리셋: {preset_name}\n"
                diff_box.insert(tk.END, head, "HEAD")
                if diff_lines:
                    diff_box.insert(tk.END, "\n".join(diff_lines) + "\n")
                else:
                    diff_box.insert(tk.END, "  (변경된 항목 없음 — 현재값이 이미 권장값과 같음)\n")
                diff_box.configure(state="disabled")
            except Exception:
                pass

        tk.Button(goal_bar, text="권장값 적용",
                  command=apply_recommended,
                  bg="#16a34a", fg="white",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=10, pady=2).pack(side="left", padx=6)

        tk.Label(goal_bar,
                 text="(현재 합금 프리셋 + 목표 → 공급사 가이드 기반 권장값으로 한 번에 세팅)",
                 bg=UI_BG, fg="#9ca3af", font=("Segoe UI", 8)).pack(side="left", padx=4)

        btns = tk.Frame(win, bg=UI_BG)
        btns.pack(pady=10)

        def apply_and_close():
            try:
                tune = {k: float(sliders[k]["var"].get()) for k in sliders}
                res = self._validate_profile_tune(tune, _resolved_preset_for_tune())
                errs = list(res.get("errors") or [])
                warns = list(res.get("warnings") or [])
                if errs or warns:
                    chunks = []
                    if errs:
                        chunks.append("❌ 오류:\n· " + "\n· ".join(errs))
                    if warns:
                        chunks.append("⚠ 경고:\n· " + "\n· ".join(warns))
                    msg = (
                        "현재 세팅에 가드레일 알림이 있습니다.\n\n"
                        + "\n\n".join(chunks)
                        + "\n\n그래도 저장하고 적용하시겠습니까?"
                    )
                    if not messagebox.askyesno(
                        "가드레일 확인",
                        msg,
                        icon="warning",
                        parent=win,
                    ):
                        return
            except Exception:
                pass
            self._save_profile_settings()
            self._rerender_compare_or_last()
            win.destroy()

        tk.Button(btns, text="적용", command=apply_and_close,
                  bg="#2563eb", fg="white", width=10, height=2,
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
        tk.Button(btns, text="닫기", command=win.destroy,
                  bg=BTN_BG, fg="white", width=10, height=2,
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)

        _refresh_validation()

    def copy_result_to_clipboard(self):
        try:
            txt = self.result_box.get("1.0", tk.END).rstrip()
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            self.root.update()
            self.set_progress(self.progress_var.get(), "결과 복사 완료")
        except Exception:
            pass

    def _clear_search_highlight(self):
        try:
            self.result_box.tag_remove("SEARCH", "1.0", tk.END)
        except Exception:
            pass

    def find_next_in_result(self):
        """
        Simple find-next with highlight. Wraps around at end.
        """
        q = (self.find_var.get() or "").strip()
        if not q:
            return

        box = self.result_box
        self._clear_search_highlight()

        try:
            start = box.index(tk.INSERT)
        except Exception:
            start = "1.0"

        idx = box.search(q, start, stopindex=tk.END, nocase=True)
        if not idx:
            idx = box.search(q, "1.0", stopindex=tk.END, nocase=True)
            if not idx:
                self.set_progress(self.progress_var.get(), "검색 결과 없음")
                return

        end = f"{idx}+{len(q)}c"
        box.tag_add("SEARCH", idx, end)
        box.mark_set(tk.INSERT, end)
        box.see(idx)
        self.set_progress(self.progress_var.get(), f"찾음: {q}")

    def copy_sources_to_clipboard(self):
        """
        Copy DOI/URL sources (internet literature) to clipboard.
        """
        try:
            srcs = []

            def _collect_sources(obj):
                if not isinstance(obj, dict):
                    return
                ai_cited = obj.get("ai_cited_sources", [])
                retrieved = obj.get("retrieved_candidates", [])
                legacy = obj.get("ai_sources", [])
                if isinstance(ai_cited, list):
                    srcs.extend([f"[AI 인용] {str(x).strip()}" for x in ai_cited if str(x).strip()])
                if isinstance(retrieved, list):
                    srcs.extend([f"[자동 검색 후보] {str(x).strip()}" for x in retrieved if str(x).strip()])
                elif isinstance(legacy, list):
                    srcs.extend([f"[출처] {str(x).strip()}" for x in legacy if str(x).strip()])
            if isinstance(self.last_result, dict):
                _collect_sources(self.last_result)
            if isinstance(self.compare_result, dict):
                _collect_sources(self.compare_result)
            seen = set()
            out = []
            for x in srcs:
                if x in seen:
                    continue
                seen.add(x)
                out.append(x)
            if not out:
                messagebox.showinfo("출처", "복사할 출처가 없습니다. (AI 키/검색 실패 가능)")
                return
            txt = "\n".join(out)
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            self.root.update()
            messagebox.showinfo("출처", f"출처 {len(out)}건을 클립보드에 복사했습니다.")
        except Exception:
            try:
                messagebox.showerror("오류", "출처 복사 실패")
            except Exception:
                pass

    @staticmethod
    def _fmt_num(v, nd=1, default="N/A"):
        try:
            return f"{float(v):.{nd}f}"
        except Exception:
            return default

    def _render_result_text(self, raw_text, summary=None):
        """
        raw_text: 기존 보고서 문자열
        summary: dict 또는 None (핵심 요약 블록 렌더링용)
        """
        # remember last render inputs (for toggle re-render)
        self._last_render_raw = raw_text or ""
        self._last_render_summary = summary

        box = self.result_box
        box.config(state=tk.NORMAL)
        # Clear previous search highlight before re-rendering
        try:
            box.tag_remove("SEARCH", "1.0", tk.END)
        except Exception:
            pass
        box.delete("1.0", tk.END)

        # 1) 상단 핵심 요약 카드 (한눈에 보는 영역)
        if isinstance(summary, dict) and summary:
            sep = "─" * 68
            def _row(label, value, tag_label="KEY", tag_value=""):
                # Tab stops are fixed in result_box; use tabs for stable alignment.
                box.insert(tk.END, f"  {label}\t", tag_label)
                box.insert(tk.END, f"{value}\n", tag_value)

            box.insert(tk.END, "핵심 요약\n", "TITLE")
            box.insert(tk.END, f"{sep}\n\n", "SEP")
            if summary.get("type") == "compare":
                a = summary.get("A", {})
                b = summary.get("B", {})
                _row("합금 A", f"{a.get('name','N/A')}   (신뢰도 {self._fmt_num(a.get('confidence'),0)}% / 종합 {self._fmt_num(a.get('confidence_overall'),0)}%)")
                _row("합금 B", f"{b.get('name','N/A')}   (신뢰도 {self._fmt_num(b.get('confidence'),0)}% / 종합 {self._fmt_num(b.get('confidence_overall'),0)}%)")
                _row("융점", f"A {self._fmt_num(a.get('solidus'),1)}~{self._fmt_num(a.get('liquidus'),1)}℃   |   "
                            f"B {self._fmt_num(b.get('solidus'),1)}~{self._fmt_num(b.get('liquidus'),1)}℃")
                _row("피크", f"A {self._fmt_num(a.get('peak'),1)}℃   |   B {self._fmt_num(b.get('peak'),1)}℃")
                ain = a.get("alloy_inference") if isinstance(a.get("alloy_inference"), dict) else {}
                binf = b.get("alloy_inference") if isinstance(b.get("alloy_inference"), dict) else {}
                if (ain.get("liquidus") is not None) or (binf.get("liquidus") is not None):
                    _row(
                        "데이터 추론 L/피크",
                        f"A L {self._fmt_num(ain.get('liquidus'),1)}℃ ≈피크 {self._fmt_num(ain.get('recommended_peak_c'),1)}℃   |   "
                        f"B L {self._fmt_num(binf.get('liquidus'),1)}℃ ≈피크 {self._fmt_num(binf.get('recommended_peak_c'),1)}℃",
                        tag_label="KEY",
                    )
                pma = a.get("profile_metrics") if isinstance(a.get("profile_metrics"), dict) else {}
                pmb = b.get("profile_metrics") if isinstance(b.get("profile_metrics"), dict) else {}
                if pma or pmb:
                    _row(
                        "체류시간",
                        f"A TAL {self._fmt_num(pma.get('tal_s'),1)}s({pma.get('tal_ref','Liq')}={self._fmt_num(pma.get('tal_thr_c'),1)}℃), "
                        f"S~L {self._fmt_num(pma.get('tsl_s'),1)}s, Peak-5 {self._fmt_num(pma.get('tpk_s'),1)}s"
                        f"   |   "
                        f"B TAL {self._fmt_num(pmb.get('tal_s'),1)}s({pmb.get('tal_ref','Liq')}={self._fmt_num(pmb.get('tal_thr_c'),1)}℃), "
                        f"S~L {self._fmt_num(pmb.get('tsl_s'),1)}s, Peak-5 {self._fmt_num(pmb.get('tpk_s'),1)}s",
                        tag_label="KEY",
                    )
                # Wetting (temperature-dependent measurement model)
                if isinstance(a.get("props"), dict) or isinstance(b.get("props"), dict):
                    pa = a.get("props") if isinstance(a.get("props"), dict) else {}
                    pb = b.get("props") if isinstance(b.get("props"), dict) else {}
                    if pa.get("wetting_fmax_pred_mn") or pb.get("wetting_fmax_pred_mn"):
                        na = pa.get("wetting_neighbors", []) if isinstance(pa.get("wetting_neighbors", []), list) else []
                        nb = pb.get("wetting_neighbors", []) if isinstance(pb.get("wetting_neighbors", []), list) else []
                        def _nei_txt(neis):
                            out = []
                            for x in (neis or [])[:3]:
                                if not isinstance(x, dict):
                                    continue
                                name = x.get("name", "N/A")
                                dist = x.get("dist", None)
                                if dist is None:
                                    out.append(f"{name}")
                                else:
                                    out.append(f"{name}(d={self._fmt_num(dist,2)})")
                            return ", ".join(out)
                        _row(
                            "젖음(예측)",
                            f"A fMAX {self._fmt_num(pa.get('wetting_fmax_pred_mn'),2)} mN / "
                            f"T0 {self._fmt_num(pa.get('wetting_t0_pred_s'),2)} s @ {self._fmt_num(pa.get('wetting_temp_c'),0)}℃"
                            f"   |   "
                            f"B fMAX {self._fmt_num(pb.get('wetting_fmax_pred_mn'),2)} mN / "
                            f"T0 {self._fmt_num(pb.get('wetting_t0_pred_s'),2)} s @ {self._fmt_num(pb.get('wetting_temp_c'),0)}℃"
                            f"   |   근접DB A: {_nei_txt(na) if na else 'N/A'} / B: {_nei_txt(nb) if nb else 'N/A'}",
                            tag_label="KEY",
                        )
            else:
                best = summary.get("best_name", "N/A")
                conf = summary.get("confidence", 0)
                _row("최적 일치", f"{best}   (신뢰도 {self._fmt_num(conf,0)}%)")
                # Overall confidence + provenance (DB/Model/AI)
                conf_overall = summary.get("confidence_overall", None)
                if conf_overall is not None:
                    _row("신뢰도(종합)", f"{self._fmt_num(conf_overall,0)}%", tag_label="KEY")

                ev = summary.get("evidence") if isinstance(summary.get("evidence"), dict) else {}
                if ev:
                    mel = ev.get("melting") if isinstance(ev.get("melting"), dict) else {}
                    wet = ev.get("wetting") if isinstance(ev.get("wetting"), dict) else {}
                    ai = ev.get("ai") if isinstance(ev.get("ai"), dict) else {}

                    mel_src = mel.get("source", "N/A")
                    mel_dist = mel.get("best_dist", None)
                    mel_forced = "YES" if mel.get("forced_db") else "NO"
                    wet_src = wet.get("source", "N/A")
                    wet_nei = wet.get("neighbors", []) if isinstance(wet.get("neighbors"), list) else []

                    def _nei_txt(neis):
                        out = []
                        for x in (neis or [])[:3]:
                            if not isinstance(x, dict):
                                continue
                            name = x.get("name", "N/A")
                            dist = x.get("dist", None)
                            if dist is None:
                                out.append(f"{name}")
                            else:
                                out.append(f"{name}(d={self._fmt_num(dist,2)})")
                        return ", ".join(out)

                    ai_on = "ON" if ai.get("enabled") else "OFF"
                    ai_used = "YES" if ai.get("used_this_request") else "NO"
                    _row(
                        "근거(출처)",
                        f"융점={mel_src}(forced={mel_forced}, d={self._fmt_num(mel_dist,3) if mel_dist is not None else 'N/A'})   |   "
                        f"젖음={wet_src}({(_nei_txt(wet_nei) if wet_nei else 'N/A')})   |   AI={ai_on}, used={ai_used}",
                        tag_label="KEY",
                    )
                    std_refs = ev.get("standards_refs") if isinstance(ev.get("standards_refs"), list) else []
                    if std_refs:
                        parts = []
                        for x in std_refs:
                            if not isinstance(x, dict):
                                continue
                            fam = str(x.get("family", "") or "").strip()
                            sid = str(x.get("id", "") or "").strip()
                            note = str(x.get("note", "") or "").strip()
                            if fam and sid:
                                parts.append(f"{fam} {sid}({note})" if note else f"{fam} {sid}")
                        if parts:
                            _row(
                                "표준 참고(IPC·JIS)",
                                "  |  ".join(parts[:10])
                                + (f"  |  (+{len(parts) - 10})" if len(parts) > 10 else ""),
                                tag_label="KEY",
                            )

                # Internet sources split: AI-cited vs retrieved candidates
                ai_cited = summary.get("ai_cited_sources", [])
                retrieved = summary.get("retrieved_candidates", [])
                legacy = summary.get("ai_sources", [])
                if not isinstance(ai_cited, list):
                    ai_cited = []
                if not isinstance(retrieved, list):
                    retrieved = []
                if not isinstance(legacy, list):
                    legacy = []
                ai_cited = [str(x).strip() for x in ai_cited if str(x).strip()]
                retrieved = [str(x).strip() for x in retrieved if str(x).strip()]
                if not retrieved and legacy:
                    retrieved = [str(x).strip() for x in legacy if str(x).strip()]
                if ai_cited or retrieved:
                    self._link_targets = {}
                    _row("문헌/출처", "", tag_label="KEY")

                    if ai_cited:
                        box.insert(tk.END, "  [AI 인용 출처]\n", "KEY")
                        for i, s in enumerate(ai_cited[:5], start=1):
                            target = s
                            if s.upper().startswith("DOI:"):
                                doi = s[4:].strip()
                                if doi:
                                    target = "https://doi.org/" + doi
                            if s.upper().startswith("URL:"):
                                u = s[4:].strip()
                                if u:
                                    target = u
                            tag = f"SRC_AI_{i}"
                            self._link_targets[tag] = target
                            box.insert(tk.END, f"    {i}) ", "MUTED")
                            box.insert(tk.END, f"{s}\n", ("LINK", tag))
                        if len(ai_cited) > 5:
                            box.insert(tk.END, f"    (+{len(ai_cited)-5} 더 있음)\n", "MUTED")
                    else:
                        box.insert(tk.END, "  [AI 인용 출처] 없음\n", "MUTED")

                    if retrieved:
                        box.insert(tk.END, "  [자동 검색 후보]\n", "KEY")
                        for i, s in enumerate(retrieved[:5], start=1):
                            target = s
                            if s.upper().startswith("DOI:"):
                                doi = s[4:].strip()
                                if doi:
                                    target = "https://doi.org/" + doi
                            if s.upper().startswith("URL:"):
                                u = s[4:].strip()
                                if u:
                                    target = u
                            tag = f"SRC_RET_{i}"
                            self._link_targets[tag] = target
                            box.insert(tk.END, f"    {i}) ", "MUTED")
                            box.insert(tk.END, f"{s}\n", ("LINK", tag))
                        if len(retrieved) > 5:
                            box.insert(tk.END, f"    (+{len(retrieved)-5} 더 있음)  '출처복사'로 전체 복사 가능\n", "MUTED")
                    else:
                        box.insert(tk.END, "  [자동 검색 후보] 없음\n", "MUTED")
                # DB direct match info (forced) + best_dist
                md = summary.get("melting_detail") if isinstance(summary.get("melting_detail"), dict) else {}
                if md:
                    forced = "YES" if md.get("forced_db") else "NO"
                    dist = md.get("best_dist", None)
                    if dist is not None:
                        _row("DB 직접 일치", f"forced={forced}   best_dist={self._fmt_num(dist,3)}")
                _row("융점", f"Solidus {self._fmt_num(summary.get('solidus'),1)}℃   /   "
                           f"Liquidus {self._fmt_num(summary.get('liquidus'),1)}℃   /   "
                           f"Peak {self._fmt_num(summary.get('peak'),1)}℃")
                ain = summary.get("alloy_inference") if isinstance(summary.get("alloy_inference"), dict) else {}
                if ain.get("solidus") is not None and ain.get("liquidus") is not None:
                    nei = ain.get("neighbors") if isinstance(ain.get("neighbors"), list) else []
                    nei_txt = ", ".join(
                        f"{n.get('name','?')}(w={self._fmt_num(n.get('weight'),3)})"
                        for n in nei[:3]
                        if isinstance(n, dict)
                    ) or "N/A"
                    wl = ain.get("element_weights_liquidus") if isinstance(ain.get("element_weights_liquidus"), dict) else {}
                    wtxt = ", ".join(f"{k}:{v}" for k, v in sorted(wl.items())[:8]) if wl else "—"
                    _row(
                        "데이터 추론(3-NN)",
                        f"S {self._fmt_num(ain.get('solidus'),1)}℃ / L {self._fmt_num(ain.get('liquidus'),1)}℃ / "
                        f"권장피크≈{self._fmt_num(ain.get('recommended_peak_c'),1)}℃   |   이웃: {nei_txt}",
                        tag_label="KEY",
                    )
                    _row("액상선 민감도(℃/wt%·근사)", wtxt, tag_label="KEY")
                    try:
                        ds = float(ain.get("solidus", 0)) - float(summary.get("solidus", 0) or 0)
                        dl = float(ain.get("liquidus", 0)) - float(summary.get("liquidus", 0) or 0)
                        rpk = ain.get("recommended_peak_c")
                        pk = summary.get("peak")
                        dpp = ""
                        if rpk is not None and pk is not None:
                            dpp = f" · 권장피크(추)−엔진피크 {float(rpk) - float(pk):+.1f}℃"
                        _row("추론−하이브리드 Δ", f"고상 {ds:+.2f}℃ · 액상 {dl:+.2f}℃{dpp}", tag_label="KEY")
                    except Exception:
                        pass
                    pr = str(ain.get("process_report") or "").strip()
                    if pr:
                        box.insert(tk.END, "\n", "SEP")
                        box.insert(tk.END, pr + "\n", "MUTED")
                pm = summary.get("profile_metrics") if isinstance(summary.get("profile_metrics"), dict) else {}
                if pm:
                    _row(
                        "체류시간",
                        f"TAL {self._fmt_num(pm.get('tal_s'),1)} s ({pm.get('tal_ref','Liquidus')}={self._fmt_num(pm.get('tal_thr_c'),1)}℃)   |   "
                        f"S~L {self._fmt_num(pm.get('tsl_s'),1)} s   |   Peak-5 {self._fmt_num(pm.get('tpk_s'),1)} s",
                        tag_label="KEY",
                    )
                props = summary.get("props", {}) if isinstance(summary.get("props"), dict) else {}
                if props:
                    _row("물성", f"인장 {self._fmt_num(props.get('tensile_strength'),1)} MPa   |   "
                               f"전단 {self._fmt_num(props.get('shear_strength'),1)} MPa   |   "
                               f"연신 {self._fmt_num(props.get('elongation'),1)} %")
                    if props.get("wetting_fmax_pred_mn"):
                        neis = props.get("wetting_neighbors", []) if isinstance(props.get("wetting_neighbors", []), list) else []
                        def _nei_txt(neis):
                            out = []
                            for x in (neis or [])[:3]:
                                if not isinstance(x, dict):
                                    continue
                                name = x.get("name", "N/A")
                                dist = x.get("dist", None)
                                if dist is None:
                                    out.append(f"{name}")
                                else:
                                    out.append(f"{name}(d={self._fmt_num(dist,2)})")
                            return ", ".join(out)
                        _wt_basis = ""
                        if props.get("wetting_temp_basis") == "auto_liq_plus_30" and props.get("wetting_temp_target_c") is not None:
                            _wt_basis = (
                                f"   |   기준: 액상선+30≈{self._fmt_num(props.get('wetting_temp_target_c'),1)}℃→측정 DB "
                                f"{self._fmt_num(props.get('wetting_temp_c'),0)}℃"
                            )
                        elif props.get("wetting_temp_basis") == "compare_shared":
                            _wt_basis = (
                                f"   |   기준: 비교 공통 {self._fmt_num(props.get('wetting_temp_c'),0)}℃"
                            )
                        elif props.get("wetting_temp_basis") == "user":
                            _wt_basis = "   |   기준: 선택 온도(측정 DB 맞춤)"
                        _row(
                            "젖음(예측)",
                            f"fMAX {self._fmt_num(props.get('wetting_fmax_pred_mn'),2)} mN   /   "
                            f"T0 {self._fmt_num(props.get('wetting_t0_pred_s'),2)} s   @ {self._fmt_num(props.get('wetting_temp_c'),0)}℃"
                            f"{_wt_basis}"
                            f"   |   근접DB: {_nei_txt(neis) if neis else 'N/A'}",
                            tag_label="KEY",
                        )
            box.insert(tk.END, f"{sep}\n\n", "SEP")

        # 2) 본문 보고서: 섹션 필터링 + 라인별 하이라이트
        def _section_kind(title_line: str):
            t = title_line.strip()
            if not (t.startswith("[") and "]" in t[:28]):
                return None
            if ("상변태" in t) or ("Phase" in t) or ("상분석" in t):
                return "phase"
            if "IMC" in t:
                return "imc"
            if "리스크" in t or "Risk" in t:
                return "risk"
            if ("원소 역할" in t) or ("구성 원소" in t) or ("역할" in t and "도펀트" not in t):
                return "roles"
            if "도펀트" in t or "dopant" in t.lower():
                return "dopant"
            return "other"

        show_map = {
            "phase": bool(self.view_show_phase.get()),
            "imc": bool(self.view_show_imc.get()),
            "risk": bool(self.view_show_risk.get()),
            "roles": bool(self.view_show_roles.get()),
            "dopant": bool(self.view_show_dopant.get()),
            "other": True,
        }

        text = raw_text or ""
        current_kind = "other"
        keep_section = True

        for line in text.splitlines(True):
            s = line.strip()
            tag = ""
            if not s:
                box.insert(tk.END, line)
                continue

            if s.startswith(("=", "─")):
                tag = "SEP"
            elif s.startswith("[") and "]" in s[:24]:
                tag = "SECTION"
                k = _section_kind(s)
                if k is not None:
                    current_kind = k
                    keep_section = show_map.get(current_kind, True)
            elif "🚨" in s or "ERROR" in s or "오류" in s:
                tag = "BAD"
            elif "⚠" in s or "주의" in s or "경고" in s:
                tag = "WARN"
            elif "✅" in s:
                tag = "GOOD"
            elif "▲" in s:
                tag = "KEY"

            if keep_section:
                box.insert(tk.END, line, tag)

        box.see("1.0")
        box.config(state=tk.NORMAL)

    def _rerender_last_result(self):
        # called by view toggles
        try:
            self._render_result_text(self._last_render_raw, summary=self._last_render_summary)
        except Exception:
            # never break UI on toggles
            pass

    def _rerender_compare_or_last(self):
        """
        목표(goal) 변경 시:
        - 비교 결과가 있으면 비교 보고서를 다시 생성해서 렌더링
        - 아니면 마지막 결과를 그대로 재렌더
        """
        try:
            if self.last_result and self.compare_result and self.comp and self.compare_comp:
                # apply wetting override for display (no full re-analysis)
                self._apply_compare_shared_wetting(self.last_result, self.compare_result)
                output = self._build_compare_report(self.comp, self.compare_comp, self.last_result, self.compare_result)
                summary = {
                    "type": "compare",
                    "A": {
                        "name": ((self.last_result.get("best") or {}).get("name", "합금 A") if isinstance(self.last_result, dict) else "합금 A"),
                        "confidence": (self.last_result.get("confidence", 0) if isinstance(self.last_result, dict) else 0),
                        "confidence_overall": (self.last_result.get("confidence_overall", 0) if isinstance(self.last_result, dict) else 0),
                        "solidus": (self.last_result.get("solidus", 0) if isinstance(self.last_result, dict) else 0),
                        "liquidus": (self.last_result.get("liquidus", 0) if isinstance(self.last_result, dict) else 0),
                        "peak": (self.last_result.get("peak", 0) if isinstance(self.last_result, dict) else 0),
                        "profile_metrics": (self._profile_metrics_for_result(self.last_result) if isinstance(self.last_result, dict) else {}),
                        "props": (self.last_result.get("props") if isinstance(self.last_result, dict) else {}),
                        "alloy_inference": (
                            self.last_result.get("alloy_inference")
                            if isinstance(self.last_result, dict)
                            else {}
                        ),
                    },
                    "B": {
                        "name": ((self.compare_result.get("best") or {}).get("name", "합금 B") if isinstance(self.compare_result, dict) else "합금 B"),
                        "confidence": (self.compare_result.get("confidence", 0) if isinstance(self.compare_result, dict) else 0),
                        "confidence_overall": (self.compare_result.get("confidence_overall", 0) if isinstance(self.compare_result, dict) else 0),
                        "solidus": (self.compare_result.get("solidus", 0) if isinstance(self.compare_result, dict) else 0),
                        "liquidus": (self.compare_result.get("liquidus", 0) if isinstance(self.compare_result, dict) else 0),
                        "peak": (self.compare_result.get("peak", 0) if isinstance(self.compare_result, dict) else 0),
                        "profile_metrics": (self._profile_metrics_for_result(self.compare_result) if isinstance(self.compare_result, dict) else {}),
                        "props": (self.compare_result.get("props") if isinstance(self.compare_result, dict) else {}),
                        "alloy_inference": (
                            self.compare_result.get("alloy_inference")
                            if isinstance(self.compare_result, dict)
                            else {}
                        ),
                    },
                }
                self._render_result_text(output, summary=summary)
            else:
                if self.last_result:
                    self._apply_wetting_override_to_result(self.last_result)
                self._rerender_last_result()
        except Exception:
            self._rerender_last_result()

    def _wetting_temp_user_override(self):
        mode = (self.wetting_temp_mode.get() or "AUTO(Liq+30)").strip()
        if mode == "AUTO(peak)":
            mode = "AUTO(Liq+30)"
        if mode.startswith("AUTO"):
            return None
        try:
            return float(int(mode))
        except Exception:
            return None

    def _apply_wetting_props_from_details(self, r, details):
        if not isinstance(r, dict) or not isinstance(details, dict):
            return
        props = r.get("props") if isinstance(r.get("props"), dict) else {}
        props["wetting_temp_c"] = float(details.get("wetting_temp_c", 0.0) or 0.0)
        props["wetting_fmax_pred_mn"] = float(details.get("fmax_pred_mn", 0.0) or 0.0)
        props["wetting_t0_pred_s"] = float(details.get("t0_pred_s", 0.0) or 0.0)
        if isinstance(details.get("neighbors"), list):
            props["wetting_neighbors"] = details.get("neighbors")
        if details.get("wetting_temp_basis"):
            props["wetting_temp_basis"] = details.get("wetting_temp_basis")
        if details.get("wetting_temp_target_c") is not None:
            props["wetting_temp_target_c"] = float(details.get("wetting_temp_target_c"))
        r["props"] = props

    def _apply_compare_shared_wetting(self, r_a, r_b):
        """비교 모드: A·B 동일 젖음 온도로 props만 갱신 (단일 조성별 auto 금지)."""
        if not isinstance(r_a, dict) or not isinstance(r_b, dict):
            return
        comp_a = dict(self.comp) if self.comp else (r_a.get("norm") or {})
        comp_b = dict(self.compare_comp) if self.compare_comp else (r_b.get("norm") or {})
        try:
            wet_t, wet_basis = self.analyzer.compare_wetting_temp_c(
                comp_a, comp_b, self._wetting_temp_user_override()
            )
        except Exception:
            return
        for r in (r_a, r_b):
            norm = r.get("norm") if isinstance(r.get("norm"), dict) else {}
            solidus = float(r.get("solidus", 0.0) or 0.0)
            liquidus = float(r.get("liquidus", 0.0) or 0.0)
            try:
                details = self.analyzer.models._predict_wetting_details(
                    norm,
                    solidus,
                    liquidus,
                    wetting_temp_c=wet_t,
                    wetting_temp_basis=wet_basis,
                )
                self._apply_wetting_props_from_details(r, details)
            except Exception:
                pass

    def _apply_wetting_override_to_result(self, r):
        """
        Recompute only wetting-related fields in r['props'] based on selected temperature.
        Keeps other properties unchanged.
        """
        if not isinstance(r, dict):
            return
        norm = r.get("norm") if isinstance(r.get("norm"), dict) else {}
        solidus = float(r.get("solidus", 0.0) or 0.0)
        liquidus = float(r.get("liquidus", 0.0) or 0.0)
        wet_arg = self._wetting_temp_user_override()

        try:
            details = self.analyzer.models._predict_wetting_details(
                norm, solidus, liquidus, wetting_temp_c=wet_arg
            )
            self._apply_wetting_props_from_details(r, details)
        except Exception:
            # leave existing values
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # 조성 입력
    # ─────────────────────────────────────────────────────────────────────────
    def enter_comp(self, elem):
        val = simpledialog.askstring("입력", f"{elem} (%) 값을 입력하세요")
        if val is None:
            return
        try:
            v = float(val)
            if v < 0:
                raise ValueError
            self.comp[elem] = v
            if elem in self.buttons:
                self.buttons[elem].config(text=f"{elem}\n{v:.2f}%")
            self.update_sum()
        except Exception:
            messagebox.showerror("오류", "0 이상의 숫자를 입력하세요.")

    def update_sum(self):
        total = sum(self.comp.values())
        color = ("#34d399" if abs(total - 100) <= 0.5
                 else "#fbbf24" if 95 <= total <= 105
                 else "#f87171")
        self.sum_label.config(text=f"총합: {total:.2f} %", fg=color)

    def auto_complete_sn(self):
        others = sum(v for k, v in self.comp.items() if k != "Sn")
        if others >= 100:
            messagebox.showwarning("자동완성 불가",
                f"Sn 외 원소 합계 {others:.2f}% >= 100%\n조성을 다시 확인하세요.")
            return
        sn_val = round(100.0 - others, 4)
        self.comp["Sn"] = sn_val
        if "Sn" in self.buttons:
            self.buttons["Sn"].config(text=f"Sn\n{sn_val:.2f}%")
        self.update_sum()

    def show_elem_menu(self, event, elem):
        menu = tk.Menu(self.root, tearoff=0, bg="#374151", fg="white",
                       activebackground="#2563eb", activeforeground="white",
                       font=("Segoe UI", 10))
        if elem in self.comp:
            cur = self.comp[elem]
            menu.add_command(label=f"  ✏️  {elem} 수정  (현재 {cur:.2f}%)",
                             command=lambda: self.enter_comp(elem))
            menu.add_separator()
            menu.add_command(label=f"  🗑️  {elem} 삭제",
                             command=lambda: self.delete_elem(elem))
        else:
            menu.add_command(label=f"  ➕  {elem} 입력",
                             command=lambda: self.enter_comp(elem))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def delete_elem(self, elem):
        if elem not in self.comp:
            return
        del self.comp[elem]
        if elem in self.buttons:
            self.buttons[elem].config(text=elem)
        self.update_sum()

    # ─────────────────────────────────────────────────────────────────────────
    def set_mode(self, m):
        self.mode = m
        messagebox.showinfo("모드 변경",
            f"{'연구소' if m == 'lab' else '엔지니어'} 모드로 변경되었습니다.")

    # ─────────────────────────────────────────────────────────────────────────
    # 분석 핵심 로직
    # ─────────────────────────────────────────────────────────────────────────
    def _apply_db_weighted_correction(self, props, norm, score):
        db_pred = predict_from_db(norm)
        if not db_pred:
            return props
        db_w  = max(0.15, min(0.75, 1.0 / (1.0 + score / 5.0)))
        mdl_w = 1.0 - db_w
        mapping = {"tensile_strength": "tensile", "yield_strength": "yield_strength",
                   "elongation": "elongation", "shear_strength": "shear"}
        corrected = dict(props)
        for mk, dk in mapping.items():
            dv, mv = db_pred.get(dk), corrected.get(mk)
            if dv is not None and mv is not None:
                corrected[mk] = mv * mdl_w + dv * db_w
        return corrected

    def _run_single(self, comp, progress_cb=None):
        lit_mode = (self.literature_mode.get() if hasattr(self.literature_mode, "get") else str(self.literature_mode))
        r = self.analyzer.analyze_all(
            comp,
            mode=self.mode,
            progress_cb=progress_cb,
            literature_mode=lit_mode or "fast",
        )
        if not isinstance(r, dict):
            return {}
        # 호환성 안전장치(구 버전 analyzer 반환 대비)
        if "knn" not in r:
            try:
                norm = r.get("norm") if isinstance(r.get("norm"), dict) else self.analyzer.normalize(comp)
                r["knn"] = self.analyzer.find_knn(norm, k=3)
            except Exception:
                r["knn"] = []
        return r

    # ─────────────────────────────────────────────────────────────────────────
    # 단일 분석
    # ─────────────────────────────────────────────────────────────────────────
    def run_analysis_thread(self):
        th = threading.Thread(target=self.run_analysis)
        th.daemon = True
        th.start()

    def run_analysis(self):
        if not self.comp:
            messagebox.showwarning("경고", "먼저 조성을 입력하세요.")
            self._analysis_live_enabled = False
            return
        self._set_ai_request_badge(None)
        self.result_box.delete("1.0", tk.END)
        self._reset_live_progress_log("단일 분석")
        self.set_progress(0, "분석 시작...")
        self._refresh_ai_engine(force=True)
        self._update_ai_result_mode_label()
        try:
            self.set_progress(20, "조성 분석 중...")
            r = self._run_single(self.comp, progress_cb=self.set_progress)
        except Exception as e:
            log_exception("GUI.run_analysis", e)
            try:
                messagebox.showerror("오류", f"분석 실패: {e}")
            except Exception:
                pass
            self._finish_live_progress_log(ok=False)
            return

        self.last_result = r
        self._set_ai_request_badge(bool(r.get("ai_used_this_request", False)) if isinstance(r, dict) else None)
        self._refresh_ai_usage_ui()
        self._apply_wetting_override_to_result(self.last_result)
        self._refresh_imc_tal_ui()
        comp_str = composition_to_string(self.comp)
        knn = r["knn"]
        self.set_progress(88, "분석 결과 정리 중...")
        self.set_progress(92, "보고서 템플릿 생성 중...")
        if self.mode == "lab":
            body         = self.ai.build_lab_report(comp_str, r, knn)
            final_output = self.reporter.lab_output(body)
        else:
            body         = self.ai.build_eng_report(comp_str, r, knn)
            final_output = self.reporter.eng_output(body)

        self.set_progress(97, "결과 렌더링 중...")
        self.root.after(0, self._enable_result_btns)
        self.set_progress(100, "완료")
        self._finish_live_progress_log(ok=True)
        summary = {
            "best_name": (r.get("best") or {}).get("name", "N/A") if isinstance(r, dict) else "N/A",
            "confidence": (r.get("confidence", 0) if isinstance(r, dict) else 0),
            "confidence_overall": (r.get("confidence_overall", 0) if isinstance(r, dict) else 0),
            "solidus": (r.get("solidus", 0) if isinstance(r, dict) else 0),
            "liquidus": (r.get("liquidus", 0) if isinstance(r, dict) else 0),
            "peak": (r.get("peak", 0) if isinstance(r, dict) else 0),
            "profile_metrics": (self._profile_metrics_for_result(r) if isinstance(r, dict) else {}),
            "props": (r.get("props") if isinstance(r, dict) else {}),
            "melting_detail": (r.get("melting_detail") if isinstance(r, dict) else {}),
            "evidence": (r.get("evidence") if isinstance(r, dict) else {}),
            "ai_sources": (r.get("ai_sources") if isinstance(r, dict) else []),
            "ai_cited_sources": (r.get("ai_cited_sources") if isinstance(r, dict) else []),
            "retrieved_candidates": (r.get("retrieved_candidates") if isinstance(r, dict) else []),
            "ai_used_this_request": (r.get("ai_used_this_request", False) if isinstance(r, dict) else False),
            "alloy_inference": (r.get("alloy_inference") if isinstance(r, dict) else {}),
        }
        self._render_result_text(final_output, summary=summary)

    # ─────────────────────────────────────────────────────────────────────────
    # ① 합금 비교 모드
    # ─────────────────────────────────────────────────────────────────────────
    def open_compare_window(self):
        win = tk.Toplevel(self.root)
        win.title("합금 비교 — 두 번째 조성 입력")
        win.configure(bg=UI_BG)
        win.geometry("920x530")

        tk.Label(win, text="비교할 두 번째 합금 조성 입력",
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Segoe UI", 15, "bold"), pady=8).pack(fill="x")
        tk.Label(win, text="조성 A:  " + (composition_to_string(self.comp) or "없음"),
                 bg=UI_BG, fg="#9ca3af", font=("Segoe UI", 10)).pack(pady=4)

        frame = tk.Frame(win, bg=PANEL_BG, padx=10, pady=10)
        frame.pack(fill="both", expand=True, padx=12, pady=6)

        comp_b, btns_b = {}, {}

        def upd_b():
            total = sum(comp_b.values())
            color = ("#34d399" if abs(total-100)<=0.5
                     else "#fbbf24" if 95<=total<=105 else "#f87171")
            lbl_b.config(text=f"총합 B: {total:.2f} %", fg=color)

        def enter_b(elem):
            val = simpledialog.askstring("입력 B", f"{elem} (%) 값 입력")
            if val is None: return
            try:
                v = float(val)
                if v < 0: raise ValueError
                comp_b[elem] = v
                btns_b[elem].config(text=f"{elem}\n{v:.2f}%")
                upd_b()
            except Exception:
                messagebox.showerror("오류", "0 이상의 숫자를 입력하세요.")

        def auto_sn_b():
            others = sum(v for k, v in comp_b.items() if k != "Sn")
            if others >= 100:
                messagebox.showwarning("불가", f"Sn 외 합계 {others:.2f}% >= 100%"); return
            comp_b["Sn"] = round(100.0 - others, 4)
            btns_b["Sn"].config(text=f"Sn\n{comp_b['Sn']:.2f}%")
            upd_b()

        solder_elems = ["Sn","Ag","Cu","Bi","In","Sb","Ni","Zn",
                        "Pb","Ge","Co","Ga","Au","Pd","Pt","Al"]
        for i, elem in enumerate(solder_elems):
            b = tk.Button(frame, text=elem, width=6, height=2,
                          bg=BTN_BG, fg="white",
                          font=("Segoe UI", 9, "bold"),
                          command=lambda e=elem: enter_b(e))
            b.grid(row=i//8, column=i%8, padx=3, pady=3)
            btns_b[elem] = b

        lbl_b = tk.Label(frame, text="총합 B: 0.00 %",
                         bg=PANEL_BG, fg="white",
                         font=("Segoe UI", 11, "bold"))
        lbl_b.grid(row=3, column=0, columnspan=8, pady=6)

        ctrl = tk.Frame(win, bg=UI_BG)
        ctrl.pack(pady=8)

        def run_compare():
            if not self.comp:
                messagebox.showwarning("경고", "조성 A를 먼저 입력하세요."); return
            if not comp_b:
                messagebox.showwarning("경고", "조성 B를 입력하세요."); return
            win.destroy()
            th = threading.Thread(target=lambda: self._do_compare(dict(comp_b)))
            th.daemon = True
            th.start()

        tk.Button(ctrl, text="Sn 자동완성", command=auto_sn_b,
                  bg="#064e3b", fg="white", width=14, height=2,
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=6)
        tk.Button(ctrl, text="⚖ 비교 분석 실행", command=run_compare,
                  bg="#7c3aed", fg="white", width=16, height=2,
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=6)

    def _do_compare(self, comp_b):
        self._set_ai_request_badge(None)
        self.result_box.delete("1.0", tk.END)
        self._reset_live_progress_log("비교 분석")
        self.set_progress(0, "비교 분석 시작...")
        try:
            self.set_progress(20, "합금 A 분석 중...")
            r_a = self._run_single(self.comp)
            self.set_progress(60, "합금 B 분석 중...")
            r_b = self._run_single(comp_b)
        except Exception as e:
            log_exception("GUI._do_compare", e)
            try:
                messagebox.showerror("오류", f"비교 분석 실패: {e}")
            except Exception:
                pass
            self._finish_live_progress_log(ok=False)
            return

        self.last_result    = r_a
        self.compare_result = r_b
        self.compare_comp   = comp_b
        a_used = bool(r_a.get("ai_used_this_request", False)) if isinstance(r_a, dict) else False
        b_used = bool(r_b.get("ai_used_this_request", False)) if isinstance(r_b, dict) else False
        self._set_ai_request_badge(compare_pair=(a_used, b_used))
        self._refresh_ai_usage_ui()
        self._refresh_imc_tal_ui()

        self._apply_compare_shared_wetting(self.last_result, self.compare_result)

        self.set_progress(90, "비교 보고서 생성 중...")
        output = self._build_compare_report(self.comp, comp_b, r_a, r_b)
        self.root.after(0, self._enable_result_btns)
        self.set_progress(100, "비교 완료")
        self._finish_live_progress_log(ok=True)
        summary = {
            "type": "compare",
            "A": {
                "name": ((r_a.get("best") or {}).get("name", "합금 A") if isinstance(r_a, dict) else "합금 A"),
                "confidence": (r_a.get("confidence", 0) if isinstance(r_a, dict) else 0),
                "confidence_overall": (r_a.get("confidence_overall", 0) if isinstance(r_a, dict) else 0),
                "solidus": (r_a.get("solidus", 0) if isinstance(r_a, dict) else 0),
                "liquidus": (r_a.get("liquidus", 0) if isinstance(r_a, dict) else 0),
                "peak": (r_a.get("peak", 0) if isinstance(r_a, dict) else 0),
                "profile_metrics": (self._profile_metrics_for_result(r_a) if isinstance(r_a, dict) else {}),
                "props": (r_a.get("props") if isinstance(r_a, dict) else {}),
                "alloy_inference": (r_a.get("alloy_inference") if isinstance(r_a, dict) else {}),
            },
            "B": {
                "name": ((r_b.get("best") or {}).get("name", "합금 B") if isinstance(r_b, dict) else "합금 B"),
                "confidence": (r_b.get("confidence", 0) if isinstance(r_b, dict) else 0),
                "confidence_overall": (r_b.get("confidence_overall", 0) if isinstance(r_b, dict) else 0),
                "solidus": (r_b.get("solidus", 0) if isinstance(r_b, dict) else 0),
                "liquidus": (r_b.get("liquidus", 0) if isinstance(r_b, dict) else 0),
                "peak": (r_b.get("peak", 0) if isinstance(r_b, dict) else 0),
                "profile_metrics": (self._profile_metrics_for_result(r_b) if isinstance(r_b, dict) else {}),
                "props": (r_b.get("props") if isinstance(r_b, dict) else {}),
                "alloy_inference": (r_b.get("alloy_inference") if isinstance(r_b, dict) else {}),
            },
        }
        self._render_result_text(output, summary=summary)

    def _build_compare_report(self, comp_a, comp_b, r_a, r_b):
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        W = 22  # kept for internal wrapping only (not column alignment)

        def _sd(x):
            return x if isinstance(x, dict) else {}

        def _sl(x):
            if x is None:
                return []
            if isinstance(x, list):
                return x
            if isinstance(x, tuple):
                return list(x)
            if isinstance(x, str):
                s = x.strip()
                return [s] if s else []
            return [str(x)]

        def _wrap(s, width):
            s = str(s) if s is not None else ""
            s = s.strip()
            if not s:
                return ["N/A"]
            out = []
            while len(s) > width:
                cut = s.rfind(" ", 0, width)
                if cut <= 0:
                    cut = width
                out.append(s[:cut].rstrip())
                s = s[cut:].lstrip()
            out.append(s)
            return out

        def _fmt_bullets(items, width=64, indent="  "):
            arr = [str(x).strip() for x in _sl(items)]
            arr = [x for x in arr if x]
            if not arr:
                arr = ["N/A"]
            lines = []
            for x in arr:
                w = _wrap(x, width)
                lines.append(f"{indent}- {w[0]}")
                for cont in w[1:]:
                    lines.append(f"{indent}  {cont}")
            return "\n".join(lines) + "\n"

        def _fmt_comp(comp, width=W):
            txt = composition_to_string(comp) if comp else "N/A"
            return _wrap(txt, width)

        def _best_name(r):
            return _sd(_sd(r).get("best")).get("name", "N/A")

        def _matrix_summary(norm):
            norm = _sd(norm)
            if not norm:
                return "N/A"
            top = sorted(norm.items(), key=lambda kv: -float(kv[1] or 0.0))[:4]
            parts = []
            for k, v in top:
                try:
                    parts.append(f"{k} {float(v):.1f}%")
                except Exception:
                    parts.append(f"{k} {v}")
            base_k, base_v = top[0]
            base = f"{base_k} ({float(base_v or 0.0):.1f}%)"
            return f"기지/메인: {base} | 상위: " + ", ".join(parts)

        def _property_notes(norm, props):
            norm = _sd(norm)
            props = _sd(props)
            bi = float(norm.get("Bi", 0.0) or 0.0)
            cu = float(norm.get("Cu", 0.0) or 0.0)
            ag = float(norm.get("Ag", 0.0) or 0.0)
            in_ = float(norm.get("In", 0.0) or 0.0)
            sb = float(norm.get("Sb", 0.0) or 0.0)
            ni = float(norm.get("Ni", 0.0) or 0.0)

            notes = []
            if bi >= 40:
                notes.append("Sn–Bi 고함량 계열: 저온 공정(저융점) 유리, 충격 취성 리스크 큼")
            elif bi >= 5:
                notes.append("Bi 중함량: 융점 하향·강도 기여 가능, 취성/드롭 신뢰성 주의")
            if ag >= 2:
                notes.append("Ag 강화: Ag3Sn 분산 강화로 강도/열피로에 유리한 경향")
            if cu >= 0.7:
                notes.append("Cu 높음: Cu-Sn IMC 성장 가속 → 계면/EM 리스크와 함께 관리 필요")
            elif 0 < cu < 0.3:
                notes.append("Cu 낮음: 젖음/계면 IMC 형성은 완만할 수 있음")
            if in_ >= 1:
                notes.append("In 첨가: 융점 하향 및 젖음성 개선에 유리한 경향")
            if sb >= 8:
                notes.append("Sb 고함량: 고온 강도/내열 기여 가능, 취성 증가 가능")
            if ni > 0:
                notes.append("Ni 미량: 계면 IMC 안정화 및 열피로 저항에 도움 가능")

            fmax = float(props.get("wetting_fmax_pred_mn", 0.0) or 0.0)
            tdb = props.get("tensile_strength_db_mpa")
            if fmax > 0:
                notes.append(f"젖음 Fmax(예측): {fmax:.2f} mN (높을수록 유리)")
            if tdb is not None:
                try:
                    notes.append(f"물성 DB 인장: {float(tdb):.1f} MPa")
                except Exception:
                    pass

            return notes[:6] if notes else ["N/A"]

        def _fmt_cell(v, unit=""):
            try:
                return f"{float(v):.2f}{unit}"
            except Exception:
                s = str(v).strip()
                return (s + unit) if s else "N/A"

        def _winner_mark(va, vb, hi="high"):
            try:
                fa, fb = float(va), float(vb)
                if hi == "high":
                    return ("▲", "") if fa > fb else ("", "▲") if fb > fa else ("", "")
                return ("▲", "") if fa < fb else ("", "▲") if fb < fa else ("", "")
            except Exception:
                return "", ""

        def _trow(label, a, b, d=""):
            # tab-separated row (tabs are pixel-aligned in result_box)
            return f"{label}\t{a}\t{b}\t{d}\n"

        def _trow_num(label, va, vb, unit="", hi="high"):
            ma, mb = _winner_mark(va, vb, hi=hi)
            a = _fmt_cell(va, unit) + (f" {ma}" if ma else "")
            b = _fmt_cell(vb, unit) + (f" {mb}" if mb else "")
            try:
                delta = float(vb) - float(va)
                d = f"{delta:+.2f}{unit}"
            except Exception:
                d = "N/A"
            return _trow(label, a, b, d)

        ra, rb = _sd(r_a), _sd(r_b)
        pa, pb = _sd(ra.get("props")), _sd(rb.get("props"))

        sep = "─" * 68
        o = f"{'='*68}\n"
        o += f"  합금 비교 분석 보고서   ({now})\n{'='*68}\n\n"
        o += f"  항목\t합금 A\t합금 B\tΔ(B-A)\n  {sep}\n"

        # 조성은 한 줄로 길게 출력 (wrap 없음 + 가로 스크롤 지원)
        o += _trow("조성", composition_to_string(comp_a) or "N/A", composition_to_string(comp_b) or "N/A", "")

        conf_a = float(ra.get("confidence", 0.0) or 0.0)
        conf_b = float(rb.get("confidence", 0.0) or 0.0)
        score_a = float(ra.get("score", 0.0) or 0.0)
        score_b = float(rb.get("score", 0.0) or 0.0)
        o += _trow("최적 일치", _best_name(ra), _best_name(rb), "")
        o += _trow("거리/신뢰도", f"{score_a:.3f} / {conf_a:.1f}%", f"{score_b:.3f} / {conf_b:.1f}%", "")

        o += f"\n  {sep}\n  [메인 조성(기지) 요약]\n  {sep}\n"
        o += f"  합금 A: {_matrix_summary(ra.get('norm'))}\n"
        o += f"  합금 B: {_matrix_summary(rb.get('norm'))}\n"

        o += f"\n  {sep}\n  [특성 방향성(조성 기반 요약)]\n  {sep}\n"
        o += "  합금 A:\n" + _fmt_bullets(_property_notes(ra.get("norm"), pa))
        o += "  합금 B:\n" + _fmt_bullets(_property_notes(rb.get("norm"), pb))

        o += f"\n  {sep}\n  [온도 프로파일]\n  {sep}\n"
        sa = float(ra.get("solidus", 0.0) or 0.0)
        la = float(ra.get("liquidus", 0.0) or 0.0)
        pk_a = float(ra.get("peak", 0.0) or 0.0)
        sb = float(rb.get("solidus", 0.0) or 0.0)
        lb = float(rb.get("liquidus", 0.0) or 0.0)
        pk_b = float(rb.get("peak", 0.0) or 0.0)
        o += _trow_num("Solidus (℃)", sa, sb, " ℃", "low")
        o += _trow_num("Liquidus (℃)", la, lb, " ℃", "low")
        o += _trow_num("ΔT (℃)", la - sa, lb - sb, " ℃", "low")
        o += _trow_num("권장 피크 (℃)", pk_a, pk_b, " ℃", "low")

        o += f"\n  {sep}\n  [물성 비교]  ▲ = 해당 항목 우위\n  {sep}\n"
        def _tensile_row_label(props):
            basis = (props or {}).get("tensile_strength_basis")
            if basis == "db_idw":
                return "인장 (BD유사) (MPa)"
            if basis == "lit_ref":
                return "인장 (문헌) (MPa)"
            if basis == "lit_blend":
                return "인장 (문헌보정) (MPa)"
            return "인장강도 (MPa)"

        def _shear_row_label(props):
            basis = (props or {}).get("shear_strength_basis")
            return "전단 (BD유사) (MPa)" if basis == "db_idw" else "전단강도 (MPa)"

        o += _trow_num(_tensile_row_label(pa), pa.get("tensile_strength", 0), pb.get("tensile_strength", 0), " MPa")
        o += _trow_num("항복강도 (MPa)", pa.get("yield_strength", 0), pb.get("yield_strength", 0), " MPa")
        o += _trow_num("연신율 (%)", pa.get("elongation", 0), pb.get("elongation", 0), "%")
        o += _trow_num(_shear_row_label(pa), pa.get("shear_strength"), pb.get("shear_strength"), " MPa")
        o += _trow_num("젖음 Fmax (mN)", pa.get("wetting_fmax_pred_mn", 0), pb.get("wetting_fmax_pred_mn", 0), " mN")
        if pa.get("tensile_strength_basis") != "db_idw" or pb.get("tensile_strength_basis") != "db_idw":
            o += _trow_num(
                "물성 DB 인장 (MPa)",
                None if pa.get("tensile_strength_basis") == "db_idw" else pa.get("tensile_strength_db_mpa"),
                None if pb.get("tensile_strength_basis") == "db_idw" else pb.get("tensile_strength_db_mpa"),
                " MPa",
            )

        # ── 비교 기반 도펀트 추천 ───────────────────────────────────────────
        def _normalize_to_100(comp):
            comp = _sd(comp)
            total = sum(float(v or 0.0) for v in comp.values())
            if total <= 0:
                return {}
            return {k: (float(v or 0.0) / total * 100.0) for k, v in comp.items() if float(v or 0.0) > 0}

        def _simulate_add(norm, elem, add_pct):
            """Add elem by add_pct (wt%), reduce Sn to keep sum 100."""
            base = _normalize_to_100(norm)
            if not base:
                return None
            add_pct = float(add_pct or 0.0)
            if add_pct <= 0:
                return None
            out = dict(base)
            out[elem] = float(out.get(elem, 0.0) or 0.0) + add_pct
            # keep total at 100 by subtracting from Sn first, else from largest component
            total = sum(out.values())
            excess = total - 100.0
            if excess > 1e-9:
                if out.get("Sn", 0.0) > 0:
                    take = min(out["Sn"], excess)
                    out["Sn"] = out["Sn"] - take
                    excess -= take
                if excess > 1e-9:
                    # subtract from the current max element (excluding the newly added elem if possible)
                    keys = sorted(out.keys(), key=lambda k: out.get(k, 0.0), reverse=True)
                    for k in keys:
                        if k == elem:
                            continue
                        if out.get(k, 0.0) <= 0:
                            continue
                        take = min(out[k], excess)
                        out[k] -= take
                        excess -= take
                        if excess <= 1e-9:
                            break
            # clean tiny/negative
            out = {k: round(v, 4) for k, v in out.items() if v and v > 1e-6}
            return out

        def _estimate_effects(base_norm, base_props, elem, add_pct):
            """
            Return short numeric delta string using existing melting + property models.
            This is a heuristic estimate based on current internal models.
            """
            new_norm = _simulate_add(base_norm, elem, add_pct)
            if not new_norm:
                return ""

            # Melting prediction
            try:
                from .melting_predictor import hybrid_melting_predict
                s2, l2, p2, _detail = hybrid_melting_predict(
                    new_norm, self.analyzer.db_prepared, ai_engine=self.ai
                )
            except Exception:
                s2 = l2 = p2 = None

            # Property prediction
            try:
                props2 = self.analyzer.model_properties(new_norm, s2 or 0.0, l2 or 0.0, peak=p2 or 0.0)
            except Exception:
                props2 = {}

            base_props = _sd(base_props)
            def d(key, nd=1):
                try:
                    return float(props2.get(key, 0.0) or 0.0) - float(base_props.get(key, 0.0) or 0.0)
                except Exception:
                    return 0.0

            parts = []
            # temperatures
            try:
                bs = float(sa)  # for A by default; caller can override by passing base temps if needed
            except Exception:
                bs = None
            try:
                # if base_norm is from B, sa isn't correct; skip base temp deltas in that case.
                pass
            except Exception:
                pass
            # We can still show absolute new temps, plus property deltas.
            if s2 is not None and l2 is not None:
                parts.append(f"예상 융점 {s2:.1f}~{l2:.1f}℃")

            dt = d("tensile_strength")
            ds = d("shear_strength")
            dfm = d("wetting_fmax_pred_mn")
            parts.append(f"Δ인장 {dt:+.1f}MPa")
            parts.append(f"Δ전단 {ds:+.1f}MPa")
            parts.append(f"ΔFmax {dfm:+.2f}mN")

            return " | " + " / ".join(parts)

        def _dopant_reco(norm, props, other_props, label="A"):
            norm = _sd(norm)
            props = _sd(props)
            other_props = _sd(other_props)
            bi = float(norm.get("Bi", 0.0) or 0.0)
            cu = float(norm.get("Cu", 0.0) or 0.0)
            ag = float(norm.get("Ag", 0.0) or 0.0)
            in_ = float(norm.get("In", 0.0) or 0.0)

            t = float(props.get("tensile_strength", 0.0) or 0.0)
            sh = float(props.get("shear_strength", 0.0) or 0.0)
            fmax = float(props.get("wetting_fmax_pred_mn", 0.0) or 0.0)
            t2 = float(other_props.get("tensile_strength", 0.0) or 0.0)
            sh2 = float(other_props.get("shear_strength", 0.0) or 0.0)
            fmax2 = float(other_props.get("wetting_fmax_pred_mn", 0.0) or 0.0)

            goal = (self.reco_goal.get() or "균형").strip()

            # deficits: positive means "needs improvement to match other"
            def _def(a, b):
                return (b - a) if (b > 0) else 0.0

            d_strength = max(_def(t, t2), _def(sh, sh2))
            d_wetting = _def(fmax, fmax2)

            # Goal weighting (크리프 지표 제거 — Fmax 기반 젖음만)
            w_strength, w_wet, w_low = 1.0, 1.0, 0.0
            if goal == "강도":
                w_strength, w_wet = 2.2, 0.6
            elif goal == "젖음":
                w_strength, w_wet = 0.7, 2.4
            elif goal == "저융점":
                w_strength, w_wet, w_low = 0.7, 1.2, 2.2

            score_strength = d_strength * w_strength
            score_wet = d_wetting * w_wet
            score_low = (max(0.0, 3.0 - bi) + max(0.0, 1.0 - in_)) * w_low

            # 근거 문자열 (짧게 1줄)
            reasons = []
            if score_strength > 0.1:
                reasons.append(f"강도열세={d_strength:.1f}")
            if score_wet > 0.05:
                reasons.append(f"Fmax열세={d_wetting:.2f}mN")
            if goal == "저융점":
                reasons.append("저융점목표")
            reason_txt = f"(근거: 목표={goal}" + (", " + ", ".join(reasons) if reasons else "") + ")"

            # Build candidate actions (score, text)
            rec = []

            def add_rec(score, elem, add, text):
                if score <= 0:
                    return
                rec.append((float(score), f"{elem}(+{add}): {text} {reason_txt}{_estimate_effects(norm, props, elem, float(add))}"))

            # Strength actions
            if ag < 2.0:
                add_rec(score_strength, "Ag", "2.0", "Ag3Sn 분산 강화 → 강도/열피로 상승 경향")
            if cu < 0.5:
                add_rec(score_strength * 0.9, "Cu", "0.5", "Cu6Sn5 기반 계면 강화 → 전단/접합 강도 상승 경향")

            # Wetting / Low-melting actions
            if in_ < 1.0:
                add_rec(max(score_wet, score_low), "In", "2.0", "젖음성 개선 + 융점 하향 방향")
            if bi < 3.0:
                add_rec(max(score_wet * 0.9, score_low * 0.9), "Bi", "2.0", "젖음성/저융점화 도움 (취성 리스크 주의)")

            # 고온 강도(Sb): 강도 목표일 때만 가중
            sb_score = score_strength * (1.4 if goal == "강도" else 0.35)
            add_rec(sb_score, "Sb", "1.0", "고온 강도·내열 방향 (과량 시 취성 증가 가능)")

            # IMC stabilization (always consider when Cu is high)
            if cu >= 0.7:
                add_rec(1.0 + score_strength * 0.2, "Ni", "0.05", "계면 IMC 안정화 → Cu3Sn 과성장/열화 리스크 완화 방향")

            # High Bi caution note
            if bi >= 10:
                rec.append((0.2, "Ni(미량) 또는 Sb(소량): 조직 안정화 방향(취성 완화 목적). 실제 적용 전 신뢰성 시험 권장"))

            rec.sort(key=lambda x: x[0], reverse=True)
            texts = [t for _s, t in rec if t]
            return texts[:6] if texts else ["(비교 기준) 큰 열세 항목이 없어 도펀트보단 공정조건 최적화 권장"]

        o += f"\n  {sep}\n  [추천 원소(도펀트) 및 기대 효과(간단 수치 추정 포함) - 비교 기반]\n  {sep}\n"
        o += "  합금 A 추천:\n" + _fmt_bullets(_dopant_reco(ra.get("norm"), pa, pb, label="A"), width=92)
        o += "  합금 B 추천:\n" + _fmt_bullets(_dopant_reco(rb.get("norm"), pb, pa, label="B"), width=92)

        roles_a = (ra.get("element_roles") or "").strip()
        roles_b = (rb.get("element_roles") or "").strip()
        o += f"\n  {sep}\n  [메인 조성 역할 / 원소 역할]\n  {sep}\n"
        o += "  합금 A:\n"
        o += ("\n".join([f"  {x}" for x in _wrap(roles_a, 64)]) + "\n") if roles_a else "  N/A\n"
        o += "\n  합금 B:\n"
        o += ("\n".join([f"  {x}" for x in _wrap(roles_b, 64)]) + "\n") if roles_b else "  N/A\n"

        o += f"\n  {sep}\n  [리스크]\n  {sep}\n"
        o += "  합금 A:\n" + _fmt_bullets(ra.get("risk", []))
        o += "  합금 B:\n" + _fmt_bullets(rb.get("risk", []))

        o += f"\n  {sep}\n  [예상 IMC]\n  {sep}\n"
        o += "  합금 A:\n" + _fmt_bullets(ra.get("imc", []))
        o += "  합금 B:\n" + _fmt_bullets(rb.get("imc", []))

        o += f"\n{'='*68}\n"
        return o

    # ─────────────────────────────────────────────────────────────────────────
    # ② 물성 레이더 차트
    # ─────────────────────────────────────────────────────────────────────────
    def show_radar_chart(self):
        if not self.last_result:
            messagebox.showwarning("경고", "먼저 분석을 실행하세요.")
            return

        def _draw():
            try:
                import matplotlib
                matplotlib.use("TkAgg")
                import matplotlib.pyplot as plt
                import matplotlib.font_manager as fm
            except Exception:
                messagebox.showerror("오류", "pip install matplotlib"); return

            kf = get_korean_font()
            def kfp(size=10, bold=False):
                if kf is None: return {}
                p = fm.FontProperties(fname=kf.get_file())
                p.set_size(size)
                if bold: p.set_weight("bold")
                return {"fontproperties": p}

            labels = ["인장강도\n(MPa)", "항복강도\n(MPa)", "연신율\n(%)",
                      "전단강도\n(MPa)", "Fmax\n(mN)",   "DB인장\n(MPa)"]
            keys   = ["tensile_strength", "yield_strength", "elongation",
                      "shear_strength",   "wetting_fmax_pred_mn",  "tensile_strength_db_mpa"]
            maxval = [150, 120, 60, 150, 3.0, 150]
            n      = len(labels)
            theta  = [2 * math.pi * i / n for i in range(n)]

            def get_vals(res):
                p = res["props"]
                return [min(p.get(k, 0) / m, 1.0) for k, m in zip(keys, maxval)]

            fig, ax = plt.subplots(figsize=(8, 7), subplot_kw={"polar": True})
            fig.patch.set_facecolor("#1f2937")
            ax.set_facecolor("#111827")

            # 극좌표 눈금
            ax.set_thetagrids([t * 180 / math.pi for t in theta], labels)
            for lbl in ax.get_xticklabels():
                lbl.set_color("#9ca3af")
                if kf: lbl.set_fontproperties(kf)
            ax.set_yticklabels([])
            ax.spines["polar"].set_color("#4b5563")
            ax.grid(color="#374151", linestyle="--", linewidth=0.8)

            # 합금 A
            va = get_vals(self.last_result)
            va_closed = va + [va[0]]
            t_closed  = theta + [theta[0]]
            ax.plot(t_closed, va_closed, color="#60a5fa", lw=2.2, label="합금 A")
            ax.fill(t_closed, va_closed, color="#60a5fa", alpha=0.2)

            # 실제값 주석 (합금 A)
            pa = self.last_result["props"]
            for i, (k, m) in enumerate(zip(keys, maxval)):
                ax.text(theta[i], va[i] + 0.10,
                        f"{pa.get(k,0):.1f}", color="#93c5fd",
                        ha="center", va="center", fontsize=7)

            # 합금 B (비교 모드)
            if self.compare_result:
                vb = get_vals(self.compare_result)
                vb_closed = vb + [vb[0]]
                ax.plot(t_closed, vb_closed, color="#f87171", lw=2.2, label="합금 B")
                ax.fill(t_closed, vb_closed, color="#f87171", alpha=0.15)

            best_a = self.last_result.get("best", {}).get("name", "합금 A")
            ax.set_title(f"물성 레이더 차트 — {best_a}",
                         color="#e5e7eb", pad=20, **kfp(13, bold=True))

            legend = ax.legend(loc="upper right", bbox_to_anchor=(1.32, 1.12),
                               facecolor="#374151", edgecolor="#6b7280",
                               labelcolor="#e5e7eb", fontsize=9)
            if kf:
                for t in legend.get_texts():
                    t.set_fontproperties(kf)

            plt.tight_layout()
            plt.show()

        self.root.after(10, _draw)

    # ─────────────────────────────────────────────────────────────────────────
    # ③ 즐겨찾기
    # ─────────────────────────────────────────────────────────────────────────
    def save_favorite(self):
        if not self.comp:
            messagebox.showwarning("경고", "먼저 조성을 입력하세요."); return
        name = simpledialog.askstring("즐겨찾기 저장",
            f"이 조성의 이름을 입력하세요\n(현재: {composition_to_string(self.comp)})")
        if not name: return
        favs = self._load_favorites_file()
        favs[name] = dict(self.comp)
        with open(self.FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("저장 완료", f"'{name}' 이(가) 즐겨찾기에 저장되었습니다.")

    def load_favorite(self):
        favs = self._load_favorites_file()
        if not favs:
            messagebox.showinfo("즐겨찾기", "저장된 즐겨찾기가 없습니다."); return

        win = tk.Toplevel(self.root)
        win.title("즐겨찾기 불러오기")
        win.configure(bg=UI_BG)
        win.geometry("480x380")
        tk.Label(win, text="즐겨찾기 목록", bg=HEADER_BG, fg=HEADER_FG,
                 font=("Segoe UI", 13, "bold"), pady=8).pack(fill="x")

        listbox = tk.Listbox(win, bg=TEXT_BG, fg=TEXT_FG,
                             font=("Consolas", 11),
                             selectbackground="#2563eb", height=12)
        listbox.pack(fill="both", expand=True, padx=12, pady=8)
        for name in favs:
            listbox.insert(tk.END, f"  {name}  —  {composition_to_string(favs[name])}")

        btn_row = tk.Frame(win, bg=UI_BG)
        btn_row.pack(pady=6)

        def apply():
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("선택 없음", "불러올 항목을 선택하세요."); return
            name = list(favs.keys())[sel[0]]
            comp = favs[name]
            self.reset()
            for elem, val in comp.items():
                self.comp[elem] = val
                if elem in self.buttons:
                    self.buttons[elem].config(text=f"{elem}\n{val:.2f}%")
            self.update_sum()
            win.destroy()
            messagebox.showinfo("불러오기 완료", f"'{name}' 조성을 불러왔습니다.")

        def delete_fav():
            sel = listbox.curselection()
            if not sel: return
            name = list(favs.keys())[sel[0]]
            if messagebox.askyesno("삭제 확인", f"'{name}'을(를) 삭제하시겠습니까?"):
                del favs[name]
                with open(self.FAVORITES_FILE, "w", encoding="utf-8") as f:
                    json.dump(favs, f, ensure_ascii=False, indent=2)
                listbox.delete(sel[0])

        for text, cmd, color in [
            ("불러오기", apply,       "#2563eb"),
            ("삭제",     delete_fav,  "#7f1d1d"),
            ("닫기",     win.destroy, BTN_BG),
        ]:
            tk.Button(btn_row, text=text, command=cmd,
                      bg=color, fg="white", width=10, height=2,
                      font=("Segoe UI", 10, "bold")).pack(side="left", padx=6)

    def _load_favorites_file(self):
        if not os.path.exists(self.FAVORITES_FILE): return {}
        try:
            with open(self.FAVORITES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # ─────────────────────────────────────────────────────────────────────────
    # ④ 리플로우 조건
    # ─────────────────────────────────────────────────────────────────────────
    def show_reflow_conditions(self):
        if not self.last_result:
            messagebox.showwarning("경고", "먼저 분석을 실행하세요."); return

        r  = self.last_result
        pf = calc_reflow_profile(r["solidus"], r["liquidus"], r["peak"])
        best_name = r.get("best", {}).get("name", "N/A")

        win = tk.Toplevel(self.root)
        win.title("리플로우 조건 — IPC-J-STD-020E")
        win.configure(bg=UI_BG)
        win.geometry("580x560")
        tk.Label(win, text="리플로우 조건 자동 계산  (IPC-J-STD-020E 기준)",
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Segoe UI", 13, "bold"), pady=8).pack(fill="x")
        tk.Label(win,
                 text=f"합금: {best_name}  |  Solidus {r['solidus']:.1f}℃ / Liquidus {r['liquidus']:.1f}℃",
                 bg=UI_BG, fg="#9ca3af", font=("Segoe UI", 10)).pack(pady=5)

        text = scrolledtext.ScrolledText(win, bg=TEXT_BG, fg=TEXT_FG,
                                         font=("Consolas", 11), height=20)
        text.pack(fill="both", expand=True, padx=12, pady=6)

        lines = [
            "=" * 54,
            "  IPC-J-STD-020E 권장 리플로우 프로파일",
            "=" * 54,
            "",
            "  [1] 예열 (Preheat) 구간",
            f"      온도 범위 : {pf['preheat_min']} ~ {pf['preheat_max']} ℃",
            f"      승온 속도 : 최대 {pf['ramp_up']} ℃/s 이하 권장",
            "",
            "  [2] 소크 (Soak) 구간",
            f"      온도 범위 : {pf['soak_start']} ~ {pf['soak_end']} ℃",
            f"      유지 시간 : {pf['soak_time']} ~ 120 초 권장",
            "",
            "  [3] 리플로우 (Reflow) 구간",
            f"      Solidus   : {r['solidus']:.1f} ℃",
            f"      Liquidus  : {r['liquidus']:.1f} ℃",
            f"      액상 유지 : {pf['tl_time']} ~ 90 초  (IPC 기준)",
            f"      피크 범위 : {pf['peak_min']} ~ {pf['peak_max']} ℃",
            f"      권장 피크 : {pf['recommended_peak']} ℃",
            "",
            "  [4] 냉각 (Cooling) 구간",
            f"      냉각 속도 : 최대 {pf['cool_rate']} ℃/s 이하 권장",
            "      급냉 주의 : 열충격으로 인한 솔더 크랙 방지",
            "",
        ]

        # ─── [5] 사용자 튜닝 가드레일 (현재 profile_tune + 목표 기준) ───
        try:
            preset_name = (self.profile_preset.get() or "AUTO").strip()
            try:
                prof = self._build_peak_profile_curve(r)
                preset_name = (prof.get("preset_name") or preset_name).strip()
            except Exception:
                pass
            goal_name = (self.profile_goal.get() or "없음").strip()
            v = self._validate_profile_tune(dict(self.profile_tune), preset_name)
            lines += [
                "  [5] 사용자 튜닝 가드레일",
                f"      목표 : {goal_name}   |   프리셋 : {preset_name}",
            ]
            for m in v.get("errors", []):
                lines.append(f"      ❌ {m}")
            for m in v.get("warnings", []):
                lines.append(f"      ⚠ {m}")
            for m in v.get("oks", []):
                lines.append(f"      ✓ {m}")
            if not (v.get("errors") or v.get("warnings") or v.get("oks")):
                lines.append("      (검증 결과 없음)")
            lines.append("")
        except Exception:
            pass

        lines += [
            "=" * 54,
            "  주의사항",
            "-" * 54,
            "  · 실제 프로파일은 PCB 열용량, 부품 종류에 따라",
            "    ±5~10℃ 조정이 필요합니다.",
            "  · 질소 분위기 사용 시 피크 온도를 5℃ 낮출 수 있습니다.",
            "  · ΔT가 좁은 합금일수록 온도 제어 정밀도가 중요합니다.",
            "=" * 54,
        ]
        text.insert(tk.END, "\n".join(lines))
        text.config(state=tk.DISABLED)
        tk.Button(win, text="닫기", command=win.destroy,
                  bg=BTN_BG, fg="white", width=12, height=2,
                  font=("Segoe UI", 10, "bold")).pack(pady=8)

    # ─────────────────────────────────────────────────────────────────────────
    # ⑤ RoHS/REACH 체크
    # ─────────────────────────────────────────────────────────────────────────
    def show_rohs_check(self):
        if not self.comp:
            messagebox.showwarning("경고", "먼저 조성을 입력하세요."); return

        norm = self.analyzer.normalize(self.comp)

        win = tk.Toplevel(self.root)
        win.title("RoHS / REACH 규제 물질 스크리닝")
        win.configure(bg=UI_BG)
        win.geometry("640x580")
        tk.Label(win, text="RoHS / REACH 규제 물질 스크리닝",
                 bg=HEADER_BG, fg=HEADER_FG,
                 font=("Segoe UI", 13, "bold"), pady=8).pack(fill="x")

        text = scrolledtext.ScrolledText(win, bg=TEXT_BG, fg=TEXT_FG,
                                         font=("Consolas", 11), height=24)
        text.pack(fill="both", expand=True, padx=12, pady=8)

        text.tag_config("RED",    foreground="#f87171")
        text.tag_config("YELLOW", foreground="#fbbf24")
        text.tag_config("GREEN",  foreground="#34d399")
        text.tag_config("GRAY",   foreground="#9ca3af")
        text.tag_config("BOLD",   font=("Consolas", 11, "bold"))

        def ins(msg, tag=""):
            text.insert(tk.END, msg, tag)

        ins("=" * 64 + "\n", "GRAY")
        ins("  RoHS Directive 2011/65/EU + REACH 규제 스크리닝\n", "BOLD")
        ins("=" * 64 + "\n\n", "GRAY")

        has_issue = False
        for elem, pct in sorted(norm.items(), key=lambda x: -x[1]):
            info = ROHS_DB.get(elem)
            ppm  = pct * 10000  # wt% → ppm

            if info is None:
                ins(f"  ✅  {elem:<4}  {pct:6.2f} wt%   규제 대상 아님\n", "GREEN")
                continue

            name = info["name"]
            reg  = info["regulation"]
            lim  = info["limit_ppm"]

            if elem in ("Pb", "Hg", "Cd") and pct > 0:
                has_issue = True
                tag = "RED"
                ins(f"  🚨  {elem:<4}  {pct:6.2f} wt%  ({ppm:,.0f} ppm)\n", tag)
                ins(f"       ▶ {name}\n", tag)
                ins(f"       ▶ 규정: {reg}" + (f"  |  한계: {lim} ppm" if lim else "") + "\n", tag)
                if elem == "Pb":
                    ins("       ▶ RoHS 적용 제품에서 원칙적 사용 금지\n", tag)
                ins("\n")
            elif elem in ("Bi", "Sb", "In") and pct > 5:
                has_issue = True
                ins(f"  ⚠️   {elem:<4}  {pct:6.2f} wt%\n", "YELLOW")
                ins(f"       ▶ {name}\n", "YELLOW")
                ins(f"       ▶ {reg}\n", "YELLOW")
                ins(f"       ▶ 고함량({pct:.1f}%) — 용도·국가별 규제 확인 필요\n\n", "YELLOW")
            elif elem in ("Bi", "Sb", "In"):
                ins(f"  ✅  {elem:<4}  {pct:6.2f} wt%  {name} — 소량, 현재 규제 없음\n", "GREEN")
            elif elem in ("Tl", "Se", "Te") and pct > 0:
                has_issue = True
                ins(f"  ⚠️   {elem:<4}  {pct:6.2f} wt%\n", "YELLOW")
                ins(f"       ▶ {name} — {reg}\n\n", "YELLOW")
            else:
                ins(f"  ✅  {elem:<4}  {pct:6.2f} wt%   규제 한계 이하\n", "GREEN")

        ins("\n" + "=" * 64 + "\n", "GRAY")
        if has_issue:
            ins("  ⚠️  규제 주의 항목이 발견되었습니다.\n", "YELLOW")
            ins("  적용 국가·제품군별 면제 조항을 반드시 확인하세요.\n", "GRAY")
        else:
            ins("  ✅  주요 RoHS/REACH 규제 항목 이상 없음\n", "GREEN")
        ins("=" * 64 + "\n", "GRAY")

        text.config(state=tk.DISABLED)
        tk.Button(win, text="닫기", command=win.destroy,
                  bg=BTN_BG, fg="white", width=12, height=2,
                  font=("Segoe UI", 10, "bold")).pack(pady=8)

    # ─────────────────────────────────────────────────────────────────────────
    # 🧱 IMC 계면 3D 구조 (전문형 시각화)
    # ─────────────────────────────────────────────────────────────────────────
    def show_imc_3d_structure(self):
        if not self.last_result:
            messagebox.showwarning("경고", "먼저 분석을 실행하세요.")
            return

        def _draw():
            try:
                import matplotlib
                matplotlib.use("TkAgg")
                import matplotlib.pyplot as plt
                import matplotlib.patches as mpatches
                import matplotlib.font_manager as fm
                import textwrap
                from matplotlib.widgets import Button
                from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
            except Exception:
                messagebox.showerror("오류", "pip install matplotlib")
                return

            kf = get_korean_font()
            try:
                if kf is not None:
                    # Keep Korean readability while allowing math/Greek fallback glyphs.
                    plt.rcParams["font.family"] = [kf.get_name(), "DejaVu Sans"]
                plt.rcParams["axes.unicode_minus"] = False
                plt.rcParams["mathtext.fontset"] = "dejavusans"
                plt.rcParams["mathtext.default"] = "regular"
            except Exception:
                pass

            def kfp(size=10, bold=False):
                if kf is None:
                    return {}
                p = fm.FontProperties(fname=kf.get_file())
                p.set_size(size)
                if bold:
                    p.set_weight("bold")
                return {"fontproperties": p}

            r = self.last_result if isinstance(self.last_result, dict) else {}
            norm = r.get("norm") if isinstance(r.get("norm"), dict) else {}
            score = float(r.get("score", 9999.0) or 9999.0)
            conf = float(r.get("confidence", 0.0) or 0.0)
            solidus = float(r.get("solidus", 0.0) or 0.0)
            liquidus = float(r.get("liquidus", 0.0) or 0.0)
            peak = float(r.get("peak", 0.0) or 0.0)
            imc_list = r.get("imc") if isinstance(r.get("imc"), list) else []

            cu = float(norm.get("Cu", 0.0) or 0.0)
            ag = float(norm.get("Ag", 0.0) or 0.0)
            ni = float(norm.get("Ni", 0.0) or 0.0)
            bi = float(norm.get("Bi", 0.0) or 0.0)
            sn = float(norm.get("Sn", 0.0) or 0.0)
            view_style = (self.imc_view_style.get() or "표준").strip()
            is_presentation = (view_style == "발표")

            vis_comp = {"Sn": sn, "Ag": ag, "Cu": cu, "Ni": ni, "Bi": bi}

            vis_sn = float(vis_comp.get("Sn", sn))
            vis_ag = float(vis_comp.get("Ag", ag))
            vis_cu = float(vis_comp.get("Cu", cu))
            vis_ni = float(vis_comp.get("Ni", ni))
            vis_bi = float(vis_comp.get("Bi", bi))

            substrate = (self.imc_substrate.get() or "Cu-OSP").strip()
            tal_mode = (self.imc_tal_mode.get() or "AUTO(profile)").strip()
            tal_thr, tal_ref = self._get_tal_threshold_c(liquidus)
            prof = self._build_peak_profile_curve(r)
            tal_calc = self._calc_tal_above_liquidus(prof["time"], prof["temp"], tal_thr)
            tsl = self._calc_time_in_range(prof["time"], prof["temp"], solidus, liquidus)
            tpk = self._calc_tal_above_liquidus(prof["time"], prof["temp"], peak - 5.0)
            if tal_mode == "AUTO(profile)":
                tal_s = tal_calc
                tal_src = "AUTO(profile)"
            elif tal_mode == "기판기본":
                tal_s = self._imc_default_tal(substrate)
                tal_src = "기판기본"
            else:
                try:
                    tal_s = float(self.imc_tal_sec.get() or 35.0)
                except Exception:
                    tal_s = float(self.profile_tune.get("over_liquidus_time", 35.0) or 35.0)
                tal_src = "사용자입력"
            tal_s = max(5.0, min(180.0, tal_s))
            try:
                self.imc_tal_sec.set(f"{tal_s:.0f}")
            except Exception:
                pass

            # Arrhenius + parabolic growth: x = k * sqrt(t), k = A * exp(-Q/RT)
            react_c = max(liquidus + 2.0, min(peak, liquidus + 35.0))
            temp_k = react_c + 273.15
            gas_r = 8.314
            score_factor = max(0.40, min(1.10, 1.0 - min(score, 10.0) * 0.045))

            def _arr_um(a_pref, q_jmol):
                try:
                    k = float(a_pref) * math.exp(-float(q_jmol) / (gas_r * temp_k))
                    return max(0.0, k * math.sqrt(max(1.0, tal_s)))
                except Exception:
                    return 0.0

            # 공통 레이어
            t_solder = 28.0
            t_sub = 4.0
            t_ni_barrier = 0.0
            imc_layers = []
            phase_color = {
                # High-contrast projector-friendly palette
                "matrix_bg": "#eaf3ff",
                "beta_sn": "#93c5fd",
                "ag3sn": "#374151",
                "cu6sn5": "#f97316",
                "cu3sn": "#a16207",
                "bi_rich": "#ef4444",
                "ni3sn4": "#7c3aed",
            }

            if substrate == "ENIG(Ni/Au)":
                # ENIG: Ni3Sn4 주도, (Cu,Ni)6Sn5 동반 가능. Cu3Sn은 일반적으로 약함.
                t_ni_barrier = 2.2
                t_ni3sn4 = _arr_um(1.6e7, 67000) * (0.55 + 0.25 * min(ni + 0.02, 0.20) * 8.0) * score_factor
                t_cuni6sn5 = _arr_um(1.9e7, 56500) * (0.15 + 0.40 * min(cu, 0.9)) * score_factor
                t_cu3sn = _arr_um(7.0e6, 62500) * (0.03 + 0.15 * max(0.0, cu - 0.4)) * score_factor
                imc_layers.append(("Ni3Sn4", max(0.05, min(2.4, t_ni3sn4)), phase_color["ni3sn4"], 0.90))
                if t_cuni6sn5 > 0.06:
                    imc_layers.append(("(Cu,Ni)6Sn5", min(1.7, t_cuni6sn5), phase_color["cu6sn5"], 0.90))
                if t_cu3sn > 0.07 and tal_s > 70:
                    imc_layers.append(("Cu3Sn", min(0.9, t_cu3sn), phase_color["cu3sn"], 0.88))
                sub_label = "ENIG Pad"
            elif substrate == "ImmAg":
                # ImmAg: Ag 도금은 대부분 용해되어 벌크 Ag3Sn로 분산, 계면은 Cu계 IMC가 주도
                t_cu6sn5 = _arr_um(2.2e7, 55500) * (0.35 + 0.65 * min(cu, 1.3)) * score_factor
                t_cu3sn = _arr_um(9.0e6, 62000) * (0.10 + 0.55 * max(0.0, cu - 0.25)) * score_factor
                if t_cu3sn > 0.06:
                    imc_layers.append(("Cu3Sn", min(1.6, t_cu3sn), phase_color["cu3sn"], 0.88))
                imc_layers.append(("Cu6Sn5", max(0.10, min(3.4, t_cu6sn5)), phase_color["cu6sn5"], 0.90))
                sub_label = "ImmAg Pad"
            elif substrate == "ImmSn":
                # Sn 도금 표면: Cu6Sn5 성장 우세, Cu3Sn은 비교적 완만
                t_cu6sn5 = _arr_um(2.4e7, 55000) * (0.45 + 0.60 * min(cu + 0.1, 1.5)) * score_factor
                t_cu3sn = _arr_um(8.5e6, 62500) * (0.08 + 0.40 * max(0.0, cu - 0.2)) * score_factor
                imc_layers.append(("Cu6Sn5", max(0.12, min(3.8, t_cu6sn5)), phase_color["cu6sn5"], 0.90))
                if t_cu3sn > 0.05:
                    imc_layers.append(("Cu3Sn", min(1.8, t_cu3sn), phase_color["cu3sn"], 0.88))
                sub_label = "ImmSn Pad"
            else:
                # Cu-OSP 기본: Cu6Sn5 + Cu3Sn
                t_cu6sn5 = _arr_um(2.5e7, 55000) * (0.40 + 0.70 * min(cu + 0.05, 1.6)) * score_factor
                t_cu3sn = _arr_um(1.0e7, 62000) * (0.08 + 0.50 * max(0.0, cu - 0.2)) * score_factor
                if bi >= 20.0:
                    t_cu6sn5 *= 0.88
                    t_cu3sn *= 0.82
                imc_layers.append(("Cu3Sn", max(0.03, min(2.0, t_cu3sn)), phase_color["cu3sn"], 0.88))
                imc_layers.append(("Cu6Sn5", max(0.10, min(4.2, t_cu6sn5)), phase_color["cu6sn5"], 0.90))
                sub_label = "Cu Pad"

            fig = plt.figure(figsize=(14.8, 8.3) if is_presentation else (13.8, 7.9))
            fig.patch.set_facecolor("#eef2f7")
            gs = fig.add_gridspec(
                2,
                2,
                height_ratios=[1.12, 0.88],
                width_ratios=[1.45, 1.0],
                hspace=0.16,
                wspace=0.08,
            )
            ax_bulk = fig.add_subplot(gs[0, 0])
            ax_info = fig.add_subplot(gs[0, 1])
            ax_if = fig.add_subplot(gs[1, :])

            # ── 상단 좌측: 벌크 미세구조(조성 기반 자동 생성)
            ax_bulk.set_xlim(0, 100)
            ax_bulk.set_ylim(0, 70)
            ax_bulk.set_xticks([])
            ax_bulk.set_yticks([])
            ax_bulk.set_facecolor("#ffffff")
            for sp in ax_bulk.spines.values():
                sp.set_color("#d1d5db")

            # beta-Sn matrix 영역
            ax_bulk.add_patch(
                plt.Rectangle((4, 5), 92, 60, facecolor=phase_color["matrix_bg"], edgecolor=phase_color["beta_sn"], linewidth=1.1, alpha=0.97)
            )
            # 상단 헤더 영역(텍스트-도형 겹침 방지)
            ax_bulk.add_patch(
                plt.Rectangle((6, 62.0), 88, 2.6, facecolor="#ffffff", edgecolor="none", alpha=0.86)
            )

            seed = int((vis_ag * 137 + vis_cu * 97 + vis_ni * 211 + vis_bi * 53 + tal_s) * 100)
            rnd = random.Random(seed)

            # 샘플 톤: grain 형태를 과도하게 복잡하지 않게 고정 레이아웃 기반으로 배치
            grain_templates = [
                [(10, 16), (13, 50), (20, 42), (18, 18), (14, 12)],
                [(27, 18), (30, 54), (37, 44), (35, 18), (30, 12)],
                [(44, 16), (47, 56), (54, 46), (52, 18), (47, 12)],
                [(61, 19), (64, 50), (70, 42), (68, 19), (64, 13)],
                [(77, 17), (80, 52), (87, 44), (85, 18), (80, 12)],
            ]
            for g in grain_templates:
                # 조성에 따라 형태를 미세 흔들어 동일 패턴 반복감을 줄임
                jx = rnd.uniform(-0.8, 0.8)
                jy = rnd.uniform(-0.8, 0.8)
                verts = [(x + jx, y + jy) for x, y in g]
                ax_bulk.add_patch(
                    plt.Polygon(
                        verts,
                        closed=True,
                        facecolor="#bfdbfe",
                        edgecolor=phase_color["beta_sn"],
                        linewidth=1.0,
                        alpha=0.88,
                    )
                )

            # Ag3Sn / Cu6Sn5 / Bi 농화 분산상(조성 따라 수량 변경)
            n_ag3sn = int(max(0, min(26, round(vis_ag * 3.2))))
            n_cu6sn5 = int(max(0, min(18, round(vis_cu * 1.8))))
            # Bi 농화 분산상은 저함량에서도 관찰될 수 있어 가시성 보정
            n_bi_rich = int(max(0, min(18, round(max(0.0, vis_bi) * 0.75))))

            for _ in range(n_ag3sn):
                x = rnd.uniform(7, 93)
                y = rnd.uniform(7, 58)
                # Ag3Sn은 침상/판상 경향을 반영해 장축:단축 비를 키움
                w = rnd.uniform(2.4, 5.4)
                h = rnd.uniform(0.35, 0.95)
                ang = rnd.uniform(0, 180)
                rect = plt.Rectangle((x, y), w, h, angle=ang, facecolor=phase_color["ag3sn"], edgecolor="#1f2937", alpha=0.95)
                ax_bulk.add_patch(rect)
            for _ in range(n_cu6sn5):
                x = rnd.uniform(6, 94)
                y = rnd.uniform(6, 58)
                ax_bulk.scatter([x], [y], s=rnd.uniform(18, 52), c=phase_color["cu6sn5"], marker="h", alpha=0.97, edgecolors="#9a3412", linewidths=0.55)
            for _ in range(n_bi_rich):
                x = rnd.uniform(6, 94)
                y = rnd.uniform(6, 58)
                ax_bulk.scatter(
                    [x],
                    [y],
                    s=rnd.uniform(18, 48),
                    c=phase_color["bi_rich"],
                    marker="D",
                    alpha=0.95,
                    edgecolors="#7f1d1d",
                    linewidths=0.5,
                )

            ax_bulk.set_title(
                "솔더 벌크 미세구조 (입력 조성 기반)",
                color="#334155",
                pad=8,
                **kfp(13 if is_presentation else 11, True),
            )
            ax_bulk.text(
                50,
                63.3,
                "β-Sn 기지 + 조성 기반 분산상",
                color="#334155",
                ha="center",
                va="top",
                bbox=dict(facecolor="#ffffff", edgecolor="#dbeafe", alpha=0.72, pad=1.2),
                **kfp(10 if is_presentation else 9, True),
            )

            # ── 상단 우측: 박스 없는 자연스러운 섹션형 레이아웃
            ax_info.set_xticks([])
            ax_info.set_yticks([])
            ax_info.set_facecolor("#ffffff")
            for sp in ax_info.spines.values():
                sp.set_color("#d1d5db")
            ax_info.set_title("범례 / 조성", color="#334155", pad=8, **kfp(13 if is_presentation else 11, True))
            ax_info.set_xlim(0, 1)
            ax_info.set_ylim(0, 1)

            # 좌측 블루 포인트 라인
            ax_info.plot([0.04, 0.04], [0.05, 0.95], color="#60a5fa", lw=2.0, alpha=0.9)
            title_fs = (12 if is_presentation else 10)
            body_fs = (10 if is_presentation else 9)
            x_title = 0.10
            x_marker = 0.115
            x_text = 0.165
            y = 0.90
            line_h = (0.072 if is_presentation else 0.064)

            def _section(title):
                nonlocal y
                ax_info.text(x_title, y, title, transform=ax_info.transAxes,
                             color="#111827", ha="left", va="top", **kfp(title_fs, True))
                y -= line_h * 0.72
                ax_info.plot([x_title, 0.94], [y, y], transform=ax_info.transAxes, color="#e5e7eb", lw=1.0)
                y -= line_h * 0.45

            def _legend_row(col, txt, style="box"):
                nonlocal y
                if style == "line":
                    ax_info.plot([x_marker - 0.02, x_marker + 0.04], [y, y], transform=ax_info.transAxes,
                                 color=col, lw=3.0, solid_capstyle="round")
                elif style == "hex":
                    ax_info.scatter([x_marker + 0.01], [y], transform=ax_info.transAxes, s=66,
                                    c=col, marker="h", edgecolors="#9a3412", linewidths=0.6)
                elif style == "diamond":
                    ax_info.scatter([x_marker + 0.01], [y], transform=ax_info.transAxes, s=54,
                                    c=col, marker="D", edgecolors="#7f1d1d", linewidths=0.6)
                else:
                    ax_info.add_patch(
                        plt.Rectangle((x_marker - 0.022, y - 0.018), 0.05, 0.036,
                                      transform=ax_info.transAxes, facecolor=col, edgecolor="#cbd5e1", linewidth=0.8)
                    )
                ax_info.text(x_text, y, txt, transform=ax_info.transAxes, color="#374151",
                             va="center", clip_on=True, **kfp(body_fs))
                y -= line_h

            def _text_rows(lines, wrap_width=28):
                nonlocal y
                for raw in lines:
                    wrapped = textwrap.wrap(str(raw), width=wrap_width, break_long_words=False, break_on_hyphens=False) or [""]
                    for ln in wrapped:
                        if y < 0.08:
                            return
                        ax_info.text(x_title, y, ln, transform=ax_info.transAxes, color="#374151",
                                     ha="left", va="top", clip_on=True, **kfp(body_fs))
                        y -= line_h * 0.95

            _section("범례")
            _legend_row(phase_color["beta_sn"], "β-Sn 수지상", style="box")
            if n_ag3sn > 0:
                _legend_row(phase_color["ag3sn"], r"Ag$_3$Sn 판상", style="line")
            if n_cu6sn5 > 0:
                _legend_row(phase_color["cu6sn5"], r"Cu$_6$Sn$_5$ 입자", style="hex")
            if n_bi_rich > 0:
                _legend_row(phase_color["bi_rich"], "Bi 농화 분산상", style="diamond")

            y -= line_h * 0.15
            _section("조성 정보")
            comp_lines = [f"• Sn {vis_sn:.1f} wt%", f"• Ag {vis_ag:.1f} wt%", f"• Cu {vis_cu:.1f} wt%"]
            if vis_bi > 0:
                comp_lines.append(f"• Bi {vis_bi:.1f} wt%")
            if vis_ni > 0:
                comp_lines.append(f"• Ni {vis_ni:.2f} wt%")
            _text_rows(comp_lines, wrap_width=24)

            y -= line_h * 0.05
            _section("공정 지표")
            proc_lines = [
                f"융점 ~{solidus:.0f}–{liquidus:.0f}℃",
                f"TAL {tal_s:.1f}s / S~L {tsl:.1f}s",
                f"Peak-5 {tpk:.1f}s",
            ]
            _text_rows(proc_lines, wrap_width=30)

            # ── 하단: 계면(IMC) 단면 인포그래픽 (샘플 스타일)
            ax_if.set_xlim(0, 100)
            ax_if.set_ylim(0, 30)
            ax_if.set_xticks([])
            ax_if.set_yticks([])
            ax_if.set_facecolor("#ffffff")
            for sp in ax_if.spines.values():
                sp.set_color("#d1d5db")
            ax_if.set_title(
                "계면 IMC (Interfacial Intermetallic Compound) 구조",
                color="#334155",
                pad=8,
                **kfp(13 if is_presentation else 11, True),
            )

            # 실제 계산 두께(라벨용)
            dmap = {}
            for lname, lh, _lcol, _la in imc_layers:
                if float(lh or 0.0) > 0.0:
                    dmap[str(lname)] = float(lh)
            t_if_cu3 = float(dmap.get("Cu3Sn", 0.0))
            t_if_cu6 = float(dmap.get("Cu6Sn5", dmap.get("(Cu,Ni)6Sn5", 0.0)))
            t_if_ni3 = float(dmap.get("Ni3Sn4", 0.0))
            scallop_label = "(Cu,Ni)6Sn5" if "(Cu,Ni)6Sn5" in dmap else "Cu6Sn5"

            x0, w = 3.0, 94.0
            # 높이 배치(시각 강조): 기판 -> Cu3Sn -> 스캘럽 -> 솔더 벌크
            y_sub = 2.0
            h_sub = 6.0
            h_cu3 = (1.8 if t_if_cu3 > 0.02 else 0.0)
            h_scallop = (2.8 if t_if_cu6 > 0.04 else 0.0)
            y_if = y_sub + h_sub
            y_scallop = y_if + h_cu3
            y_bulk = y_scallop + h_scallop
            h_bulk = 26.8 - y_bulk

            # 1) 솔더 벌크
            ax_if.add_patch(
                plt.Rectangle((x0, y_bulk), w, h_bulk, facecolor=phase_color["matrix_bg"], edgecolor=phase_color["beta_sn"], linewidth=0.9)
            )
            # grain motif
            for gx in [8, 24, 40, 58, 74, 88]:
                verts = [(gx - 3, y_bulk + 1.0), (gx - 1.2, y_bulk + h_bulk - 2.0), (gx + 2.2, y_bulk + h_bulk - 6.5),
                         (gx + 0.8, y_bulk + 1.8), (gx - 2.0, y_bulk + 0.8)]
                ax_if.add_patch(
                    plt.Polygon(verts, closed=True, facecolor=phase_color["beta_sn"], edgecolor=phase_color["beta_sn"], alpha=0.90, linewidth=0.65)
                )
            if vis_ag > 0:
                for dx, dy in [(16, y_bulk + 8.8), (31, y_bulk + 11.5), (49, y_bulk + 7.6), (67, y_bulk + 10.4), (83, y_bulk + 8.5)]:
                    ax_if.plot([dx, dx + 2.0], [dy, dy + 0.6], color=phase_color["ag3sn"], lw=1.8, alpha=0.9)
            if vis_bi > 0:
                for bx, by in [(20, y_bulk + 2.3), (46, y_bulk + 1.8), (76, y_bulk + 2.4)]:
                    ax_if.scatter([bx], [by], s=28, c=phase_color["bi_rich"], marker="o", alpha=0.9, edgecolors="#92400e", linewidths=0.4)
            ax_if.text(50.0, y_bulk + h_bulk - 1.1, r"솔더 벌크 (β-Sn + Ag$_3$Sn + Cu$_6$Sn$_5$)", color="#334155",
                       ha="center", va="top", **kfp(10 if is_presentation else 9, True))

            # 2) Cu6Sn5 스캘럽층
            if h_scallop > 0:
                n_scallop = 16
                cell = w / n_scallop
                r_sc = h_scallop
                for i in range(n_scallop):
                    cx = x0 + i * cell + cell * 0.5
                    ax_if.add_patch(
                        mpatches.Wedge((cx, y_scallop), r_sc, 0, 180, facecolor=phase_color["cu6sn5"], edgecolor="#c2410c", linewidth=0.75, alpha=0.97)
                    )
                ax_if.plot([x0, x0 + w], [y_scallop, y_scallop], color="#c2410c", lw=1.0, alpha=0.86)
                txt_sc = (
                    rf"(Cu,Ni)$_6$Sn$_5$ (η 상) ≈ {max(0.10, t_if_cu6):.2f} um"
                    if "(Cu,Ni)6Sn5" in dmap
                    else rf"Cu$_6$Sn$_5$ (η 상) ≈ {max(0.10, t_if_cu6):.2f} um"
                )
                ax_if.annotate(
                    txt_sc,
                    xy=(66.0, y_scallop + h_scallop * 0.75),
                    xytext=(70.0, y_scallop + h_scallop + 1.8),
                    color="#1f2937",
                    ha="center",
                    va="center",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#fff7ed", edgecolor="#fdba74", alpha=0.95),
                    arrowprops=dict(arrowstyle="-", color="#9a3412", lw=0.8),
                    **kfp(10 if is_presentation else 9, True),
                )

            # 3) Cu3Sn 얇은 층
            if h_cu3 > 0:
                ax_if.add_patch(
                    plt.Rectangle((x0, y_if), w, h_cu3, facecolor=phase_color["cu3sn"], edgecolor="#854d0e", linewidth=0.85, alpha=0.97)
                )
                ax_if.annotate(
                    rf"Cu$_3$Sn (ε 상) ≈ {max(0.03, t_if_cu3):.2f} um",
                    xy=(61.0, y_if + h_cu3 * 0.5),
                    xytext=(58.0, y_if - 1.0),
                    color="#1f2937",
                    ha="center",
                    va="center",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#fef3c7", edgecolor="#fcd34d", alpha=0.95),
                    arrowprops=dict(arrowstyle="-", color="#854d0e", lw=0.8),
                    **kfp(10 if is_presentation else 9, True),
                )

            # 4) Cu 기판
            ax_if.add_patch(plt.Rectangle((x0, y_sub), w, h_sub, facecolor="#e9d8a6", edgecolor="#d6bc7f", linewidth=0.8))
            for sx in range(0, 95, 10):
                ax_if.plot([x0 + sx, x0 + sx + 5], [y_sub + h_sub - 0.2, y_sub + 0.3], color="#d6bc7f", lw=0.7, alpha=0.75)
            ax_if.text(50.0, y_sub + h_sub * 0.52, "Cu 기판 (Copper Substrate)", color="#334155",
                       ha="center", va="center", **kfp(11 if is_presentation else 9, True))

            # ENIG에서 Ni3Sn4 보조 라벨
            if t_if_ni3 > 0.02:
                ax_if.text(
                    95.0,
                    y_bulk - 0.35,
                    rf"Ni$_3$Sn$_4$ ≈ {t_if_ni3:.2f} um",
                    color="#6d28d9",
                    ha="right",
                    va="top",
                    **kfp(9 if is_presentation else 8, True),
                )

            # 하단 범례 바 (폭 초과 시 자동 다음 줄)
            lg_items = [
                (phase_color["cu6sn5"], r"Cu$_6$Sn$_5$ (η 상)"),
                (phase_color["cu3sn"], r"Cu$_3$Sn (ε 상)"),
            ]
            if vis_ag > 0:
                lg_items.append((phase_color["ag3sn"], r"Ag$_3$Sn 분산상"))
            if vis_bi > 0:
                lg_items.append((phase_color["bi_rich"], "Bi 농화 분산상"))
            if t_if_ni3 > 0.02:
                lg_items.append((phase_color["ni3sn4"], r"Ni$_3$Sn$_4$"))
            lg_x, lg_y = 4.0, 1.05
            for c, txt in lg_items:
                # 라벨 폭 근사치로 줄바꿈
                step = 7.0 + max(11.0, len(txt) * 1.0)
                if lg_x + step > 95.0:
                    lg_x = 4.0
                    lg_y = 2.1
                ax_if.add_patch(plt.Rectangle((lg_x, lg_y), 1.6, 0.9, facecolor=c, edgecolor="#64748b", linewidth=0.5))
                ax_if.text(lg_x + 2.0, lg_y + 0.45, txt, color="#334155", va="center", **kfp(9 if is_presentation else 8))
                lg_x += step

            # 그림 하단 캡션(간결) - 기존 장문 박스 제거
            fig.text(
                0.015,
                0.028,
                "모델: Arrhenius + 포물선 성장(상대 비교용) | 주의: SEM/EDS 실측 절대두께 대체 불가",
                color="#64748b",
                fontsize=(10 if is_presentation else 9),
                bbox=dict(facecolor="#ffffff", edgecolor="#e5e7eb", alpha=0.92, pad=2.0),
                **kfp(10 if is_presentation else 9),
            )

            # 저장 버튼(발표 자료 내보내기)
            btn_ax = fig.add_axes([0.86, 0.01, 0.12, 0.045])
            btn_ax.set_facecolor("#1f2937")
            save_btn = Button(btn_ax, "PNG 저장", color="#1e3a8a", hovercolor="#2563eb")
            try:
                if kf is not None:
                    save_btn.label.set_fontproperties(kfp(10, True).get("fontproperties"))
            except Exception:
                pass

            def _on_save(_event):
                path = filedialog.asksaveasfilename(
                    title="IMC 시각화 PNG 저장",
                    defaultextension=".png",
                    filetypes=[("PNG Image", "*.png")],
                    initialfile="imc_visualization.png",
                )
                if not path:
                    return
                try:
                    fig.savefig(path, dpi=220, facecolor=fig.get_facecolor(), bbox_inches="tight")
                    messagebox.showinfo("저장 완료", f"PNG로 저장했습니다.\n{path}")
                except Exception as e:
                    messagebox.showerror("오류", f"저장 실패: {e}")

            save_btn.on_clicked(_on_save)

            # ─── 튜닝 가드레일 한 줄 요약 (footer 텍스트) ───
            try:
                preset_name = (self.profile_preset.get() or "AUTO").strip()
                try:
                    preset_name = (prof.get("preset_name") or preset_name).strip()
                except Exception:
                    pass
                goal_name = (self.profile_goal.get() or "없음").strip()
                v_res = self._validate_profile_tune(dict(self.profile_tune), preset_name)
                if v_res.get("errors"):
                    head_msg = "❌ " + v_res["errors"][0]
                    head_color = "#f87171"
                elif v_res.get("warnings"):
                    head_msg = "⚠ " + v_res["warnings"][0]
                    head_color = "#fbbf24"
                elif v_res.get("oks"):
                    head_msg = "✓ " + v_res["oks"][0]
                    head_color = "#86efac"
                else:
                    head_msg = ""
                    head_color = "#9ca3af"
                if head_msg:
                    extra = (
                        f"   목표: {goal_name} · 프리셋: {preset_name}"
                    )
                    fig.text(
                        0.5, 0.005,
                        f"튜닝 가드레일: {head_msg}{extra}",
                        ha="center", va="bottom",
                        color=head_color, fontsize=9,
                        **kfp(9, bold=False),
                    )
            except Exception:
                pass

            # Use explicit margins so panels fill the canvas consistently.
            fig.subplots_adjust(left=0.03, right=0.985, top=0.94, bottom=0.10, wspace=0.08, hspace=0.16)
            plt.show()

        self.root.after(10, _draw)

    # ─────────────────────────────────────────────────────────────────────────
    # 📈 융점 그래프
    # ─────────────────────────────────────────────────────────────────────────
    def show_melting_graph(self):
        if not self.last_result:
            messagebox.showwarning("경고", "먼저 분석을 실행하세요."); return

        def _draw():
            try:
                import matplotlib
                matplotlib.use("TkAgg")
                import matplotlib.pyplot as plt
                import matplotlib.patches as mpatches
                import matplotlib.font_manager as fm
            except Exception:
                messagebox.showerror("오류", "pip install matplotlib"); return

            kf = get_korean_font()
            def kfp(size=10, bold=False):
                if kf is None: return {}
                p = fm.FontProperties(fname=kf.get_file())
                p.set_size(size)
                if bold: p.set_weight("bold")
                return {"fontproperties": p}

            r = self.last_result
            solidus, liquidus, peak = r["solidus"], r["liquidus"], r["peak"]
            props = r["props"]
            best  = r.get("best") or {}
            conf  = r.get("confidence", 0)

            soak_temp = solidus - 5
            t_ph      = 25 + (150 - 25) * 0.9
            time = [0, 60, 120, 150, 180, 210, 220, 230, 240, 245, 250, 260, 290, 330]
            temp = [
                25, t_ph*0.55, t_ph, soak_temp*0.9, soak_temp,
                solidus, solidus+(liquidus-solidus)*0.5, liquidus,
                liquidus+(peak-liquidus)*0.6, peak,
                liquidus, solidus, soak_temp*0.6, 25,
            ]

            fig, ax = plt.subplots(figsize=(11, 6))
            fig.patch.set_facecolor("#1f2937")
            ax.set_facecolor("#111827")
            ax.axvspan(0,   60,  alpha=0.12, color="#60a5fa")
            ax.axvspan(60,  180, alpha=0.12, color="#fbbf24")
            ax.axvspan(180, 260, alpha=0.18, color="#f87171")
            ax.axvspan(260, 330, alpha=0.10, color="#34d399")

            y_lbl = min(temp) + (max(temp)-min(temp))*0.04
            for x, lbl, col in [(30,"예열","#60a5fa"),(120,"소크","#fbbf24"),
                                  (220,"리플로우","#f87171"),(295,"냉각","#34d399")]:
                ax.text(x, y_lbl, lbl, color=col, fontsize=9,
                        ha="center", alpha=0.9, **kfp(9, bold=True))

            ax.axhline(solidus,  color="#60a5fa", lw=1.4, ls="--", alpha=0.8)
            ax.axhline(liquidus, color="#f87171", lw=1.4, ls="--", alpha=0.8)
            ax.axhline(peak,     color="#fbbf24", lw=1.2, ls=":",  alpha=0.7)
            ax.text(332, solidus,  f"Solidus  {solidus:.1f} \u2103",  color="#60a5fa", va="center", fontsize=9)
            ax.text(332, liquidus, f"Liquidus {liquidus:.1f} \u2103", color="#f87171", va="center", fontsize=9)
            ax.text(332, peak,     f"Peak     {peak:.1f} \u2103",     color="#fbbf24", va="center", fontsize=9)
            ax.plot(time, temp, color="#e5e7eb", lw=2.5, zorder=5)
            ax.plot(time, temp, "o", color="#ffffff", ms=5, zorder=6)

            best_name = best.get("name", "N/A")
            delta_t   = liquidus - solidus
            _tdb_v = props.get("tensile_strength_db_mpa")
            try:
                _tdb_txt = f"{float(_tdb_v):.1f} MPa" if _tdb_v is not None else "N/A"
            except Exception:
                _tdb_txt = "N/A"
            info = (
                f"최적 일치 : {best_name}\n신뢰도    : {conf:.0f} %\n"
                f"Solidus   : {solidus:.1f} \u2103\nLiquidus  : {liquidus:.1f} \u2103\n"
                f"\u0394T        : {delta_t:.1f} \u2103\nPeak      : {peak:.1f} \u2103\n"
                f"{'─'*22}\n"
                f"인장강도  : {props.get('tensile_strength',0):.1f} MPa\n"
                f"항복강도  : {props.get('yield_strength',  0):.1f} MPa\n"
                f"연신율    : {props.get('elongation',      0):.1f} %\n"
                f"전단강도  : {props.get('shear_strength',  0):.1f} MPa\n"
                f"젖음 Fmax : {props.get('wetting_fmax_pred_mn', 0):.2f} mN\n"
                f"물성DB인장: {_tdb_txt}"
            )
            txt_kw = {"fontproperties": fm.FontProperties(fname=kf.get_file())} if kf else {}
            ax.text(0.01, 0.99, info, transform=ax.transAxes,
                    va="top", ha="left", fontsize=8.5, color="#e5e7eb",
                    bbox=dict(boxstyle="round,pad=0.55", facecolor="#374151",
                              alpha=0.88, edgecolor="#6b7280"), **txt_kw)

            ax.set_xlim(-5, 380)
            ax.set_xlabel("시간 (초)", color="#9ca3af", fontsize=10, **kfp(10))
            ax.set_ylabel("온도 (\u2103)", color="#9ca3af", fontsize=10, **kfp(10))
            ax.set_title(f"리플로우 프로파일 / 융점 예측  [{best_name}]",
                         color="#e5e7eb", fontsize=13, pad=12, **kfp(13, bold=True))
            ax.tick_params(colors="#9ca3af")
            for spine in ax.spines.values():
                spine.set_edgecolor("#4b5563")

            handles = [mpatches.Patch(color=c, alpha=a, label=l) for c, a, l in [
                ("#60a5fa",0.5,"예열"),("#fbbf24",0.5,"소크"),
                ("#f87171",0.6,"리플로우"),("#34d399",0.4,"냉각")]]
            legend = ax.legend(handles=handles, loc="upper right",
                               facecolor="#374151", edgecolor="#6b7280",
                               labelcolor="#e5e7eb", fontsize=9)
            if kf:
                for t in legend.get_texts(): t.set_fontproperties(kf)

            plt.tight_layout()
            plt.show()

        self.root.after(10, _draw)

    # ─────────────────────────────────────────────────────────────────────────
    # 📄 Peak-based automatic reflow profile (template style)
    # - Uses predicted Solidus/Liquidus/Peak
    # - Keeps PDF-like stages, but generalizes "220C over" to "Liquidus over"
    # ─────────────────────────────────────────────────────────────────────────
    def show_peak_profile(self):
        if not self.last_result:
            messagebox.showwarning("경고", "먼저 분석을 실행하세요."); return

        def _draw():
            try:
                import matplotlib
                matplotlib.use("TkAgg")
                import matplotlib.pyplot as plt
                import matplotlib.patches as mpatches
                import matplotlib.font_manager as fm
            except Exception:
                messagebox.showerror("오류", "pip install matplotlib"); return

            kf = get_korean_font()
            def kfp(size=10, bold=False):
                if kf is None: return {}
                p = fm.FontProperties(fname=kf.get_file())
                p.set_size(size)
                if bold: p.set_weight("bold")
                return {"fontproperties": p}

            r = self.last_result
            solidus = float(r.get("solidus", 0.0) or 0.0)
            liquidus = float(r.get("liquidus", 0.0) or 0.0)
            peak = float(r.get("peak", 0.0) or 0.0)
            md = r.get("melting_detail") if isinstance(r.get("melting_detail"), dict) else {}
            family = (md.get("family") or "").strip()
            best = r.get("best") or {}
            best_name = best.get("name", "N/A")

            prof = self._build_peak_profile_curve(r)
            preset_name = prof["preset_name"]
            ramp_rate = float(prof["ramp_rate"])
            cool_rate = float(prof["cool_rate"])
            peak_margin = float(prof["peak_margin"])
            t_pre_start = float(prof["t_pre_start"])
            t_pre_end = float(prof["t_pre_end"])
            t_reflow_thr = float(prof["t_reflow_thr"])
            peak = float(prof["peak"])
            dt_b = float(prof["dt_b"])
            dt_e = float(prof["dt_e"])
            t0 = float(prof["t0"])
            tA = float(prof["tA"])
            tB = float(prof["tB"])
            tC = float(prof["tC"])
            tE = float(prof["tE"])
            tF = float(prof["tF"])
            time = list(prof["time"])
            temp = list(prof["temp"])
            tal_thr, tal_ref = self._get_tal_threshold_c(liquidus)
            tal_liq = self._calc_tal_above_liquidus(time, temp, tal_thr)
            t_sl = self._calc_time_in_range(time, temp, solidus, liquidus)
            t_peak5 = self._calc_tal_above_liquidus(time, temp, peak - 5.0)

            fig, ax = plt.subplots(figsize=(11, 6))
            fig.patch.set_facecolor("#1f2937")
            ax.set_facecolor("#111827")

            # Highlight zones roughly matching PDF meaning
            ax.axvspan(t0, tA, alpha=0.10, color="#60a5fa")  # 1st ramp
            ax.axvspan(tA, tB, alpha=0.12, color="#fbbf24")  # preheat
            ax.axvspan(tB, tE, alpha=0.16, color="#f87171")  # reflow/over 220
            ax.axvspan(tE, tF, alpha=0.10, color="#34d399")  # cool

            ax.plot(time, temp, color="#e5e7eb", lw=2.6, zorder=5)
            ax.plot(time, temp, "o", color="#ffffff", ms=5, zorder=6)

            # Annotate stage reference lines
            ax.axhline(t_pre_start, color="#9ca3af", lw=1.0, ls="--", alpha=0.35)
            ax.axhline(t_pre_end, color="#9ca3af", lw=1.0, ls="--", alpha=0.35)
            ax.axhline(t_reflow_thr, color="#f87171", lw=1.2, ls="--", alpha=0.7)
            ax.axhline(peak, color="#fbbf24", lw=1.2, ls=":", alpha=0.8)

            # Show melting lines too (context)
            if solidus and liquidus:
                ax.axhline(solidus,  color="#60a5fa", lw=1.2, ls="--", alpha=0.7)
                ax.axhline(liquidus, color="#f87171", lw=1.2, ls="--", alpha=0.7)

            # Text labels similar to PDF
            y_lbl = min(temp) + (max(temp) - min(temp)) * 0.06
            ax.text((t0+tA)/2, y_lbl, f"1' Ramp-up\n(→{t_pre_start:.0f}℃)\n1~2℃/s", color="#60a5fa",
                    ha="center", va="bottom", fontsize=9, **kfp(9, bold=True))
            ax.text((tA+tB)/2, y_lbl, f"Pre-heat\n{t_pre_start:.0f}~{t_pre_end:.0f}℃\n90±30s", color="#fbbf24",
                    ha="center", va="bottom", fontsize=9, **kfp(9, bold=True))
            ax.text((tB+tC)/2, y_lbl, f"2' Ramp-up\n{t_pre_end:.0f}~{t_reflow_thr:.0f}℃\n1~2℃/s", color="#f87171",
                    ha="center", va="bottom", fontsize=9, **kfp(9, bold=True))
            ax.text((tC+tE)/2, y_lbl, f"Liquidus over\n≥25s\nPeak {peak:.0f}℃", color="#fbbf24",
                    ha="center", va="bottom", fontsize=9, **kfp(9, bold=True))

            ax.set_xlim(-5, tF + 10)
            ax.set_xlabel("Time (sec)", color="#9ca3af", fontsize=10, **kfp(10))
            ax.set_ylabel("Temperature (℃)", color="#9ca3af", fontsize=10, **kfp(10))
            ax.set_title(f"Reflow temperature profile (Peak-based template)\n[{best_name}]",
                         color="#e5e7eb", fontsize=13, pad=12, **kfp(13, bold=True))
            ax.text(
                0.01, 0.02,
                f"Preset: {preset_name} | ramp={ramp_rate:.2f}C/s | preheat={dt_b:.0f}s | over(liq,target)={dt_e:.0f}s | TAL(calc)={tal_liq:.1f}s ({tal_ref}={tal_thr:.1f}C) | S~L={t_sl:.1f}s | Peak-5C={t_peak5:.1f}s | cool={cool_rate:.2f}C/s | peak_margin={peak_margin:.0f}C",
                transform=ax.transAxes,
                ha="left", va="bottom",
                fontsize=8.5, color="#9ca3af",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#111827", alpha=0.75, edgecolor="#374151"),
                **kfp(8)
            )
            ax.tick_params(colors="#9ca3af")
            for spine in ax.spines.values():
                spine.set_edgecolor("#4b5563")

            handles = [mpatches.Patch(color=c, alpha=a, label=l) for c, a, l in [
                ("#60a5fa",0.5,"1st ramp"),("#fbbf24",0.5,"preheat"),
                ("#f87171",0.6,"reflow"),("#34d399",0.4,"cool")]]
            legend = ax.legend(handles=handles, loc="upper right",
                               facecolor="#374151", edgecolor="#6b7280",
                               labelcolor="#e5e7eb", fontsize=9)
            if kf:
                for t in legend.get_texts():
                    t.set_fontproperties(kf)

            plt.tight_layout()
            plt.show()

        self.root.after(10, _draw)

    def draw_melting_curve(self, solidus, liquidus, peak):
        """하위 호환 래퍼"""
        if not self.last_result:
            self.last_result = {"solidus": solidus, "liquidus": liquidus,
                                "peak": peak, "norm": {}, "props": {},
                                "best": {}, "score": 0, "confidence": 0}
        self.show_melting_graph()

    # ─────────────────────────────────────────────────────────────────────────
    # CSV 저장
    # ─────────────────────────────────────────────────────────────────────────
    def _sanitize_csv_text(self, text):
        safe = []
        for line in text.splitlines():
            safe.append(("'" + line) if line.lstrip().startswith(("=","+","-","@")) else line)
        return "\n".join(safe) + ("\n" if text.endswith("\n") else "")

    def save_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv")
        if not path: return
        raw = self.result_box.get("1.0", tk.END)
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(self._sanitize_csv_text(raw))
        messagebox.showinfo("저장 완료", "CSV 저장이 완료되었습니다.")

    # ─────────────────────────────────────────────────────────────────────────
    # 초기화
    # ─────────────────────────────────────────────────────────────────────────
    def reset(self):
        self.comp           = {}
        self.last_result    = None
        self.compare_result = None
        self.compare_comp   = {}
        self._set_ai_request_badge(None)
        for e, b in self.buttons.items():
            b.config(text=e)
        self.update_sum()
        self.result_box.delete("1.0", tk.END)
        for btn in (self.graph_btn, self.radar_btn, self.reflow_btn, self.profile48_btn, self.imc3d_btn):
            if btn:
                btn.config(state=tk.DISABLED, bg="#1e3a5f", fg="#aaaaaa")

    def run(self):
        self.root.mainloop()


# =============================================================================
if __name__ == "__main__":
    gui = AlloyGUI()
    gui.run()
