# ============================================================
#  analyzer.py — Hybrid melting (melting_predictor) + AI 디스크 캐시
#  AI 캐시 키: mode/lit/조성 + mv(융점 엔진 버전) + solder_db 지문
# ============================================================

from functools import lru_cache
import math
from .utils import composition_distance
from .phase import PhasePredictor
from .models import PropertyModels
from .ai_engine import AIEngine
from .cerebras_melting import CerebrasMeltingDeltaEngine
from .db_regression import predict_from_db
from .melting_predictor import MELTING_ENGINE_VERSION, hybrid_melting_predict
import os
from . import ai_cache

# DB 정확 일치 판정 임계값 — melting_predictor와 동일한 기준.
_DB_EXACT_EPS = 1e-4

# Bump whenever cached narrative/report safety rules change.  Keeping this in
# the cache key prevents an older recommendation or provenance claim from
# reappearing after the deterministic policy has been tightened.
_AI_REPORT_POLICY_VERSION = "property-provenance-v2-20260821"

# DB 정확 일치 시 AI를 어떻게 다룰지 결정하는 플래그:
#   "cache_first" (기본): 캐시에 기존 AI 응답이 있으면 재사용, 없으면 AI 1회 호출 → 영구 저장
#                        → 첫 호출 이후 품질/서술 완전 동일, API 0회. 가장 안전한 선택.
#   "skip":              로컬 폴백만 사용 (규칙 기반 서술). API 완전 0회지만 서술 간결.
#   "always":            DB 정확 일치여도 매번 정상 AI 호출 (= 기존 동작, 캐시만 적용).
# 환경변수 AI_DB_EXACT_MODE=skip / always 로 전환 가능.
_AI_DB_EXACT_MODE = os.environ.get("AI_DB_EXACT_MODE", "cache_first").strip().lower()
if _AI_DB_EXACT_MODE not in ("cache_first", "skip", "always"):
    _AI_DB_EXACT_MODE = "cache_first"


# ------------------------------------------------------------
# 거리 계산 캐싱
# ------------------------------------------------------------
@lru_cache(maxsize=2048)
def cached_distance(a_tuple, b_tuple):
    a = dict(a_tuple)
    b = dict(b_tuple)
    return composition_distance(a, b)


def _property_db_weight(best_dist):
    """
    물성 DB 가중치.

    가까운 DB는 더 강하게 신뢰하고, 1 wt% 이내는 사실상 DB 우선으로 둔다.
    """
    if best_dist is None:
        return 0.0
    try:
        d0 = float(best_dist)
    except Exception:
        return 0.0
    if d0 <= 1.0:
        return 1.0
    if d0 <= 2.0:
        return max(0.0, min(0.95, 1.0 / (1.0 + d0 / 1.4)))
    if d0 <= 3.0:
        return max(0.0, min(0.80, 1.0 / (1.0 + d0 / 2.4)))
    return 0.0


_MECHANICAL_PROPERTY_KEYS = (
    "tensile_strength",
    "yield_strength",
    "elongation",
    "shear_strength",
)
_LEGACY_MECHANICAL_MISSING_CONDITIONS = (
    "source_identifier",
    "test_standard",
    "specimen_geometry",
    "test_temperature",
    "loading_rate",
    "thermal_history",
)


def _mechanical_property_metadata(props, prop_sources, db_best_dist):
    """Conservative provenance contract for displayed mechanical values."""
    values = props if isinstance(props, dict) else {}
    sources = prop_sources if isinstance(prop_sources, dict) else {}
    try:
        db_exact_hit = (
            db_best_dist is not None
            and float(db_best_dist) <= _DB_EXACT_EPS
        )
    except Exception:
        db_exact_hit = False

    out = {}
    for key in _MECHANICAL_PROPERTY_KEYS:
        if values.get(key) is None:
            continue
        source_label = str(sources.get(key) or "MODEL")
        if source_label.startswith("DB("):
            if "IDW" in source_label:
                value_type = "idw_prediction"
            elif db_exact_hit:
                value_type = "legacy_measured_mean"
            else:
                value_type = "legacy_db_estimate"
            source_type = "legacy_property_db"
            provenance_status = "unconfirmed"
            reason_code = "LEGACY_MECHANICAL_PROVENANCE_UNCONFIRMED"
            missing_conditions = list(_LEGACY_MECHANICAL_MISSING_CONDITIONS)
        elif source_label.startswith("LIT("):
            value_type = "literature_reference"
            source_type = "literature"
            provenance_status = "reference_only"
            reason_code = "LITERATURE_VALUE_NOT_CONDITION_NORMALIZED"
            missing_conditions = []
        else:
            value_type = "model_prediction"
            source_type = "model"
            provenance_status = "derived"
            reason_code = "MODEL_PREDICTION_NOT_MEASUREMENT_VERIFIED"
            missing_conditions = []

        out[key] = {
            "value_type": value_type,
            "source_type": source_type,
            "source_label": source_label,
            "provenance_status": provenance_status,
            "verification_status": "unverified",
            "comparison_allowed": False,
            "reason_code": reason_code,
            "missing_conditions": missing_conditions,
        }
    return out


def _imc_line_to_plain_korean(s: str) -> str:
    """IMC 한 줄을 비전문가용 표현으로 통일(이미 쉬운 문장이면 유지)."""
    t = str(s).strip()
    if not t:
        return t
    low = t.lower()
    # 알려진 IMC는 AI 수식어를 그대로 신뢰하지 않고 용어집 문장으로 고정한다.
    # 예: Ag3Sn을 "약한 층"으로 쓰는 상충 설명을 차단한다.
    if "규칙 기반으로는 지배적" in t:
        return "이 조성만으로는 어떤 합금층이 가장 두드러지는지 특정하기 어렵습니다."
    if "ag3sn" in low or "sn-ag" in low:
        return "은과 주석이 만나 생기는 단단한 층(약칭: Ag3Sn)"
    if "cu6sn5" in low:
        return "구리와 주석이 만나 생기는 단단한 층(약칭: Cu6Sn5)"
    if "cu3sn" in low:
        return "오래 가열하면 두꺼워질 수 있는 구리·주석 반응층(약칭: Cu3Sn)"
    if "(ni,cu)6sn5" in low or "ni3sn4" in low:
        return "니켈·구리·주석이 함께 만든 단단한 층(일명 (Ni,Cu)6Sn5 등)"
    # [2026-09-21 웹 점검 패치] "bi 농화" 를 원문 t(대문자 "Bi")에서 찾아 매칭되지 않던 버그 수정 → low 사용.
    #   결과: Sn-58Bi 결과에서 같은 Bi 분산상이 쉬운 문장·원문으로 두 번 나오던 문제 해소.
    if "bi 농화" in low or "bi-rich" in low or "비스무스가 많을" in t:
        return "비스무스가 많을 때 생길 수 있는 작은 알갱이 모양 층"
    if "in-rich" in low or "insn" in low:
        return "인듐이 많을 때 생길 수 있는 저융점 층"
    if "zn-rich" in low or "sn-zn" in low:
        return "아연이 많을 때 생길 수 있는 층"
    if "pb-rich" in low or "sn-pb" in low:
        return "납이 있을 때 생길 수 있는 층(규제 확인 필요)"
    if "snsb" in low:
        return "안티몬과 주석이 만난 층"
    hangul = sum(1 for c in t if "\uac00" <= c <= "\ud7a3")
    if hangul >= 10 and ("약칭" in t or "만나" in t or "단단한" in t):
        return t
    return t


def _mentions_unentered_element(text: str, norm: dict) -> bool:
    """AI 문장에 입력하지 않은 명시적 원소명이 섞이면 표시하지 않는다."""
    raw = str(text or "")
    low = raw.lower()
    explicit_mentions = {
        "As": ("비소", "arsenic", "(as)", " as 원소", "as 첨가"),
    }
    for symbol, markers in explicit_mentions.items():
        if float(norm.get(symbol, 0.0) or 0.0) <= 0 and any(
            marker in low if marker.isascii() else marker in raw
            for marker in markers
        ):
            return True
    return False


