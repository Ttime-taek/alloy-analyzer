# models.py (Improved v2.1)
# 물성 예측 모델 - 조성 기반 보정 강화 + 고함량 원소 클램핑
# 수정: Bi 고함량 시 선형 오버플로 방지 → 포화 함수 적용

import math

from .utils import composition_distance
from .utils import log_exception
from .wetting_db import WETTING_DB, WETTING_TEMPS_C
from .interp_pchip import interp_pchip_1d


def snap_wetting_temp_to_bd_grid(target_c: float) -> float:
    """250–290℃ 범위로 클램프한 뒤, 측정 DB와 동일한 입력 온도 목록에 가장 가깝게 스냅."""
    lo, hi = min(WETTING_TEMPS_C), max(WETTING_TEMPS_C)
    t = max(min(float(target_c), hi), lo)
    return float(min(WETTING_TEMPS_C, key=lambda x: (abs(x - t), -x)))


def default_wetting_temp_c(liquidus: float) -> float:
    """기본: 액상선+30℃를 측정 DB 온도 축(250–290℃)에 맞춤."""
    return snap_wetting_temp_to_bd_grid(float(liquidus or 0.0) + 30.0)


def compare_default_wetting_temp_c(liquidus_a: float, liquidus_b: float) -> float:
    """비교 모드 자동: 더 높은 액상선+30℃ 목표를 BD 격자(250–290℃)에 한 번 스냅해 A·B 공통 온도로 사용."""
    ta = default_wetting_temp_c(float(liquidus_a or 0.0))
    tb = default_wetting_temp_c(float(liquidus_b or 0.0))
    return float(max(ta, tb))

