# models.py (Improved v2.1)
# 물성 예측 모델 - 조성 기반 보정 강화 + 고함량 원소 클램핑
# 수정: Bi 고함량 시 선형 오버플로 방지 → 포화 함수 적용

import math

from .utils import composition_distance
from .utils import log_exception
from .wetting_db import WETTING_DB, WETTING_TEMPS_C
from .interp_pchip import interp_pchip_1d

_WETTING_EXACT_EPS = 1e-4
_WETTING_LEGACY_MISSING_CONDITIONS = (
    "source_identifier",
    "test_standard",
    "substrate_and_finish",
    "test_atmosphere",
    "flux_amount",
    "replicate_count",
)


def _optional_finite_float(value):
    if type(value) is bool or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def clamp_wetting_temp_to_db_range(target_c: float) -> float:
    """측정 DB 온도 범위(250–290℃)로만 클램프한다(격자 스냅 없음).

    측정 온도 사이 값은 레코드별로 온도 선형 보간해 평가하므로, 목표 온도가
    격자 경계(예: 285℃)를 넘을 때 평가 온도가 10℃씩 건너뛰며 점수가 튀지 않는다.
    """
    target = _optional_finite_float(target_c)
    if target is None:
        raise ValueError("wetting temperature must be finite")
    lo, hi = min(WETTING_TEMPS_C), max(WETTING_TEMPS_C)
    return float(max(min(target, hi), lo))


def default_wetting_temp_c(liquidus: float) -> float:
    """기본: 액상선+30℃를 측정 DB 온도 범위(250–290℃)로 클램프(사이 온도는 보간)."""
    liquidus_value = _optional_finite_float(liquidus)
    if liquidus_value is None:
        raise ValueError("liquidus is required for automatic wetting temperature")
    return clamp_wetting_temp_to_db_range(liquidus_value + 30.0)


def compare_default_wetting_temp_c(liquidus_a: float, liquidus_b: float) -> float:
    """비교 모드 자동: 더 높은 액상선+30℃ 목표(DB 온도 범위로 클램프)를 공통 온도로 사용."""
    # A missing liquidus is an unavailable prediction, not 0 °C.  Do not let
    # the DB-grid clamp turn that sentinel into a plausible 250 °C test point.
    ta = default_wetting_temp_c(liquidus_a)
    tb = default_wetting_temp_c(liquidus_b)
    return float(max(ta, tb))