class AlloyAnalyzer:
    # DB/물성 커버리지가 높은 핵심 솔더 원소(이 외는 미지 금속으로 페널티·경고)
    KNOWN_CORE_ELEMENTS = frozenset({"Sn", "Ag", "Cu", "Bi", "In", "Sb", "Ni", "Zn", "Pb"})
    # 주기율표(금속만 보기)·비교 태그용: UI에서 다루는 원소 집합(핵심 + 부가 금속)
    KNOWN_PERIODIC_METALS = frozenset(
        KNOWN_CORE_ELEMENTS
        | {
            "Ge", "Co", "Ga", "Au", "Pd", "Pt", "Al",
            "Cd", "Cr", "Hg", "Tl", "Se", "Te", "P",
        }
    )

    @staticmethod
    def canonical_element_symbol(sym: str) -> str:
        """원소 기호를 Sn, Cu 형태로 통일(대소문자·공백 허용)."""
        s = str(sym).strip()
        if not s:
            raise ValueError("빈 원소 기호입니다.")
        if len(s) == 1:
            return s.upper()
        return s[0].upper() + s[1:].lower()

    @classmethod
    def validate_input_comp(cls, comp) -> None:
        """
        원시 조성 dict 검증. 실패 시 ValueError — API는 422, GUI는 메시지로 처리.
        """
        if not isinstance(comp, dict) or not comp:
            raise ValueError("조성(comp)은 최소 한 원소 이상 필요합니다.")
        tot = 0.0
        for k, v in comp.items():
            if not isinstance(k, str) or not str(k).strip():
                raise ValueError("원소 기호는 비어 있지 않은 문자열이어야 합니다.")
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k}: wt% 값은 숫자여야 합니다.")
            if fv < 0:
                raise ValueError(f"{k}: wt%는 0 이상이어야 합니다.")
            tot += fv
        if tot <= 0.0:
            raise ValueError("모든 원소 wt%가 0이면 분석할 수 없습니다.")
        for k in comp:
            canon = cls.canonical_element_symbol(k)
            if canon not in cls.KNOWN_PERIODIC_METALS:
                raise ValueError(f"지원하지 않는 원소 기호: {str(k).strip()}")

    def __init__(self, solder_db, ai_engine=None):
        self.db = solder_db
        self.phase_predictor = PhasePredictor()
        self.models = PropertyModels()
        self.ai = ai_engine if ai_engine else AIEngine()
        # 고상선/액상선 L6 델타 보정 전용(고속 추론). 사용 불가 시 휴리스틱으로 폴백.
        self.melting_ai = CerebrasMeltingDeltaEngine()

        self._solder_db_fingerprint = None
        self.db_prepared = []
        self._sync_db_prepared()

    def _sync_db_prepared(self) -> None:
        """
        self.db(solder_db)가 갱신되면 db_prepared를 다시 구축한다.

        - API 장기 실행 중에도 동일 list 객체가 in-place로 바뀌는 경우를 흡수.
        - 지문은 AI 디스크 캐시 키에 포함되어 DB 수정 후 옛 요약이 재사용되지 않게 한다.
        """
        try:
            from .solder_db import fingerprint_solder_db as _fp
        except ImportError:
            from test7.solder_db import fingerprint_solder_db as _fp

        fp = _fp(self.db)
        if fp == self._solder_db_fingerprint and self.db_prepared:
            return
        self._solder_db_fingerprint = fp
        self.db_prepared = [
            {
                "name": item["name"],
                "comp": item["comp"],
                "comp_tuple": tuple(sorted(item["comp"].items())),
                "solidus": item["solidus"],
                "liquidus": item["liquidus"],
                "density": item.get("density"),
            }
            for item in self.db
        ]

    # ============================================================
    # 정규화 (LRU 캐싱)
    # ============================================================
    @lru_cache(maxsize=512)
    def normalize_cached(self, comp_tuple):
        comp = dict(comp_tuple)
        s = sum(comp.values())
        if s == 0:
            return {}
        return {k: v / s * 100 for k, v in comp.items()}

    def normalize(self, comp):
        if not comp:
            return {}
        # 입력에 Sn이 없으면 잔량으로 보정(사용자가 Cu/Ag만 입력하는 케이스 방어)
        c = dict(comp)
        if "Sn" not in c:
            try:
                s = sum(float(v or 0.0) for v in c.values())
            except Exception:
                s = sum(c.values())
            if s < 100.0:
                c["Sn"] = 100.0 - s
        return self.normalize_cached(tuple(sorted(c.items())))

    # ============================================================
    # 거리 계산
    # ============================================================
    def distance(self, a, b):
        return cached_distance(
            tuple(sorted(a.items())),
            tuple(sorted(b.items()))
        )

    # ============================================================
    # 신뢰도 계산 (비선형 스케일 - 수정됨)
    # ============================================================
    @staticmethod
    def calc_confidence(score):
        """
        score=0   → 100%
        score=1   → ~82%  (기존 99% → 과대 평가 수정)
        score=5   → ~50%
        score=10  → ~30%
        score=20  → ~12%
        score>=50 → ~0%
        """
        import math
        return max(0.0, 100.0 * math.exp(-0.12 * score))

    @staticmethod
    def _clamp01(x):
        try:
            x = float(x)
        except Exception:
            return 0.0
        return max(0.0, min(1.0, x))

    def _dist_conf(self, dist):
        # Use the same curve as DB match confidence for interpretability.
        try:
            return float(self.calc_confidence(float(dist)))
        except Exception:
            return 0.0

    def _wetting_conf_from_neighbors(self, neighbors):
        """
        neighbors: list of {name, dist, weight}
        Map composition distance to a 0..100 confidence-like score.
        """
        if not isinstance(neighbors, list) or not neighbors:
            return 0.0
        dists = []
        for n in neighbors[:3]:
            if not isinstance(n, dict):
                continue
            if n.get("dist") is None:
                continue
            try:
                dists.append(float(n.get("dist")))
            except Exception:
                pass
        if not dists:
            return 0.0
        # average distance -> confidence curve
        return float(self.calc_confidence(sum(dists) / max(1, len(dists))))

    def _unknown_element_profile(self, norm):
        """
        Return (unknown_elems, unknown_total_pct) in normalized composition.
        Unknown means not in KNOWN_CORE_ELEMENTS.
        """
        if not isinstance(norm, dict):
            return [], 0.0
        unknown = []
        total = 0.0
        for k, v in norm.items():
            if k in self.KNOWN_CORE_ELEMENTS:
                continue
            try:
                fv = float(v or 0.0)
            except Exception:
                fv = 0.0
            if fv <= 0.0:
                continue
            unknown.append(str(k))
            total += fv
        unknown.sort()
        return unknown, float(total)

    def _db_sample_support_factor(self, alloy_name):
        """
        Return a conservative 0..1 support factor based on DB sample count.

        The composition match can be exact, but if the property database only
        has one or two measurements, the result should not be shown as fully
        certain.
        """
        if not alloy_name:
            return 1.0, 0
        try:
            from .db_regression import get_statistics
        except Exception:
            return 1.0, 0

        stats = get_statistics(alloy_name)
        if not isinstance(stats, dict):
            return 1.0, 0

        counts = []
        for key in ("tensile", "yield_strength", "elongation", "shear"):
            stat = stats.get(key)
            if isinstance(stat, dict):
                try:
                    n = int(stat.get("n") or 0)
                except Exception:
                    n = 0
                if n > 0:
                    counts.append(n)

        if not counts:
            return 0.75, 0

        n = min(counts)
        import math

        support = 0.75 + 0.25 * (1.0 - math.exp(-max(0, n - 1) / 3.0))
        return max(0.75, min(1.0, float(support))), int(n)

    def build_evidence(self, norm, melting_detail, score, conf, props, prop_sources, db_out):
        """
        UI/리포트용 근거 블록. analyze_all 경로와 GUI _run_single 경로에서 공통 사용.
        """
        md = melting_detail if isinstance(melting_detail, dict) else {}
        forced_db = md.get("forced_db") is True
        melting_src = "DB-direct" if forced_db else "Hybrid"
        melting_dist = md.get("best_dist", score)
        wet_neighbors = []
        if isinstance(props, dict) and isinstance(props.get("wetting_neighbors"), list):
            wet_neighbors = props.get("wetting_neighbors")
        wetting_metadata = (
            dict(props.get("wetting_metadata"))
            if isinstance(props, dict) and isinstance(props.get("wetting_metadata"), dict)
            else {}
        )
        wetting_source_kind = str(wetting_metadata.get("source_kind") or "").strip()
        wetting_value_type = str(wetting_metadata.get("value_type") or "").strip()
        if wetting_source_kind == "measured_db" or wetting_value_type in {
            "measured",
            "direct_db_record",
        }:
            wet_src = "Measured(DB-exact)"
        else:
            wet_src = "IDW(DB)" if wet_neighbors else "Heuristic"

        unknown_elems, unknown_total = self._unknown_element_profile(norm)
        unknown_penalty = min(35.0, max(0.0, float(unknown_total)) * 0.7) if unknown_total > 0 else 0.0

        db_top = (db_out.get("top") if isinstance(db_out, dict) else None) or []
        db_tensile_top = (
            (db_out.get("tensile_top") if isinstance(db_out, dict) else None) or db_top
        )
        db_best_dist = None
        try:
            if isinstance(db_top, list) and db_top:
                db_best_dist = float((db_top[0] or {}).get("dist"))
        except Exception:
            db_best_dist = None
        use_db = (db_best_dist is not None) and (db_best_dist <= 3.0)
        db_exact_hit = (db_best_dist is not None) and (db_best_dist <= _DB_EXACT_EPS)
        db_w = _property_db_weight(db_best_dist)
        if db_exact_hit:
            # 실측 DB와 사실상 동일한 조성은 모델 블렌드 없이 DB 값을 그대로 우선한다.
            db_w = 1.0

        db_support_n = None
        db_support_factor = None
        if isinstance(db_top, list) and db_top:
            db_best_name = (db_top[0] or {}).get("alloy")
            try:
                db_support_factor, db_support_n = self._db_sample_support_factor(db_best_name)
            except Exception:
                db_support_factor, db_support_n = None, None

        ps = dict(prop_sources) if isinstance(prop_sources, dict) else {}
        mechanical_metadata = (
            dict(props.get("mechanical_property_metadata"))
            if isinstance(props, dict)
            and isinstance(props.get("mechanical_property_metadata"), dict)
            else _mechanical_property_metadata(props, ps, db_best_dist)
        )
        return {
            "melting": {
                "source": melting_src,
                "best_dist": float(melting_dist) if melting_dist is not None else None,
                "forced_db": forced_db,
            },
            "wetting": {
                "source": wet_src,
                "neighbors": wet_neighbors[:3] if isinstance(wet_neighbors, list) else [],
                **wetting_metadata,
            },
            "props": ps,
            "mechanical_properties": mechanical_metadata,
            "props_db": {
                "best_dist": db_best_dist,
                "use_db": bool(use_db),
                "db_w": float(db_w),
                "support_n": db_support_n,
                "support_factor": float(db_support_factor) if db_support_factor is not None else None,
                "top": db_top[:5] if isinstance(db_top, list) else [],
                "tensile_top": (
                    db_tensile_top[:5] if isinstance(db_tensile_top, list) else []
                ),
            },
            "ai": {
                "enabled": bool(getattr(self.ai, "available", False)),
            },
            "unknown_elements": {
                "names": unknown_elems,
                "total_pct": float(unknown_total),
                "penalty": float(unknown_penalty),
            },
        }

    @staticmethod
    def gui_blend_prop_sources(norm, props_before_blend, score, db_out=None):
        """
        GUI 결과의 물성 출처 라벨 생성.
        - 가능하면 predict_from_db_with_detail() 결과(db_out)로 dist 기반 db_w를 사용해
          analyze_all과 동일한 게이팅/가중치를 맞춥니다.
        - db_out이 없으면 기존(score 기반) 방식으로 폴백합니다.
        """
        keys = (
            "tensile_strength",
            "yield_strength",
            "elongation",
            "shear_strength",
            "wetting_score",
        )
        out = {k: "MODEL" for k in keys}
        db_pred = {}
        db_w = 0.0
        if isinstance(db_out, dict):
            db_pred = db_out.get("pred") if isinstance(db_out.get("pred"), dict) else {}
            db_top = db_out.get("top") if isinstance(db_out.get("top"), list) else []
            db_best_dist = None
            try:
                if isinstance(db_top, list) and db_top:
                    db_best_dist = float((db_top[0] or {}).get("dist"))
            except Exception:
                db_best_dist = None
            use_db = (db_best_dist is not None) and (db_best_dist <= 3.0)
            if use_db:
                try:
                    d0 = float(db_best_dist) if db_best_dist is not None else 9999.0
                    db_w = 1.0 / (1.0 + d0 / 2.0)
                except Exception:
                    db_w = 0.0
                db_w = _property_db_weight(db_best_dist)
        else:
            db_pred = predict_from_db(norm)
            if not db_pred:
                return out
            try:
                sc = float(score or 0.0)
            except Exception:
                sc = 0.0
            db_w = max(0.15, min(0.75, 1.0 / (1.0 + sc / 5.0)))

        if not isinstance(db_pred, dict) or not db_pred or db_w <= 0.0:
            return out
        mapping = {
            "tensile_strength": "tensile",
            "yield_strength": "yield_strength",
            "elongation": "elongation",
            "shear_strength": "shear",
        }
        pb = props_before_blend if isinstance(props_before_blend, dict) else {}
        for mk, dk in mapping.items():
            if db_pred.get(dk) is None or pb.get(mk) is None:
                continue
            out[mk] = f"DB(blend_GUI,w={db_w:.2f})"
        return out

    def overall_confidence(self, conf, score, melting_detail, props, norm=None):
        """analyze_all과 동일 가중식 — GUI 단일 분석 경로에서도 종합 신뢰도 표시용."""
        md = melting_detail if isinstance(melting_detail, dict) else {}
        melting_dist = md.get("best_dist", score)
        melting_conf = self._dist_conf(melting_dist)
        wet_neighbors = []
        if isinstance(props, dict):
            confidence_neighbors = props.get("wetting_confidence_neighbors")
            if isinstance(confidence_neighbors, list) and confidence_neighbors:
                wet_neighbors = confidence_neighbors
            elif isinstance(props.get("wetting_neighbors"), list):
                wet_neighbors = props.get("wetting_neighbors")
        wet_conf = self._wetting_conf_from_neighbors(wet_neighbors) if wet_neighbors else 0.0
        overall = 0.55 * float(conf or 0.0) + 0.30 * float(melting_conf or 0.0) + 0.15 * float(wet_conf or 0.0)
        # Penalize confidence when composition includes non-core (DB-poor) unknown metals.
        # Ratio-based, capped so confidence remains informative but conservative.
        _, unknown_total = self._unknown_element_profile(norm)
        penalty = min(35.0, max(0.0, float(unknown_total)) * 0.7) if unknown_total > 0 else 0.0
        overall -= penalty
        return max(0.0, min(100.0, float(overall)))

    # ============================================================
    # Best Match
    # ============================================================
    def find_best_match(self, norm):
        if not norm:
            return None, 9999, 0.0

        n_tuple = tuple(sorted(norm.items()))
        best, score = None, 9999

        for item in self.db_prepared:
            d = cached_distance(n_tuple, item["comp_tuple"])
            if d < score:
                best = item
                score = d

        confidence = self.calc_confidence(score)
        try:
            support_factor, _ = self._db_sample_support_factor(best["name"] if best else None)
            confidence *= float(support_factor)
        except Exception:
            pass
        return best, score, confidence

    # ============================================================
    # KNN
    # ============================================================
    def find_knn(self, norm, k=3):
        if not norm:
            return []
        n_tuple = tuple(sorted(norm.items()))
        dlist = [
            (cached_distance(n_tuple, item["comp_tuple"]), item)
            for item in self.db_prepared
        ]
        dlist.sort(key=lambda x: x[0])
        return dlist[:k]

    # ============================================================
    # Phase 분석
    # ============================================================
    def phase_analysis(self, norm):
        results = []
        rule_phase = []

        if norm.get("Ag", 0) > 0:
            rule_phase.append("가능 IMC: Ag3Sn")
        if norm.get("Cu", 0) > 0:
            rule_phase.append("가능 IMC: Cu6Sn5 / Cu3Sn")
        if norm.get("Bi", 0) > 0:
            rule_phase.append("저융점 Sn–Bi 공융계의 영향 가능성")
            bi = float(norm.get("Bi", 0) or 0.0)
            if bi >= 40:
                rule_phase.append("고 Bi 구간: β-Sn + Bi 농화 공정(층상/망상) 조직이 지배적일 수 있음")
            elif bi >= 5:
                rule_phase.append("중 Bi 구간: 입계 Bi 농화 분산상 증가로 취성 기여 가능성")
            else:
                rule_phase.append("저 Bi 구간: 미세 Bi 분산상 영향(강도↑/연성↓ 가능)")

        results.append({"rule_phase": rule_phase})

        try:
            ai_phase = self.ai.get_phase_data(norm)
            results.append({"ai_phase": ai_phase})
        except Exception as e:
            results.append({"ai_phase": f"AI phase lookup skipped: {e}"})

        return results

    def _predict_imc_rules(self, norm):
        """AI 호출 없이 조성 기반 IMC/상 후보를 생성."""
        out = []
        ag = float(norm.get("Ag", 0.0) or 0.0)
        cu = float(norm.get("Cu", 0.0) or 0.0)
        ni = float(norm.get("Ni", 0.0) or 0.0)
        sb = float(norm.get("Sb", 0.0) or 0.0)
        bi = float(norm.get("Bi", 0.0) or 0.0)
        inn = float(norm.get("In", 0.0) or 0.0)
        zn = float(norm.get("Zn", 0.0) or 0.0)
        pb = float(norm.get("Pb", 0.0) or 0.0)

        if ag > 0:
            out.append("Ag3Sn")
        if cu > 0:
            out.append("Cu6Sn5")
            if cu > 0.5:
                out.append("Cu3Sn")
        if ni > 0:
            out.append("(Ni,Cu)6Sn5")
            if ni >= 0.05:
                out.append("Ni3Sn4")
        if sb > 0:
            out.append("SnSb")
        if inn >= 1.0:
            out.append("In 농화상 / In-Sn 금속간화합물 (예: InSn4)")
        if bi > 0:
            out.append("Bi 농화 분산상 (비금속간화합물, 공정/분산상)")
        if zn >= 1.0:
            out.append("Zn 농화 분산상 (Zn-Sn계 분산상 가능)")
        if pb > 0:
            out.append("Pb 농화 분산상 (Sn-Pb 공정/분산상)")
        return out

    def _filter_phase_text_by_input(self, text: str, norm: dict) -> str:
        """
        입력 조성에 없는 원소/계열 언급을 phase 본문에서 제거.
        (예: Ag=0이면 Ag3Sn/Sn-Ag 문장 제거)
        """
        src = str(text or "").strip()
        if not src:
            return src
        ag = float(norm.get("Ag", 0.0) or 0.0)
        cu = float(norm.get("Cu", 0.0) or 0.0)
        ni = float(norm.get("Ni", 0.0) or 0.0)
        bi = float(norm.get("Bi", 0.0) or 0.0)
        inn = float(norm.get("In", 0.0) or 0.0)
        sb = float(norm.get("Sb", 0.0) or 0.0)
        zn = float(norm.get("Zn", 0.0) or 0.0)
        pb = float(norm.get("Pb", 0.0) or 0.0)

        lines = [ln.strip() for ln in src.splitlines() if str(ln).strip()]
        kept = []
        for ln in lines:
            l = ln.lower()
            if _mentions_unentered_element(ln, norm):
                continue
            if ("ag3sn" in l or "sn-ag" in l or " ag" in l) and ag <= 0:
                continue
            if ("cu6sn5" in l or "cu3sn" in l or "sn-cu" in l or "(ni,cu)6sn5" in l) and cu <= 0:
                continue
            if ("ni3sn4" in l or "(ni,cu)6sn5" in l or "sn-ni" in l) and ni <= 0:
                continue
            if ("bi-rich" in l or "sn-bi" in l) and bi <= 0:
                continue
            if ("in-rich" in l or "insn" in l or "sn-in" in l) and inn <= 0:
                continue
            if ("snsb" in l or "sn-sb" in l) and sb <= 0:
                continue
            if ("zn-rich" in l or "sn-zn" in l) and zn <= 0:
                continue
            if ("pb-rich" in l or "sn-pb" in l) and pb <= 0:
                continue
            kept.append(ln)
        return "\n".join(kept) if kept else "특징적인 상변태 경향을 특정하기 어려움."

    # ============================================================
    # IMC 예측
    # ============================================================
    def predict_imc(self, norm):
        imc_list = list(self._predict_imc_rules(norm))

        try:
            ai_imc = self.ai.get_imc_data(norm)
            if isinstance(ai_imc, list):
                imc_list.extend(ai_imc)
            else:
                imc_list.append(str(ai_imc))
        except Exception as e:
            imc_list.append(f"AI IMC lookup skipped: {e}")

        return imc_list

    # ============================================================
    # 용융점 계산 — 하이브리드 6레이어 예측 엔진
    # ============================================================
    def calc_melting(self, best, norm):
        """
        hybrid_melting_predict 엔진 위임.
        L1(DB직접) → L2(상태도) → L3(KNN) → L4(CALPHAD) → L6(AI)
        순서로 신뢰도 가중 앙상블.

        Returns: solidus, liquidus, peak, stage(str)
        """
        if not norm:
            return 217.0, 221.0, 246.0, "unknown"

        solidus, liquidus, peak, stage, _detail = self.calc_melting_with_detail(best, norm)
        return solidus, liquidus, peak, stage

    def calc_melting_with_detail(self, best, norm, include_ai: bool = True):
        """
        calc_melting + detail 반환 버전.

        Returns: solidus, liquidus, peak, stage(int), detail(dict)
        """
        if not norm:
            return (
                217.0,
                221.0,
                246.0,
                5,
                {
                    "best_dist": 9999,
                    "forced_db": False,
                    "engine_version": MELTING_ENGINE_VERSION,
                },
            )

        solidus, liquidus, peak, detail = hybrid_melting_predict(
            norm,
            self.db_prepared,
            ai_engine=self.melting_ai if include_ai else None,
        )

        # stage는 best_dist 기준으로 기존 stage 숫자 유지
        dist = detail.get("best_dist", 9999)
        if dist < 0.3:
            stage = 0
        elif dist < 1.0:
            stage = 1
        elif dist < 3.0:
            stage = 2
        elif dist < 6.0:
            stage = 3
        elif dist < 12.0:
            stage = 4
        else:
            stage = 5
        return solidus, liquidus, peak, stage, detail

    # ============================================================
    # Risk 분석
    # ============================================================
    def predict_risk(self, norm):
        risk = []
        if norm.get("Bi", 0) >= 5:
            risk.append("Bi >= 5% → 낙하(drop) 충격에 따른 취성 증가 경향")
        if norm.get("Sb", 0) >= 8:
            risk.append("Sb >= 8% → 고온에서 취성 경향 증가")
        if norm.get("Cu", 0) >= 0.7:
            risk.append("Cu >= 0.7% → Cu6Sn5 성장 가속 → 전기이동(EM) 손상 위험")
        if norm.get("Bi", 0) >= 40:
            risk.append("Bi >= 40% → 저온 공정 적합, 고온 환경 사용 주의")
        if norm.get("Pb", 0) > 0:
            risk.append("Pb 함유 → RoHS 규제 대상. 용도 확인 필요")
        if not risk:
            risk.append("규칙 기준으로는 뚜렷한 취성·신뢰성 위험이 식별되지 않음")
        return risk

    # ============================================================
    # 물성 예측
    # ============================================================
    def model_properties(
        self,
        comp,
        solidus,
        liquidus,
        peak=None,
        wetting_temp_c=None,
        wetting_temp_basis=None,
        include_wetting_grid=False,
    ):
        return self.models.predict_all(
            comp,
            solidus,
            liquidus,
            peak=peak,
            wetting_temp_c=wetting_temp_c,
            wetting_temp_basis=wetting_temp_basis,
            include_wetting_grid=include_wetting_grid,
        )

    def liquidus_for_comp(self, comp) -> float:
        """비교용 공통 젖음 온도 산출 전 액상선만 빠르게 계산."""
        self.validate_input_comp(comp)
        norm = self.normalize(comp)
        best, _, _ = self.find_best_match(norm)
        # 공통 젖음 온도 선택은 결정론적 핵심 수치만 필요하다.
        # 원격 AI를 호출하면 비교 요청마다 불필요한 지연과 비결정성이 생긴다.
        _, liquidus, _, _, _ = self.calc_melting_with_detail(best, norm, include_ai=False)
        if type(liquidus) is bool or liquidus is None:
            raise ValueError("액상선 예측값이 없어 공통 젖음 온도를 계산할 수 없습니다.")
        liquidus_value = float(liquidus)
        if not math.isfinite(liquidus_value):
            raise ValueError("액상선 예측값이 유한하지 않습니다.")
        return liquidus_value

    def compare_wetting_temp_c(self, comp_a, comp_b, user_wetting_temp_c=None):
        """
        비교 모드 젖음 온도: 사용자 지정이 없으면 A·B 자동 스냅값 중 max(공통 온도).
        Returns (snapped_temp_c, basis).
        """
        from .models import compare_default_wetting_temp_c, snap_wetting_temp_to_bd_grid

        if user_wetting_temp_c is not None:
            return snap_wetting_temp_to_bd_grid(float(user_wetting_temp_c)), "user"
        la = self.liquidus_for_comp(comp_a)
        lb = self.liquidus_for_comp(comp_b)
        return compare_default_wetting_temp_c(la, lb), "compare_shared"

    def wetting_grid_for_comp(self, comp):
        """250–290℃ 온도별 Fmax/T0 (IDW). 별도 API·지연 로드용."""
        if comp:
            self.validate_input_comp(comp)
        norm = self.normalize(comp) if comp else {}
        return self.models._predict_wetting_by_temperature(norm)

    # ============================================================
    # 전체 분석
    # ============================================================
    def analyze_all(
        self,
        comp,
        mode="eng",
        progress_cb=None,
        literature_mode: str = "fast",
        wetting_temp_c=None,
        wetting_temp_basis=None,
        include_wetting_grid=False,
        include_ai: bool = True,
        include_melting_ai: bool | None = None,
    ):
        def _p(v, msg):
            if callable(progress_cb):
                try:
                    progress_cb(v, msg)
                except Exception:
                    pass

        self._sync_db_prepared()
        _p(8, "입력 조성 검증·정규화 중...")
        self.validate_input_comp(comp)
        norm = self.normalize(comp)
        _p(16, "DB 최근접 합금 탐색 중...")
        best, score, conf = self.find_best_match(norm)
        _p(28, "융점/온도 프로파일 계산 중...")
        melting_ai_enabled = include_ai if include_melting_ai is None else include_melting_ai
        solidus, liquidus, peak, stage, melting_detail = self.calc_melting_with_detail(
            best, norm, include_ai=bool(melting_ai_enabled)
        )

        _p(66, "KNN 유사 합금 검색 중...")
        knn  = self.find_knn(norm, k=3)
        alloy_inference = {}
        try:
            from .alloy_property_inference import predictAlloyProperties

            alloy_inference = predictAlloyProperties(norm, self.db_prepared, k=3)
        except Exception:
            alloy_inference = {
                "solidus": None,
                "liquidus": None,
                "recommended_peak_c": None,
                "neighbors": [],
                "neighbor_weights": [],
                "element_weights_liquidus": {},
                "element_weights_solidus": {},
                "process_report": "데이터 추론 단계에서 오류가 발생했습니다.",
                "inference_note": "오류",
                "idw_baseline_solidus": None,
                "idw_baseline_liquidus": None,
            }
        _p(38, "리스크 예측 중...")
        risk = self.predict_risk(norm)
        _p(50, "물성 예측 모델 계산 중...")
        props = self.model_properties(
            norm,
            solidus,
            liquidus,
            peak=peak,
            wetting_temp_c=wetting_temp_c,
            wetting_temp_basis=wetting_temp_basis,
            include_wetting_grid=include_wetting_grid,
        )
        # Preserve the untouched composition-model estimate before any DB blend.
        # This is the fallback for genuinely unregistered/out-of-domain alloys.
        try:
            raw_model_tensile = props.get("tensile_strength")
            if raw_model_tensile is not None:
                props["tensile_strength_model_mpa"] = float(raw_model_tensile)
        except Exception:
            pass
        props["density"] = None
        try:
            best_density = (best or {}).get("density")
            if (
                best_density is not None
                and score is not None
                and float(score) <= _DB_EXACT_EPS
            ):
                props["density"] = float(best_density)
        except Exception:
            pass

        # DB 기반 물성 보정 (properties DB)
        # - 기존: DB 예측값을 항상 덮어쓰기 → Bi계(또는 Cu-free)에서 과매칭 가능
        # - 개선: properties DB 거리 기반 게이팅 + 블렌딩
        _p(58, "DB 가중 보정 중...")
        prop_sources = {}
        try:
            from .db_regression import predict_from_db_with_detail
            db_out = predict_from_db_with_detail(norm)
        except Exception:
            db_out = None

        db_pred = (db_out.get("pred") if isinstance(db_out, dict) else None) or {}
        db_top = (db_out.get("top") if isinstance(db_out, dict) else None) or []

        db_best_dist = None
        try:
            if isinstance(db_top, list) and db_top:
                db_best_dist = float((db_top[0] or {}).get("dist"))
        except Exception:
            db_best_dist = None

        # Only trust properties DB when it's truly close.
        # (Loose thresholds tend to over-fit/over-match across alloy families, especially Bi / Cu-free cases.)
        try:
            db_w = _property_db_weight(db_best_dist)
        except Exception:
            db_w = 0.0
        mdl_w = 1.0 - db_w
        db_exact_hit = (db_best_dist is not None) and (float(db_best_dist) <= _DB_EXACT_EPS)

        if db_pred and db_w > 0.0:
            def _blend(key_out, key_db):
                dv = db_pred.get(key_db, None)
                mv = props.get(key_out, None)
                if dv is None or mv is None:
                    return
                try:
                    props[key_out] = float(dv) if db_exact_hit else (float(mv) * mdl_w + float(dv) * db_w)
                    prop_sources[key_out] = f"DB(blend,w={db_w:.2f})"
                except Exception:
                    return

            _blend("tensile_strength", "tensile")
            _blend("yield_strength", "yield_strength")
            _blend("elongation", "elongation")
            _blend("shear_strength", "shear")
        # 물성 DB(IDW) 단독 인장 추정 — UI에 실값으로 표시(블렌드 결과와 구분)
        if isinstance(db_pred, dict) and db_pred.get("tensile") is not None:
            try:
                props["tensile_strength_db_mpa"] = float(db_pred["tensile"])
            except Exception:
                pass

        # 전단: 합금족 정렬 IDW (근접 블렌드와 별도 — Bi계 등 원거리 조성용)
        shear_idw_detail = None
        try:
            from .db_regression import predict_shear_from_db_with_detail

            shear_idw_detail = predict_shear_from_db_with_detail(norm)
            if isinstance(shear_idw_detail, dict) and shear_idw_detail.get("value") is not None:
                props["shear_strength_db_mpa"] = float(shear_idw_detail["value"])
                top_sh = shear_idw_detail.get("top")
                if isinstance(top_sh, list) and top_sh:
                    props["shear_neighbors"] = top_sh
        except Exception:
            shear_idw_detail = None

        # 문헌·업계 참고 인장 (비교 모드·근거 표시용)
        strength_lit = None
        try:
            from .strength_literature_refs import nearest_strength_literature

            strength_lit = nearest_strength_literature(norm)
            if isinstance(strength_lit, dict) and strength_lit.get("tensile_mpa") is not None:
                props["tensile_strength_lit_mpa"] = float(strength_lit["tensile_mpa"])
                if strength_lit.get("tensile_range"):
                    props["tensile_strength_lit_range_mpa"] = list(strength_lit["tensile_range"])
        except Exception:
            strength_lit = None

        # Fill defaults
        for k in ("tensile_strength", "yield_strength", "elongation", "shear_strength", "wetting_score"):
            prop_sources.setdefault(k, "MODEL")

        # 전단: 근접 블렌드 없으면 MODEL 대신 합금족 IDW(BD 유사)로 표시
        if prop_sources.get("shear_strength") == "MODEL":
            shear_idw = None
            if isinstance(shear_idw_detail, dict):
                shear_idw = shear_idw_detail.get("value")
            shear_db_dist = None
            if isinstance(shear_idw_detail, dict):
                try:
                    shear_db_dist = float(shear_idw_detail.get("best_dist"))
                except (TypeError, ValueError):
                    shear_db_dist = None
            # A composition that exactly matches a property-DB row with no
            # shear observation must not inherit a different alloy's IDW
            # value.  Use IDW only when the nearest *valid shear* evidence is
            # itself within the property blend radius.
            exact_shear_missing = bool(
                db_exact_hit and (db_pred.get("shear") is None)
            )
            allow_shear_idw = bool(
                shear_idw is not None
                and shear_db_dist is not None
                and shear_db_dist <= 3.0
                and not exact_shear_missing
            )
            if allow_shear_idw:
                try:
                    props["shear_strength"] = float(shear_idw)
                    d_s = shear_idw_detail.get("best_dist")
                    if d_s is None:
                        d_s = db_best_dist
                    prop_sources["shear_strength"] = (
                        f"DB(IDW,d={float(d_s):.1f})" if d_s is not None else "DB(IDW)"
                    )
                    props["shear_strength_basis"] = "db_idw"
                except Exception:
                    pass
        elif prop_sources.get("shear_strength", "").startswith("DB(blend"):
            props["shear_strength_basis"] = "db_blend"
        if str(prop_sources.get("yield_strength", "")).startswith("DB(blend"):
            props["yield_strength_basis"] = "db_blend"

        # 인장: exact는 DB 평균, 가까운 미등록 조성은 MODEL+DB 블렌드,
        # 먼 미등록 조성은 조성 모델을 유지한다. 문헌값은 별도 참고치만 제공한다.
        tv = props.get("tensile_strength_db_mpa")
        if tv is not None and db_exact_hit:
            try:
                props["tensile_strength"] = float(tv)
                props["tensile_strength_basis"] = "db_priority"
                d_t = db_best_dist
                prop_sources["tensile_strength"] = (
                    f"DB(priority,d={float(d_t):.1f})" if d_t is not None else "DB(priority)"
                )
            except Exception:
                pass
        elif db_w > 0.0 and str(prop_sources.get("tensile_strength", "")).startswith("DB(blend"):
            props["tensile_strength_basis"] = "db_blend"
        else:
            props["tensile_strength_basis"] = "model_prediction"

        # 최종 물리 제약: 항복강도는 인장강도를 넘지 않도록 정렬.
        try:
            tensile_val = props.get("tensile_strength")
            yield_val = props.get("yield_strength")
            if tensile_val is not None and yield_val is not None:
                tensile_f = float(tensile_val)
                yield_f = float(yield_val)
                if yield_f > tensile_f:
                    props["yield_strength"] = max(0.0, tensile_f * 0.98)
                    props["yield_strength_basis"] = "clamped_to_tensile"
                    if prop_sources.get("yield_strength", "MODEL") == "MODEL":
                        prop_sources["yield_strength"] = "CLAMP(tensile)"
        except Exception:
            pass

        mechanical_metadata = _mechanical_property_metadata(
            props, prop_sources, db_best_dist
        )
        props["mechanical_property_metadata"] = mechanical_metadata
        if "shear_strength" in mechanical_metadata:
            props["shear_metadata"] = dict(mechanical_metadata["shear_strength"])

        # Evidence/provenance for transparency in UI
        md = melting_detail if isinstance(melting_detail, dict) else {}
        melting_dist = md.get("best_dist", score)
        melting_conf = self._dist_conf(melting_dist)

        wet_neighbors = []
        if isinstance(props, dict):
            confidence_neighbors = props.get("wetting_confidence_neighbors")
            if isinstance(confidence_neighbors, list) and confidence_neighbors:
                wet_neighbors = confidence_neighbors
            elif isinstance(props.get("wetting_neighbors"), list):
                wet_neighbors = props.get("wetting_neighbors")
        wet_conf = self._wetting_conf_from_neighbors(wet_neighbors) if wet_neighbors else 0.0

        _, unknown_total = self._unknown_element_profile(norm)
        unknown_penalty = min(35.0, max(0.0, float(unknown_total)) * 0.7) if unknown_total > 0 else 0.0

        # Overall confidence is a weighted blend (bounded, explainable)
        # - DB best-match confidence: how close to known alloy comps
        # - melting_conf: how close the melting engine thinks it is to DB anchors
        # - wet_conf: how well wetting is supported by nearby DB records
        overall = 0.55 * float(conf or 0.0) + 0.30 * float(melting_conf or 0.0) + 0.15 * float(wet_conf or 0.0)
        overall -= float(unknown_penalty)
        overall = max(0.0, min(100.0, float(overall)))
        evidence = self.build_evidence(norm, melting_detail, score, conf, props, prop_sources, db_out)
        try:
            from .standards_refs import IPC_JIS_SUMMARY_FOR_EVIDENCE

            evidence = dict(evidence)
            evidence["standards_refs"] = list(IPC_JIS_SUMMARY_FOR_EVIDENCE)
            if isinstance(strength_lit, dict) and strength_lit.get("refs"):
                evidence["strength_literature"] = {
                    "tensile_mpa": strength_lit.get("tensile_mpa"),
                    "tensile_range": strength_lit.get("tensile_range"),
                    "best_dist": strength_lit.get("best_dist"),
                    "refs": strength_lit.get("refs", [])[:5],
                }
        except Exception:
            pass

        _p(78, "AI 상분석/요약 생성 중...")
        comp_str = ", ".join([f"{k}:{v:.2f}%" for k, v in comp.items()])

        # ─── 효율화 3단 게이트 ─────────────────────────────────────────────
        # (B) DB 정확 일치: AI 호출 전부 스킵, 로컬 폴백으로 충분한 리포트 생성.
        # (A) 디스크 캐시: 같은 조성+mode+literature_mode를 과거에 분석했으면 재사용.
        # (C) miss 시에만 Gemini/Cerebras 호출 → 응답을 캐시에 저장.
        ai_result_payload = {
            "norm": norm,
            "best": best,
            "score": score,
            "confidence": conf,
            "confidence_overall": overall,
            "solidus": solidus,
            "liquidus": liquidus,
            "peak": peak,
            "risk": risk,
            "melting_stage": stage,
            "melting_detail": melting_detail,
            "props": props,
        }

        ai_source = "api"            # api / cache / db_exact
        # detail에 engine_version이 없으면(레거시·예외 경로) 상수로 채워 캐시가 엔진 버전과 어긋나지 않게 함
        if isinstance(melting_detail, dict):
            _mv = str(melting_detail.get("engine_version") or MELTING_ENGINE_VERSION).strip()
        else:
            _mv = str(MELTING_ENGINE_VERSION).strip()
        cache_key = ai_cache.make_key(
            norm,
            mode=mode,
            literature_mode=literature_mode,
            extra=(
                f"mv={_mv}|dbfp={getattr(self, '_solder_db_fingerprint', '') or ''}"
                f"|report_policy={_AI_REPORT_POLICY_VERSION}"
            ),
        )
        db_exact_hit = (score is not None and float(score) <= _DB_EXACT_EPS)

        def _call_api_and_cache():
            """실제 Gemini/Cerebras 호출 + 성공 시 캐시 저장. 결과(full_ai) 반환."""
            out = self.ai.get_full_analysis(
                norm, comp_str, ai_result_payload, knn,
                mode=mode, literature_mode=literature_mode,
            )
            # AI가 실제 원격 호출되어 유의미한 결과를 줬을 때만 캐시.
            # (로컬 폴백/오류 메시지는 캐시하지 않음 → 다음 기회에 재시도 가능)
            if isinstance(out, dict) and bool(out.get("ai_used_this_request")):
                ai_cache.put(cache_key, out)
            return out

        # 1) 비정확 조성: 캐시 우선, miss면 API 호출
        # 2) 정확 조성 (db_exact_hit):
        #    - cache_first(기본): 캐시 있으면 재사용, 없으면 AI 호출해서 만들고 저장
        #                        → 첫 호출 이후 영구적으로 API 0회 + 품질 완전 동일
        #    - skip: 로컬 폴백으로만 생성 (API 완전 0회, 서술 간결)
        #    - always: 정확 일치 무시하고 항상 API 호출 (기존 동작)
        cached = ai_cache.get(cache_key) if include_ai else None

        if not include_ai:
            # 수치 예측 API는 외부 생성형 AI 상태와 분리한다. 로컬 규칙 설명만
            # 구성해 핵심 결과가 API 키·네트워크·AI 지연에 영향받지 않게 한다.
            try:
                full_ai = self.ai._build_local_fallback(
                    norm, ai_result_payload, knn,
                    literature_mode=literature_mode, mode=mode,
                )
            except Exception:
                full_ai = {}
            ai_source = "local"
        elif isinstance(cached, dict):
            full_ai = cached
            ai_source = "cache"
        elif db_exact_hit and _AI_DB_EXACT_MODE == "skip":
            # 로컬 폴백 강제 모드: API 0회, 서술은 규칙 기반.
            try:
                full_ai = self.ai._build_local_fallback(
                    norm, ai_result_payload, knn,
                    literature_mode=literature_mode, mode=mode,
                )
                ai_source = "db_exact"
            except Exception:
                full_ai = None
            if not isinstance(full_ai, dict):
                # 폴백 실패 시 안전 복귀 — API 호출
                full_ai = _call_api_and_cache()
                ai_source = "api"
        else:
            # cache_first(기본), always, 또는 비정확 조성 — 모두 정상 AI 호출 경로.
            # 단, AI 호출 성공 시 캐시 저장하므로 같은 조성은 두 번째부터 무료.
            full_ai = _call_api_and_cache()
            ai_source = "api"
        ai_summary_txt = str(full_ai.get("summary", "") or "") if isinstance(full_ai, dict) else ""
        ai_cited_sources = full_ai.get("ai_cited_sources", []) if isinstance(full_ai, dict) else []
        retrieved_candidates = full_ai.get("retrieved_candidates", []) if isinstance(full_ai, dict) else []
        legacy_sources = full_ai.get("sources", []) if isinstance(full_ai, dict) else []
        if not isinstance(ai_cited_sources, list):
            ai_cited_sources = []
        if not isinstance(retrieved_candidates, list):
            retrieved_candidates = []
        if not isinstance(legacy_sources, list):
            legacy_sources = []
        ai_cited_sources = [str(x).strip() for x in ai_cited_sources if str(x).strip()]
        retrieved_candidates = [str(x).strip() for x in retrieved_candidates if str(x).strip()]
        legacy_sources = [str(x).strip() for x in legacy_sources if str(x).strip()]
        if not retrieved_candidates and legacy_sources:
            retrieved_candidates = list(legacy_sources)
        mode_key = (mode or "eng").strip().lower()
        _local_summary_markers = (
            "[로컬 하이브리드 요약]",
            "[쉬운 요약 · 로컬 전용]",
            "[쉬운 요약 · Gemini 미연결]",  # 구버전 요약 헤더 호환
        )
        ai_used_this_request = False
        # 이번 요청에서 실제로 외부 API(Gemini/Cerebras)를 태운 경우만 True.
        # - ai_source == "cache": 과거에 API로 받아 저장해둔 결과 재사용 → 이번 요청엔 호출 없음.
        # - ai_source == "db_exact": DB 정확 일치라서 AI 호출 자체를 스킵 → False.
        if ai_source in ("cache", "db_exact"):
            ai_used_this_request = False
        elif isinstance(full_ai, dict) and ("ai_used_this_request" in full_ai):
            ai_used_this_request = bool(full_ai.get("ai_used_this_request"))
        else:
            ai_used_this_request = bool(getattr(self.ai, "available", False)) and (
                not any(ai_summary_txt.startswith(m) for m in _local_summary_markers)
            )
        # 어떤 조성이 들어와도 조성 기반 규칙 설명이 최소 포함되도록 보강 (엔지니어=비전문가 모드: 기술 보강 생략)
        rule_phase_txt = self.phase_predictor.predict(norm, solidus=solidus, liquidus=liquidus)
        ai_phase_txt = str(full_ai.get("phase", "") or "").strip() if isinstance(full_ai, dict) else ""
        if ai_phase_txt:
            phase_txt = ai_phase_txt
            if (
                mode_key != "eng"
                and rule_phase_txt
                and rule_phase_txt not in ai_phase_txt
            ):
                phase_txt += "\n\n[규칙 기반 보강]\n" + str(rule_phase_txt)
        else:
            if mode_key == "eng":
                try:
                    fn_pc = getattr(self.ai, "_rule_phase_consumer", None)
                    phase_txt = (
                        str(fn_pc(norm))
                        if callable(fn_pc)
                        else str(rule_phase_txt or "특징적인 상변태 경향을 특정하기 어려움.")
                    )
                except Exception:
                    phase_txt = str(rule_phase_txt or "특징적인 상변태 경향을 특정하기 어려움.")
            else:
                phase_txt = str(rule_phase_txt or "특징적인 상변태 경향을 특정하기 어려움.")
        phase_txt = self._filter_phase_text_by_input(phase_txt, norm)

        rule_imc = self._predict_imc_rules(norm)
        ai_imc = full_ai.get("imc", []) if isinstance(full_ai, dict) else []
        merged_imc = []
        seen_imc = set()
        ag = float(norm.get("Ag", 0.0) or 0.0)
        cu = float(norm.get("Cu", 0.0) or 0.0)
        ni = float(norm.get("Ni", 0.0) or 0.0)
        bi = float(norm.get("Bi", 0.0) or 0.0)
        inn = float(norm.get("In", 0.0) or 0.0)
        sb = float(norm.get("Sb", 0.0) or 0.0)
        zn = float(norm.get("Zn", 0.0) or 0.0)
        pb = float(norm.get("Pb", 0.0) or 0.0)

        def _compatible_with_input(text: str) -> bool:
            t = text.lower()
            # 입력에 없는 원소 기반 상/IMC는 제외 (AI 환각 방어)
            if _mentions_unentered_element(text, norm):
                return False
            if ("ag3sn" in t or " ag" in t or "ag-" in t or "sn-ag" in t) and ag <= 0:
                return False
            if ("cu6sn5" in t or "cu3sn" in t or "(ni,cu)6sn5" in t or "cu-sn" in t) and cu <= 0:
                return False
            if ("ni3sn4" in t or "(ni,cu)6sn5" in t) and ni <= 0:
                return False
            if ("bi-rich" in t or "sn-bi" in t) and bi <= 0:
                return False
            if ("in-rich" in t or "insn" in t or "sn-in" in t) and inn <= 0:
                return False
            if "snsb" in t and sb <= 0:
                return False
            if ("zn-rich" in t or "sn-zn" in t) and zn <= 0:
                return False
            if ("pb-rich" in t or "sn-pb" in t) and pb <= 0:
                return False
            return True

        for x in (ai_imc if isinstance(ai_imc, list) else [ai_imc]) + rule_imc:
            s = str(x).strip()
            if not s:
                continue
            if not _compatible_with_input(s):
                continue
            # 표기 표준화(중복/유사문구 정리)
            lk = s.lower()
            if "bi-rich phase" in lk or "bi 농화" in lk:
                s = "Bi 농화 분산상 (비금속간화합물, 공정/분산상)"
            elif "in-rich phase" in lk or "insn" in lk or "in 농화" in lk:
                s = "In 농화상 / In-Sn 금속간화합물 (예: InSn4)"
            elif "zn-rich phase" in lk or "zn 농화" in lk:
                s = "Zn 농화 분산상 (Zn-Sn계 분산상 가능)"
            elif "pb-rich phase" in lk or "pb 농화" in lk:
                s = "Pb 농화 분산상 (Sn-Pb 공정/분산상)"
            key = s.lower()
            if key in seen_imc:
                continue
            seen_imc.add(key)
            merged_imc.append(s)
        if len(merged_imc) > 1:
            merged_imc = [
                x for x in merged_imc
                if "규칙 기반으로는 지배적 IMC를 특정하기 어려움" not in str(x)
            ]
        if not merged_imc:
            merged_imc = ["규칙 기반으로는 지배적 IMC를 특정하기 어려움"]

        if mode_key == "eng":
            # [2026-09-21 웹 점검 패치] 쉬운 설명 변환 후 중복 제거
            #   변경 전: 원문이 다른 두 줄(예: "Ag3Sn", "Ag3Sn IMC ...")이 같은 쉬운 문장으로 바뀌어
            #            SAC105 결과에 Ag3Sn·Cu6Sn5가 두 번씩 표시됨.
            #   결과: 변환 후 문장 기준으로 한 번만 표시.
            #   검증: tests/test_web_audit_2026_09_21_regression.py
            #   또한 "특정하기 어렵습니다" 문장은 다른 항목이 있으면 빼서 모순 표시를 막음
            #   (예: Sn63Pb37·In52Sn48에서 '특정 어려움'과 실제 층이 함께 나오던 문제).
            plain = []
            for x in merged_imc[:6]:
                line = _imc_line_to_plain_korean(x)
                if line not in plain:
                    plain.append(line)
            unknown_line = _imc_line_to_plain_korean("규칙 기반으로는 지배적 IMC를 특정하기 어려움")
            if len(plain) > 1:
                plain = [x for x in plain if x != unknown_line]
            merged_imc = plain

        ai_dopant_txt = str(full_ai.get("dopant", "") or "").strip() if isinstance(full_ai, dict) else ""
        rule_dopant_txt = ""
        try:
            fn = getattr(self.ai, "_rule_dopant", None)
            if callable(fn):
                rule_dopant_txt = str(fn(norm) or "").strip()
        except Exception:
            rule_dopant_txt = ""
        if mode_key == "eng":
            if ai_dopant_txt:
                dopant_txt = ai_dopant_txt
            else:
                try:
                    fn_c = getattr(self.ai, "_rule_dopant_consumer", None)
                    dopant_txt = str(fn_c(norm) or "").strip() if callable(fn_c) else rule_dopant_txt
                except Exception:
                    dopant_txt = rule_dopant_txt or "이 조성만으로도 목적에 맞을 수 있습니다. 변경은 전문가와 상의하세요."
            if not dopant_txt:
                dopant_txt = "이 조성만으로도 목적에 맞을 수 있습니다. 변경은 전문가와 상의하세요."
        elif ai_dopant_txt and rule_dopant_txt:
            dopant_txt = (
                ai_dopant_txt
                if rule_dopant_txt in ai_dopant_txt
                else (ai_dopant_txt + "\n\n[규칙 기반 추가 제안]\n" + rule_dopant_txt)
            )
        elif ai_dopant_txt:
            dopant_txt = ai_dopant_txt
        elif rule_dopant_txt:
            dopant_txt = rule_dopant_txt
        else:
            dopant_txt = "- 현재 조성 기준으로 공정 조건 최적화가 우선입니다."

        ai_sources = list(ai_cited_sources if ai_cited_sources else retrieved_candidates)
        cache_age = None
        if ai_source == "cache" and isinstance(full_ai, dict):
            try:
                cache_age = int(full_ai.get("_cache_age_sec")) if full_ai.get("_cache_age_sec") is not None else None
            except (TypeError, ValueError):
                cache_age = None
        if isinstance(evidence, dict):
            ai_ev = evidence.get("ai") if isinstance(evidence.get("ai"), dict) else {}
            ai_ev = dict(ai_ev)
            ai_ev["used_this_request"] = bool(ai_used_this_request)
            ai_ev["source"] = ai_source  # "api" | "cache" | "db_exact"
            ai_ev["db_exact_hit"] = bool(db_exact_hit)
            ai_ev["db_exact_mode"] = _AI_DB_EXACT_MODE
            if cache_age is not None:
                ai_ev["cache_age_sec"] = cache_age
            if ai_source == "cache":
                ai_ev["melting_numbers_from_current_request"] = True
                ai_ev["cached_summary_may_differ_from_numbers"] = True
            evidence = dict(evidence)
            evidence["ai"] = ai_ev
        return {
            "norm": norm,
            "best": best,
            "score": score,
            "confidence": conf,
            "confidence_overall": overall,
            "solidus": solidus,
            "liquidus": liquidus,
            "peak": peak,

            "phase": phase_txt,
            "imc":   merged_imc,
            "risk":  risk,

            "props": props,
            "melting_stage": stage,
            "melting_detail": melting_detail,
            "evidence": evidence,
            "knn": knn,
            "element_roles": full_ai.get("roles", "") if isinstance(full_ai, dict) else "",
            "dopant_rec":    dopant_txt,

            "ai_summary": full_ai.get("summary", "") if isinstance(full_ai, dict) else "",
            "ai_sources": ai_sources,
            "ai_cited_sources": ai_cited_sources,
            "retrieved_candidates": retrieved_candidates,
            "ai_used_this_request": bool(ai_used_this_request),
            "ai_source": ai_source,  # "api" | "cache" | "db_exact"
            "alloy_inference": alloy_inference,
        }