class PropertyModels:

    def __init__(self):
        pass

    # -----------------------------------------------------
    # 포화 함수: 원소 기여를 비선형으로 제한
    # f(x) = A * (1 - exp(-x/tau))
    # 소량에서 선형, 고함량에서 포화
    # -----------------------------------------------------
    @staticmethod
    def _sat(x, A, tau):
        """포화 함수: 최대 A에 수렴"""
        return A * (1.0 - math.exp(-max(0, x) / tau))

    @staticmethod
    def _smoothstep01(t):
        """t∈[0,1] 매끈한 S곡선 — 물성 계단(anti-step) 방지."""
        t = max(0.0, min(1.0, float(t)))
        return t * t * (3.0 - 2.0 * t)

    # -----------------------------------------------------
    # 인장강도(MPa)
    # -----------------------------------------------------
    def predict_tensile_strength(self, comp, solidus, liquidus):
        try:
            # 문헌·내부실측 정렬 (SAC305 ~41–49 MPa, Sn0.7Cu ~31–39 MPa)
            base = 29.0
            delta_t = max(0, liquidus - solidus)
            temp_factor = max(0, 8.0 - delta_t * 0.1)

            ag = float(comp.get("Ag", 0) or 0.0)
            bi = float(comp.get("Bi", 0) or 0.0)
            sn = float(comp.get("Sn", 0) or 0.0)

            comp_factor = 0.0
            comp_factor += self._sat(ag, A=15, tau=3.5)
            comp_factor += self._sat(comp.get("Cu", 0), A=10, tau=2)
            # SAC+Bi 저함량: Bi 1–3%에서 UTS 급상승 (실측·MDPI metals-12-01245)
            if sn >= 50.0 and bi >= 12.0:
                # Sn-rich SAC+Bi(12–35%): Sn57Bi 저Sn 곡선(A=80)과 분리 — Sn1Ag25Bi0.7Cu 등
                comp_factor += self._sat(max(0.0, bi - 8.0), A=36, tau=11)
            elif bi >= 20.0:
                # Ag가 거의 없는 순수 Sn-Bi는 내부 DB 평균이 더 낮아
                # 고Bi(Ag-rich)와 같은 강한 A=80 곡선을 쓰면 과대가 된다.
                if ag >= 0.3:
                    comp_factor += self._sat(bi, A=80, tau=20)
                else:
                    comp_factor += self._sat(bi, A=52, tau=16)
            elif ag >= 0.5 and 0.0 < bi < 12.0:
                comp_factor += self._sat(bi, A=42, tau=2.5)
            elif bi > 0.0:
                comp_factor += self._sat(bi, A=50, tau=15)
            comp_factor += self._sat(comp.get("Sb", 0),  A=35, tau=8)
            comp_factor += self._sat(comp.get("In", 0),  A=12, tau=10)
            comp_factor += self._sat(comp.get("Ni", 0),  A=15, tau=0.5)
            comp_factor += self._sat(comp.get("Zn", 0),  A=10, tau=5)

            return base + temp_factor + comp_factor
        except:
            return 0.0

    # -----------------------------------------------------
    # 항복강도(MPa)
    # -----------------------------------------------------
    def predict_yield_strength(self, comp, solidus, liquidus):
        try:
            tensile = self.predict_tensile_strength(comp, solidus, liquidus)
            bi = comp.get("Bi", 0)
            # Bi 고함량: 항복/인장 비율 상승 (취성 거동)
            ratio = 0.75 + self._sat(bi, A=0.15, tau=20)
            return tensile * ratio
        except:
            return 0.0

    # -----------------------------------------------------
    # 연신율(%)
    # -----------------------------------------------------
    def predict_elongation(self, comp, solidus, liquidus):
        try:
            base = 42.0
            delta_t = max(0, liquidus - solidus)
            base -= delta_t * 0.3

            # 취성 원소 페널티 (포화)
            bi_penalty = self._sat(comp.get("Bi", 0), A=38, tau=15)
            sb_penalty = self._sat(comp.get("Sb", 0), A=20, tau=10)
            cu_penalty = self._sat(comp.get("Cu", 0), A=8,  tau=2)

            return max(3.0, base - bi_penalty - sb_penalty - cu_penalty)
        except:
            return 0.0

    # -----------------------------------------------------
    # 전단강도(MPa)
    # -----------------------------------------------------
    def predict_shear_strength(self, comp, solidus, liquidus):
        try:
            tensile = self.predict_tensile_strength(comp, solidus, liquidus)
            bi = float(comp.get("Bi", 0) or 0.0)
            if bi >= 40.0:
                # Sn-Bi 고함량: 인장 대비 전단 비율 ≈0.30–0.40 (실측 Sn57Bi 등)
                return tensile * 0.40
            # Bi 미량(≥0.3%)부터 SAC+Bi·저Bi SAC에서 전단/인장 비가 급격히 하락
            # (실측 Sn3Ag0.5Cu3Bi shear/tensile≈0.36, Sn4Ag0.5Cu2.5Bi≈0.30).
            # 기존 bi≥5 hard step(×1.55→×0.55)은 0.1%p 변화로 ~70 MPa 전단 점프 유발.
            w = self._smoothstep01((bi - 0.3) / 2.2)  # 0.3%→0, 2.5%→~1
            factor_hi = 1.72  # 무 Bi SAC/SnCu (실측·DB shear/tensile≈1.7–1.8)
            factor_lo = 0.34 + 0.06 * self._smoothstep01(bi / 30.0)
            factor = factor_hi * (1.0 - w) + factor_lo * w
            return tensile * factor
        except:
            return 0.0

    # -----------------------------------------------------
    # 젖음성 지수
    # -----------------------------------------------------
    @staticmethod
    def _ensure_sn(comp):
        # Ensure Sn exists; many parts of the app expect wt% sums close to 100.
        if not isinstance(comp, dict):
            return {}
        total = 0.0
        for v in comp.values():
            try:
                total += float(v or 0.0)
            except Exception:
                pass
        out = dict(comp)
        if "Sn" not in out:
            sn = max(0.0, 100.0 - total)
            out["Sn"] = sn
        return out

    @staticmethod
    def _interp_1d(x, xs, ys):
        """온도 축 등 1D 그리드 — PCHIP(단조 Hermite), scipy 없으면 선형 폴백."""
        if not xs or len(xs) != len(ys):
            return None
        xf = float(x)
        if xf <= float(xs[0]):
            return float(ys[0])
        if xf >= float(xs[-1]):
            return float(ys[-1])
        v = interp_pchip_1d(xf, [float(t) for t in xs], [float(y) for y in ys])
        if v != v:  # NaN
            return None
        return float(v)

    @staticmethod
    def _idw_comp_weight(dist: float, comp: dict) -> float:
        """
        Cu ~0.55–0.72 wt% 구간은 실측 샘플이 성길 때 이웃 가중 전환이 급격해질 수 있음.
        거리 바닥(floor)과 멱을 살짝 올려 IDW 절벽을 완화.
        """
        floor = 1e-6
        power = 1.0
        try:
            cu = float(comp.get("Cu", 0) or 0)
            if 0.55 <= cu <= 0.72:
                floor = max(floor, 0.035)
                power = 1.15
        except (TypeError, ValueError):
            pass
        d = max(0.0, float(dist))
        return 1.0 / (d + floor) ** power

    @staticmethod
    def _rec_fmax_t0_at_temp(rec, temp_c):
        """Single record: fmax/t0 at temp_c (may interpolate within record's temperature grid)."""
        data = rec.get("data") if isinstance(rec, dict) else None
        if not isinstance(data, dict) or not data:
            return None, None
        temps = sorted([int(k) for k in data.keys() if isinstance(k, int) or str(k).isdigit()])
        if not temps:
            return None, None
        f_list = []
        t_list = []
        for tt in temps:
            v = data.get(tt, {})
            try:
                f_list.append(float(v.get("fmax_mn")))
                t_list.append(float(v.get("t0_s")))
            except Exception:
                f_list.append(None)
                t_list.append(None)
        xs = []
        fs = []
        ts = []
        for tt, ff, to in zip(temps, f_list, t_list):
            if ff is None or to is None:
                continue
            xs.append(float(tt))
            fs.append(float(ff))
            ts.append(float(to))
        if len(xs) < 2:
            if xs:
                return fs[0], ts[0]
            return None, None
        f_i = PropertyModels._interp_1d(float(temp_c), xs, fs)
        t_i = PropertyModels._interp_1d(float(temp_c), xs, ts)
        return f_i, t_i

    def _predict_wetting_at_single_temp(self, comp, t_test):
        """
        IDW in composition space at fixed test temperature t_test.
        Returns fmax (mN), t0 (s), 10–100 wetting_score, neighbors (same as legacy).
        """
        comp = self._ensure_sn(comp)
        t_test = float(t_test)

        f_terms = []
        t_terms = []
        w_terms = []
        neighbors = []

        f_vals = []
        t_vals = []
        for rec in WETTING_DB:
            f_i, t_i = self._rec_fmax_t0_at_temp(rec, t_test)
            if f_i is not None and t_i is not None:
                f_vals.append(f_i)
                t_vals.append(t_i)
        if not f_vals:
            raise ValueError("wetting db normalization empty")
        f_min, f_max = min(f_vals), max(f_vals)
        t_min, t_max = min(t_vals), max(t_vals)

        for rec in WETTING_DB:
            d = composition_distance(comp, rec["comp"])
            w = PropertyModels._idw_comp_weight(d, comp)
            f_i, t_i = self._rec_fmax_t0_at_temp(rec, t_test)
            if f_i is None or t_i is None:
                continue
            f_terms.append(f_i * w)
            t_terms.append(t_i * w)
            w_terms.append(w)
            neighbors.append({
                "name": rec.get("name", "N/A"),
                "dist": float(d),
                "weight": float(w),
            })

        if not w_terms:
            raise ValueError("wetting db interpolation empty")

        f_pred = sum(f_terms) / sum(w_terms)
        t_pred = sum(t_terms) / sum(w_terms)

        if abs(f_max - f_min) < 1e-9:
            f_score = 70.0
        else:
            f_score = 10.0 + 90.0 * (f_pred - f_min) / (f_max - f_min)

        if abs(t_max - t_min) < 1e-9:
            t_score = 70.0
        else:
            t_score = 10.0 + 90.0 * (t_max - t_pred) / (t_max - t_min)

        score = 0.55 * f_score + 0.45 * t_score
        score = max(10.0, min(100.0, float(score)))

        neighbors.sort(key=lambda x: x.get("dist", 9999.0))
        return {
            "wetting_temp_c": float(t_test),
            "fmax_pred_mn": float(f_pred),
            "t0_pred_s": float(t_pred),
            "wetting_score": float(score),
            "neighbors": neighbors[:3],
        }

    def _predict_wetting_by_temperature(self, comp):
        """측정 DB와 동일한 온도(250–290℃)마다 IDW 예측 행(실측 단위 Fmax/T0)."""
        rows = []
        for t in WETTING_TEMPS_C:
            try:
                d = self._predict_wetting_at_single_temp(comp, float(t))
                rows.append({
                    "temp_c": int(t),
                    "fmax_mn": d["fmax_pred_mn"],
                    "t0_s": d["t0_pred_s"],
                })
            except Exception:
                continue
        return rows

    def _predict_wetting_details(
        self, comp, solidus, liquidus, peak=None, wetting_temp_c=None, wetting_temp_basis=None
    ):
        """
        대표 젖음 행( fMAX / T0 / 점수 ).
        - wetting_temp_c 가 있으면: 해당 값을 측정 DB 온도(250–290℃)에 맞춤.
        - 없으면: 액상선+30℃ 후 동일 축에 맞춤 (기본 공정 온도 프록시).
        peak 는 하위 호환용으로만 남김(젖음 온도 선택에는 사용하지 않음).
        """
        comp = self._ensure_sn(comp)
        liq = float(liquidus or 0.0)
        if wetting_temp_c is not None:
            t_test = snap_wetting_temp_to_bd_grid(float(wetting_temp_c))
            basis = wetting_temp_basis or "user"
            target_for_ui = float(wetting_temp_c)
        else:
            t_test = default_wetting_temp_c(liq)
            basis = "auto_liq_plus_30"
            target_for_ui = liq + 30.0
        d = self._predict_wetting_at_single_temp(comp, t_test)
        d["wetting_temp_basis"] = basis
        d["wetting_temp_target_c"] = float(target_for_ui)
        return d

    def predict_wetting(self, comp, solidus, liquidus, peak=None, wetting_temp_c=None):
        try:
            return self._predict_wetting_details(
                comp, solidus, liquidus, peak=peak, wetting_temp_c=wetting_temp_c
            )["wetting_score"]
        except Exception as e:
            log_exception("predict_wetting fallback", e)
            # Fallback to heuristic if DB interpolation fails.
            span = max(0, float(liquidus or 0.0) - float(solidus or 0.0))
            base = 80.0 - span * 0.6
            base += self._sat(comp.get("In", 0), A=8,  tau=5)
            base += self._sat(comp.get("Bi", 0), A=6,  tau=15)
            if comp.get("Cu", 0) > 1.0:
                base -= (comp.get("Cu", 0) - 1.0) * 2.0
            return max(10.0, min(100.0, base))

    # -----------------------------------------------------
    # 전체 예측
    # -----------------------------------------------------
    def predict_all(
        self,
        comp,
        solidus=None,
        liquidus=None,
        peak=None,
        wetting_temp_c=None,
        wetting_temp_basis=None,
        include_wetting_grid=False,
    ):
        s = solidus  if solidus  is not None else 0
        l = liquidus if liquidus is not None else 0

        try: tensile = self.predict_tensile_strength(comp, s, l)
        except: tensile = 0.0

        try: yield_s = self.predict_yield_strength(comp, s, l)
        except: yield_s = 0.0

        try: elong = self.predict_elongation(comp, s, l)
        except: elong = 0.0

        try: shear = self.predict_shear_strength(comp, s, l)
        except: shear = 0.0

        wet_details = None
        wetting_by_temp = []
        try:
            wet_details = self._predict_wetting_details(
                comp, s, l, peak=peak, wetting_temp_c=wetting_temp_c, wetting_temp_basis=wetting_temp_basis
            )
            wet = float(wet_details.get("wetting_score", 0.0) or 0.0)
            if include_wetting_grid:
                try:
                    wetting_by_temp = self._predict_wetting_by_temperature(comp)
                except Exception:
                    wetting_by_temp = []
        except Exception:
            # IDW 실패 시 predict_wetting()이 동일 조성에 대해 휴리스틱 젖음 지수를 돌려줌 (0 고정 방지)
            wet = float(self.predict_wetting(comp, s, l, peak=peak, wetting_temp_c=wetting_temp_c) or 0.0)

        out = {
            "tensile_strength": float(tensile),
            "yield_strength":   float(yield_s),
            "elongation":       float(elong),
            "shear_strength":   float(shear),
            "wetting_score":    float(wet),
        }
        if isinstance(wet_details, dict):
            out["wetting_temp_c"] = float(wet_details.get("wetting_temp_c", 0.0) or 0.0)
            out["wetting_fmax_pred_mn"] = float(wet_details.get("fmax_pred_mn", 0.0) or 0.0)
            out["wetting_t0_pred_s"] = float(wet_details.get("t0_pred_s", 0.0) or 0.0)
            out["wetting_neighbors"] = wet_details.get("neighbors", [])
            out["wetting_by_temp"] = wetting_by_temp
            wb = wet_details.get("wetting_temp_basis")
            if wb:
                out["wetting_temp_basis"] = str(wb)
            wt = wet_details.get("wetting_temp_target_c")
            if wt is not None:
                try:
                    out["wetting_temp_target_c"] = float(wt)
                except Exception:
                    pass
        else:
            out["wetting_by_temp"] = []
        return out
