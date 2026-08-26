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


def snap_wetting_temp_to_bd_grid(target_c: float) -> float:
    """250–290℃ 범위로 클램프한 뒤, 측정 DB와 동일한 입력 온도 목록에 가장 가깝게 스냅."""
    target = _optional_finite_float(target_c)
    if target is None:
        raise ValueError("wetting temperature must be finite")
    lo, hi = min(WETTING_TEMPS_C), max(WETTING_TEMPS_C)
    t = max(min(target, hi), lo)
    return float(min(WETTING_TEMPS_C, key=lambda x: (abs(x - t), -x)))


def default_wetting_temp_c(liquidus: float) -> float:
    """기본: 액상선+30℃를 측정 DB 온도 축(250–290℃)에 맞춤."""
    liquidus_value = _optional_finite_float(liquidus)
    if liquidus_value is None:
        raise ValueError("liquidus is required for automatic wetting temperature")
    return snap_wetting_temp_to_bd_grid(liquidus_value + 30.0)


def compare_default_wetting_temp_c(liquidus_a: float, liquidus_b: float) -> float:
    """비교 모드 자동: 더 높은 액상선+30℃ 목표를 DB 격자에 한 번 스냅해 공통 온도로 사용."""
    # A missing liquidus is an unavailable prediction, not 0 °C.  Do not let
    # the DB-grid clamp turn that sentinel into a plausible 250 °C test point.
    ta = default_wetting_temp_c(liquidus_a)
    tb = default_wetting_temp_c(liquidus_b)
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
            # SAC+Bi: the low-Bi strengthening curve and the Sn-rich high-Bi
            # curve describe different regimes.  Blend them over 12–18 wt%
            # Bi so an input rounding at 12.00% cannot create a 30 MPa step.
            if sn >= 50.0 and bi >= 12.0:
                low_bi = self._sat(bi, A=42, tau=2.5)
                high_bi = self._sat(max(0.0, bi - 8.0), A=36, tau=11)
                transition = self._smoothstep01((bi - 12.0) / 6.0)
                comp_factor += low_bi * (1.0 - transition) + high_bi * transition
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
        try:
            base = 42.0
            delta_t = max(0, liquidus - solidus)
            base -= delta_t * 0.3

            # 취성 원소 페널티 (포화)
            bi_penalty = self._sat(comp.get("Bi", 0), A=38, tau=15)
            sb_penalty = self._sat(comp.get("Sb", 0), A=20, tau=10)
            cu_penalty = self._sat(comp.get("Cu", 0), A=8,  tau=2)

            return max(3.0, base - bi_penalty - sb_penalty - cu_penalty)
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
        - wetting_temp_c 가 있으면: 해당 값을 측정 DB 온도(250–290℃)에 맞춤.
        - 없으면: 액상선+30℃ 후 동일 축에 맞춤 (기본 공정 온도 프록시).
        peak 는 하위 호환용으로만 남김(젖음 온도 선택에는 사용하지 않음).
        """
        comp = self._ensure_sn(comp)
        if wetting_temp_c is not None:
            t_test = snap_wetting_temp_to_bd_grid(float(wetting_temp_c))
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