# 순수 Sn 인장강도(MPa) — 물성 DB LT 데이터시트 Sn100 실측
_PURE_SN_TENSILE_MPA = 14.0


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
    # Bi 인장 기여 (연속)
    # -----------------------------------------------------
    @classmethod
    def _bi_tensile_term(cls, sn, bi, ag):
        """
        Bi가 인장강도에 더하는 몫(MPa).

        [2026-09-30 계산 로직 2차 점검 P1] 이전에는 if/elif 분기(Sn 50 %, Bi 12·20 %,
        Ag 0.3·0.5 %)마다 다른 곡선을 골라 경계에서 값이 튀었다
        (Sn49.9Bi50.1 → Sn50.1Bi49.9 인장 −15 MPa, Ag 0.4 %면 −38 MPa; Ag 없는 Bi 11.99 → 12 % +14 MPa).
        같은 곡선들을 매끈한 가중으로 섞는다. 경계에서 먼 조성(DB 합금 포함)은 이전 값과 같다.
          · 저Bi 곡선: Ag 0.3 → 0.7 %에서 A=50/τ=15 → A=42/τ=2.5 (SAC+Bi 강화)
          · Sn-rich 고Bi 곡선: Bi 12 → 18 %에서 저Bi 곡선 → A=36/τ=11
          · Bi-rich 곡선(Sn58Bi 쪽): Ag 0.2 → 0.4 %에서 A=52/τ=16 → A=80/τ=20
          · Bi-rich 가중 = [Bi 18 → 22 %] × [Sn 54 → 46 %]
        """
        if bi <= 0.0:
            return 0.0
        s = cls._smoothstep01
        a_lo = s((ag - 0.3) / 0.4)
        low_bi = cls._sat(bi, A=50, tau=15) * (1.0 - a_lo) + cls._sat(bi, A=42, tau=2.5) * a_lo
        high_bi = cls._sat(max(0.0, bi - 8.0), A=36, tau=11)
        t_hi = s((bi - 12.0) / 6.0)
        sn_rich = low_bi * (1.0 - t_hi) + high_bi * t_hi
        a_hi = s((ag - 0.2) / 0.2)
        bi_rich = cls._sat(bi, A=52, tau=16) * (1.0 - a_hi) + cls._sat(bi, A=80, tau=20) * a_hi
        r = s((bi - 18.0) / 4.0) * (1.0 - s((sn - 46.0) / 8.0))
        return sn_rich * (1.0 - r) + bi_rich * r

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

            inp = float(comp.get("In", 0) or 0.0)
            pb = float(comp.get("Pb", 0) or 0.0)
            zn = float(comp.get("Zn", 0) or 0.0)

            comp_factor = 0.0
            comp_factor += self._sat(ag, A=15, tau=3.5)
            comp_factor += self._sat(comp.get("Cu", 0), A=10, tau=2)
            comp_factor += self._bi_tensile_term(sn, bi, ag)
            comp_factor += self._sat(comp.get("Sb", 0),  A=35, tau=8)
            comp_factor += self._sat(inp, A=12, tau=10)
            comp_factor += self._sat(comp.get("Ni", 0),  A=15, tau=0.5)
            # [2026-09-30 계산 로직 2차 점검 P2] 원소 항 보정 (물성 DB 실측 기준)
            #  - Zn: A=10 → 30 (Sn8Zn3Bi 실측 78 MPa, 이전 모델 53)
            #  - Pb: 항이 없었음 (Sn63Pb37 실측 47, 이전 모델 37)
            #  - In 고함량 연화: In은 무르므로 8 % 넘으면 강도가 크게 떨어짐 (Sn42In1Cu1Zn 실측 19, 이전 모델 54)
            comp_factor += self._sat(zn, A=30, tau=4)
            comp_factor += self._sat(pb, A=12, tau=15)
            comp_factor -= self._sat(max(0.0, inp - 8.0), A=45, tau=20)

            alloyed = base + temp_factor + comp_factor
            # 순수 Sn은 합금 모델 기준값(29 + 온도항 8 = 37)보다 훨씬 약함(실측 14 MPa).
            # 미량 첨가로도 빠르게 강해지므로 전체 첨가량 s에 대해 14 → 합금값으로 매끈하게 올린다.
            solute = max(0.0, 100.0 - sn) if sn > 0 else sum(
                float(v or 0.0) for k, v in comp.items() if k != "Sn"
            )
            dilute = 1.0 - math.exp(-solute / 0.35)
            return _PURE_SN_TENSILE_MPA + (alloyed - _PURE_SN_TENSILE_MPA) * dilute
        except Exception as exc:
            log_exception("predict tensile unavailable", exc)
            return None

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
        except Exception as exc:
            log_exception("predict yield unavailable", exc)
            return None

    # -----------------------------------------------------
    # 연신율(%)
    # -----------------------------------------------------
    def predict_elongation(self, comp, solidus, liquidus):
        """
        [2026-09-30 계산 로직 2차 점검 P2] 이전 모델은 고상–액상 간격 ΔT × 0.3 %p를 깎았는데,
        실측은 ΔT와 무관했다(Sn3.0Cu ΔT 85 ℃ 32 %, Sn3.0Cu0.5Ni ΔT 166 ℃ 30 % — 모델 10 %, 3 %).
        Bi도 방향이 틀렸다: 2.5~3 %만 넣어도 10~17 %로 크게 떨어지고(모델 28~32 %),
        공정 Sn58Bi는 오히려 24~25 %(모델 3~5 %). ΔT 항을 빼고 Bi를 "빠르게 떨어졌다가 공정 쪽에서 일부 회복"
        모양으로 바꾸고 Pb·In 감소 항을 넣었다. 인자는 물성 DB 실측에 맞춘 값.
        """
        try:
            # 융점 예측이 없으면 물성도 '예측 불가'로 둔다(다른 물성 모델과 같은 규칙).
            float(liquidus) - float(solidus)
            base = 42.0
            bi = float(comp.get("Bi", 0) or 0.0)
            zn = float(comp.get("Zn", 0) or 0.0)
            pb = float(comp.get("Pb", 0) or 0.0)
            inp = float(comp.get("In", 0) or 0.0)

            bi_penalty = 30.0 * (1.0 - math.exp(-max(0.0, bi) / 1.2))
            bi_penalty *= 1.0 - 0.45 * self._smoothstep01((bi - 15.0) / 40.0)
            # Sn-Zn 기지에서는 같은 Bi 3 %여도 연신이 유지됨(Sn8Zn3Bi 실측 34.7 %) — 실측 1개 기준.
            bi_penalty *= 1.0 - 0.7 * self._smoothstep01(zn / 8.0)
            sb_penalty = self._sat(comp.get("Sb", 0), A=20, tau=10)
            cu_penalty = self._sat(comp.get("Cu", 0), A=6, tau=2)
            pb_penalty = self._sat(pb, A=25, tau=15)
            in_penalty = self._sat(max(0.0, inp - 5.0), A=30, tau=25)

            return max(
                3.0,
                base - bi_penalty - sb_penalty - cu_penalty - pb_penalty - in_penalty,
            )
        except Exception as exc:
            log_exception("predict elongation unavailable", exc)
            return None

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
        except Exception as exc:
            log_exception("predict shear unavailable", exc)
            return None

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
        젖음성 IDW 가중 = 1 / (거리 + 1e-3)².

        [2026-09-30 계산 로직 2차 점검 P1] 이전: 1/거리(멱 1), Cu 0.55–0.72 %에서만 바닥 0.035·멱 1.15.
        그 Cu 구간 규칙 때문에 거리 → 0에서도 실측 행 값으로 수렴하지 않아 정확일치 행과 바로 옆이
        달랐고(Sn0.7Cu 젖음 점수 10.0 → Cu +0.01 %에 15.2, +0.1 %에 27.6), Cu 0.55·0.72 % 경계에도
        작은 계단이 있었다. 멱 2는 실측점에서 기울기가 0이라 정확일치와 이웃이 매끈하게 이어진다
        (10.0 → 10.1 → 15.1). 6개 합금 leave-one-out 오차는 Fmax 0.184 → 0.193 mN, T0 0.156 → 0.162 s로
        거의 같다. ``comp`` 인자는 호출부 호환을 위해 남겨 둔다.
        """
        d = max(0.0, float(dist))
        return 1.0 / (d + 1e-3) ** 2

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
        # 측정 온도(격자) 사이에서 평가하면 각 레코드 값은 온도 선형 보간값이다.
        temp_interpolated = not any(abs(t_test - float(g)) < 1e-9 for g in WETTING_TEMPS_C)

        f_terms = []
        t_terms = []
        w_terms = []
        neighbors = []

        # 점수 정규화는 DB 전체(모든 합금 × 모든 측정 온도)의 Fmax·T0 범위로 고정한다.
        # 온도마다 그 온도의 6개 합금 min–max로 늘이면, 고온에서 합금 간 차이가
        # 0.1 mN뿐이어도 10↔100점으로 벌어져 평가 온도가 몇 ℃만 움직여도 점수가 크게 흔들렸다.
        f_vals = []
        t_vals = []
        for rec in WETTING_DB:
            for grid_t in WETTING_TEMPS_C:
                f_i, t_i = self._rec_fmax_t0_at_temp(rec, float(grid_t))
                if f_i is not None and t_i is not None:
                    f_vals.append(f_i)
                    t_vals.append(t_i)
        if not f_vals:
            raise ValueError("wetting db normalization empty")
        f_min, f_max = min(f_vals), max(f_vals)
        t_min, t_max = min(t_vals), max(t_vals)

        # An exact composition is a measured DB row, not an interpolation.
        # Return that row directly so the value and its evidence cannot be
        # contaminated by even a numerically tiny contribution from neighbors.
        for rec in WETTING_DB:
            exact_dist = float(composition_distance(comp, rec["comp"]))
            if exact_dist > _WETTING_EXACT_EPS:
                continue
            f_exact, t_exact = self._rec_fmax_t0_at_temp(rec, t_test)
            if f_exact is None or t_exact is None:
                continue
            if abs(f_max - f_min) < 1e-9:
                f_score = 70.0
            else:
                f_score = 10.0 + 90.0 * (f_exact - f_min) / (f_max - f_min)
            if abs(t_max - t_min) < 1e-9:
                t_score = 70.0
            else:
                t_score = 10.0 + 90.0 * (t_max - t_exact) / (t_max - t_min)
            score = max(10.0, min(100.0, float(0.55 * f_score + 0.45 * t_score)))
            confidence_neighbors = []
            for neighbor_rec in WETTING_DB:
                neighbor_dist = float(composition_distance(comp, neighbor_rec["comp"]))
                f_neighbor, t_neighbor = self._rec_fmax_t0_at_temp(
                    neighbor_rec, t_test
                )
                if f_neighbor is None or t_neighbor is None:
                    continue
                confidence_neighbors.append(
                    {
                        "name": neighbor_rec.get("name", "N/A"),
                        "dist": neighbor_dist,
                        "weight": float(
                            PropertyModels._idw_comp_weight(neighbor_dist, comp)
                        ),
                    }
                )
            confidence_neighbors.sort(key=lambda x: x.get("dist", 9999.0))
            return {
                "wetting_temp_c": float(t_test),
                "fmax_pred_mn": float(f_exact),
                "t0_pred_s": float(t_exact),
                "wetting_score": score,
                "neighbors": [
                    {
                        "name": rec.get("name", "N/A"),
                        "dist": exact_dist,
                        "weight": 1.0,
                        "weight_share": 1.0,
                    }
                ],
                # Confidence remains calibrated against the same three-distance
                # support profile used before the exact-value short-circuit.
                "confidence_neighbors": confidence_neighbors[:3],
                "wetting_metadata": {
                    "source_kind": "measured_db",
                    "value_type": "direct_db_record",
                    "exact_match": True,
                    "nearest_distance": exact_dist,
                    "provenance_status": "unconfirmed",
                    "verification_status": "unverified",
                    "comparison_allowed": False,
                    "reason_code": "WETTING_PROVENANCE_UNCONFIRMED",
                    "missing_conditions": list(_WETTING_LEGACY_MISSING_CONDITIONS),
                    "neighbor_semantics": "value_contributors_v2",
                    "confidence_neighbor_semantics": "distance_support_v1",
                    "temperature_interpolated": temp_interpolated,
                },
            }

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
        nearest_distance = (
            float(neighbors[0]["dist"])
            if neighbors and neighbors[0].get("dist") is not None
            else None
        )
        exact_match = (
            nearest_distance is not None
            and nearest_distance <= _WETTING_EXACT_EPS
        )
        return {
            "wetting_temp_c": float(t_test),
            "fmax_pred_mn": float(f_pred),
            "t0_pred_s": float(t_pred),
            "wetting_score": float(score),
            "neighbors": neighbors[:3],
            "wetting_metadata": {
                "source_kind": "measured_db" if exact_match else "idw_prediction",
                "value_type": "direct_db_record" if exact_match else "idw_prediction",
                "exact_match": bool(exact_match),
                "nearest_distance": nearest_distance,
                "provenance_status": "unconfirmed",
                "verification_status": "unverified",
                "comparison_allowed": False,
                "reason_code": "WETTING_PROVENANCE_UNCONFIRMED",
                "missing_conditions": list(_WETTING_LEGACY_MISSING_CONDITIONS),
                "neighbor_semantics": "value_contributors_v2",
                "confidence_neighbor_semantics": "distance_support_v1",
                "temperature_interpolated": temp_interpolated,
            },
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
        - wetting_temp_c 가 있으면: 해당 값을 측정 DB 온도 범위(250–290℃)로 클램프.
        - 없으면: 액상선+30℃ 후 동일 범위로 클램프 (기본 공정 온도 프록시).
        - 측정 온도 사이 값은 레코드별 온도 선형 보간(점수 정규화도 같은 온도에서).
        peak 는 하위 호환용으로만 남김(젖음 온도 선택에는 사용하지 않음).
        """
        comp = self._ensure_sn(comp)
        if wetting_temp_c is not None:
            t_test = clamp_wetting_temp_to_db_range(float(wetting_temp_c))
            basis = wetting_temp_basis or "user"
            target_for_ui = float(wetting_temp_c)
        else:
            liq = _optional_finite_float(liquidus)
            if liq is None:
                raise ValueError("liquidus is required for automatic wetting prediction")
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
        s = solidus
        l = liquidus

        # A failed property model means "unavailable", not a physically measured
        # zero.  Downstream DB/literature layers may still fill these values.
        try:
            tensile = self.predict_tensile_strength(comp, s, l)
        except Exception as exc:
            log_exception("predict tensile unavailable", exc)
            tensile = None

        try:
            yield_s = self.predict_yield_strength(comp, s, l)
        except Exception as exc:
            log_exception("predict yield unavailable", exc)
            yield_s = None

        try:
            elong = self.predict_elongation(comp, s, l)
        except Exception as exc:
            log_exception("predict elongation unavailable", exc)
            elong = None

        try:
            shear = self.predict_shear_strength(comp, s, l)
        except Exception as exc:
            log_exception("predict shear unavailable", exc)
            shear = None

        wet_details = None
        wet = None
        wetting_by_temp = []
        # Automatic wetting temperature depends on a real liquidus.  If melting
        # failed, keep wetting unavailable instead of snapping a fake 30℃ target
        # to the 250℃ DB row.  A user-supplied test temperature remains usable.
        if wetting_temp_c is not None or liquidus is not None:
            try:
                wet_details = self._predict_wetting_details(
                    comp, s, l, peak=peak, wetting_temp_c=wetting_temp_c, wetting_temp_basis=wetting_temp_basis
                )
                wet_value = wet_details.get("wetting_score")
                wet = float(wet_value) if wet_value is not None else None
                if include_wetting_grid:
                    try:
                        wetting_by_temp = self._predict_wetting_by_temperature(comp)
                    except Exception:
                        wetting_by_temp = []
            except Exception:
                # IDW 실패 시 명시 온도 또는 유효 액상선에 대해서만 휴리스틱을 사용한다.
                wet_fallback = self.predict_wetting(
                    comp, s, l, peak=peak, wetting_temp_c=wetting_temp_c
                )
                wet = float(wet_fallback) if wet_fallback is not None else None

        out = {
            "tensile_strength": float(tensile) if tensile is not None else None,
            "yield_strength":   float(yield_s) if yield_s is not None else None,
            "elongation":       float(elong) if elong is not None else None,
            "shear_strength":   float(shear) if shear is not None else None,
            "wetting_score":    float(wet) if wet is not None else None,
        }
        if isinstance(wet_details, dict):
            out["wetting_temp_c"] = _optional_finite_float(wet_details.get("wetting_temp_c"))
            out["wetting_fmax_pred_mn"] = _optional_finite_float(wet_details.get("fmax_pred_mn"))
            out["wetting_t0_pred_s"] = _optional_finite_float(wet_details.get("t0_pred_s"))
            out["wetting_neighbors"] = wet_details.get("neighbors", [])
            confidence_neighbors = wet_details.get("confidence_neighbors")
            if isinstance(confidence_neighbors, list):
                out["wetting_confidence_neighbors"] = confidence_neighbors
            out["wetting_by_temp"] = wetting_by_temp
            wetting_metadata = wet_details.get("wetting_metadata")
            if isinstance(wetting_metadata, dict):
                out["wetting_metadata"] = dict(wetting_metadata)
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
