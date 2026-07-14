"""
FastAPI backend for alloy analysis.

Usage (dev, 로컬만):
    uvicorn api_server:app --reload --host 127.0.0.1 --port 8000

외부(같은 Wi‑Fi의 다른 PC, 방화벽 허용 시)에서 API 접속:
    uvicorn api_server:app --host 0.0.0.0 --port 8000
    # uvicorn 기본 host는 127.0.0.1 이라 --host 0.0.0.0 이 없으면 외부에서 안 열립니다.

직접 실행(기본 0.0.0.0 — LAN/외부에서 http://<이PC_IP>:8000):
    python api_server.py
    # ALLOY_API_HOST, ALLOY_API_PORT 로 바인딩 변경 / ALLOY_API_CORS=0 이면 CORS 미들웨어 끔

웹 UI를 다른 기기에서 쓰려면: FastAPI를 위처럼 0.0.0.0으로 띄운 뒤,
`frontend/dist`를 이 서버가 함께 제공하므로 http://<host>:8000/ 로 접속하거나,
빌드 산출물을 별도 정적 서버와 함께 배포하세요. Windows는
고급 방화벽에서 해당 포트 인바운드 허용이 필요할 수 있습니다.

배포(웹 공개) 요약:
  1) frontend: npm ci && npm run build
  2) 서버에 test7 전체 복사 후 GEMINI_API_KEY 환경변수 설정
  3) python api_server.py — `frontend/dist`가 있으면 같은 주소에서 UI+API 제공(ALLOY_SERVE_STATIC=0 으로 API만 가능)

The core analysis logic is reused from the existing test7 package
so that GUI와 서버가 항상 동일한 엔진을 사용합니다.
"""

import json
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from .ai_engine import AIEngine  # type: ignore
    from .analyzer import AlloyAnalyzer  # type: ignore

# 패키지/직접 실행 모두 지원:
# - python -m test7.api_server
# - python -m api_server  (상위 경로를 PYTHONPATH에 추가한 경우)
try:
    from .app_meta import about_api_payload, API_VERSION_SEMVER, PRODUCT_NAME  # type: ignore
except ImportError:
    # package context가 아닐 때는 상위 디렉터리를 sys.path에 추가
    import sys

    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root.parent))
    from test7.app_meta import about_api_payload, API_VERSION_SEMVER, PRODUCT_NAME  # type: ignore

try:
    from .composition_recommend import (  # type: ignore
        MeltTarget,
        list_db_compositions_matching_melt_target,
        merge_db_registered_into_recommend_candidates,
        recommend_compositions,
        _melt_target_l1_score,
    )
except ImportError:
    try:
        from test7.composition_recommend import (  # type: ignore
            MeltTarget,
            list_db_compositions_matching_melt_target,
            merge_db_registered_into_recommend_candidates,
            recommend_compositions,
            _melt_target_l1_score,
        )
    except Exception:
        MeltTarget = None  # type: ignore
        recommend_compositions = None  # type: ignore
        list_db_compositions_matching_melt_target = None  # type: ignore
        merge_db_registered_into_recommend_candidates = None  # type: ignore
        _melt_target_l1_score = None  # type: ignore

try:
    from .melting_predictor import MELTING_ENGINE_VERSION  # type: ignore
except ImportError:
    try:
        from test7.melting_predictor import MELTING_ENGINE_VERSION  # type: ignore
    except Exception:
        MELTING_ENGINE_VERSION = "?"  # type: ignore

try:
    from .env_loader import load_env_keys  # type: ignore
except Exception:
    try:
        from test7.env_loader import load_env_keys  # type: ignore
    except Exception:
        load_env_keys = None  # type: ignore

try:
    from .favorites_store import (  # type: ignore
        FavoritesStoreError,
        read_supabase_favorites,
        supabase_configured,
        write_supabase_favorites,
    )
except ImportError:
    from test7.favorites_store import (  # type: ignore
        FavoritesStoreError,
        read_supabase_favorites,
        supabase_configured,
        write_supabase_favorites,
    )


def _load_gemini_key_from_file() -> None:
    """
    uvicorn/별도 cmd에서 GEMINI_API_KEY가 비어 있을 때, 프로젝트 루트의
    .gemini_api_key 또는 gemini_api_key.txt(한 줄)에서 키를 읽어 환경변수에 넣습니다.
    환경변수가 이미 있으면 덮어쓰지 않습니다.
    """
    if (os.getenv("GEMINI_API_KEY") or "").strip():
        return
    root = Path(__file__).resolve().parent
    for name in (".gemini_api_key", "gemini_api_key.txt"):
        path = root / name
        if not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        for line in raw.splitlines():
            key = line.strip()
            if not key or key.startswith("#"):
                continue
            os.environ["GEMINI_API_KEY"] = key
            return


_load_gemini_key_from_file()

# Cerebras 키도 동일한 규칙으로 .env에서 로드(환경변수가 이미 있으면 덮어쓰지 않음).
if load_env_keys:
    try:
        load_env_keys(["CEREBRAS_API_KEY"], override=False)
    except Exception:
        pass


def _coerce_response_str(v: Any) -> str:
    """analyzer/Gemini가 가끔 list를 넣어도 API 모델은 str만 받도록 정규화."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n".join(str(x).strip() for x in v if str(x).strip())
    return str(v)


_AlloyAnalyzerClass = None
_AIEngineClass = None
_SOLDER_DB = None


def _load_analysis_runtime() -> tuple[Any, Any, Any]:
    global _AlloyAnalyzerClass, _AIEngineClass, _SOLDER_DB
    if _AlloyAnalyzerClass is not None and _AIEngineClass is not None and _SOLDER_DB is not None:
        return _AlloyAnalyzerClass, _AIEngineClass, _SOLDER_DB
    try:
        from .ai_engine import AIEngine as _RuntimeAIEngine  # type: ignore
        from .analyzer import AlloyAnalyzer as _RuntimeAlloyAnalyzer  # type: ignore
        from .solder_db import SOLDER_DB as _RuntimeSolderDB  # type: ignore
    except ImportError:
        from test7.ai_engine import AIEngine as _RuntimeAIEngine  # type: ignore
        from test7.analyzer import AlloyAnalyzer as _RuntimeAlloyAnalyzer  # type: ignore
        from test7.solder_db import SOLDER_DB as _RuntimeSolderDB  # type: ignore
    _AlloyAnalyzerClass = _RuntimeAlloyAnalyzer
    _AIEngineClass = _RuntimeAIEngine
    _SOLDER_DB = _RuntimeSolderDB
    return _AlloyAnalyzerClass, _AIEngineClass, _SOLDER_DB


def _alloy_analyzer_cls() -> Any:
    analyzer_cls, _, _ = _load_analysis_runtime()
    return analyzer_cls


class _LazyRuntimeSymbol:
    def __init__(self, symbol_name: str):
        self.symbol_name = symbol_name

    def _resolve(self) -> Any:
        analyzer_cls, ai_engine_cls, solder_db = _load_analysis_runtime()
        if self.symbol_name == "AlloyAnalyzer":
            return analyzer_cls
        if self.symbol_name == "AIEngine":
            return ai_engine_cls
        if self.symbol_name == "SOLDER_DB":
            return solder_db
        raise AttributeError(self.symbol_name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._resolve()(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)


AlloyAnalyzer = _LazyRuntimeSymbol("AlloyAnalyzer")
AIEngine = _LazyRuntimeSymbol("AIEngine")
SOLDER_DB = _LazyRuntimeSymbol("SOLDER_DB")


def _validate_alloy_comp_dict(v: Any, label: str = "comp") -> Dict[str, float]:
    """CompositionRequest / CompareRequest 공통: wt% 조성 dict 검증."""
    if not isinstance(v, dict) or not v:
        raise ValueError(f"{label}는 최소 1개 이상의 원소를 포함해야 합니다.")
    analyzer_cls = _alloy_analyzer_cls()
    clean: Dict[str, float] = {}
    for k, val in v.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError("원소 기호는 문자열이어야 합니다.")
        try:
            f = float(val)
        except Exception:
            raise ValueError(f"{k} 값은 숫자여야 합니다.")
        if f < 0:
            raise ValueError(f"{k} 값은 0 이상이어야 합니다.")
        sk = k.strip()
        try:
            canon = analyzer_cls.canonical_element_symbol(sk)
        except ValueError as e:
            raise ValueError(f"{label}: {e}") from e
        if canon not in analyzer_cls.KNOWN_PERIODIC_METALS:
            raise ValueError(f"{label}: 지원하지 않는 원소 기호: {sk}")
        clean[canon] = float(clean.get(canon, 0.0)) + f
    total_wt = float(sum(clean.values()))
    if total_wt <= 0.0:
        raise ValueError(f"{label}: 모든 원소 wt%가 0입니다.")
    strict = (os.getenv("ALLOY_STRICT_COMP_SUM") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if strict and not (99.5 <= total_wt <= 100.5):
        raise ValueError(
            f"{label}: wt% 합이 {total_wt:.2f}% 입니다. "
            "ALLOY_STRICT_COMP_SUM 사용 시 99.5~100.5%만 허용합니다."
        )
    return clean


def _require_wt_sum_100_00(comp: Dict[str, float], label: str = "comp") -> None:
    """웹·API 공통: 화면과 동일하게 소수 둘째 자리 반올림 합이 100.00%일 때만 분석."""
    total = round(float(sum(comp.values())), 2)
    if total != 100.0:
        raise ValueError(
            f"{label}: wt% 합이 {total:.2f}% 입니다. "
            "총합이 100.00%가 되도록 맞춘 뒤 분석하세요."
        )


def _composition_notes_for_raw_comp(comp: Dict[str, float]) -> tuple[float, list[str]]:
    """정규화 전 요청 comp 합계에 대한 사용자 안내(분석 응답에 실어 표시)."""
    total = float(sum(comp.values()))
    notes: list[str] = []
    if total <= 0:
        return total, notes
    if total < 99.5:
        notes.append(
            f"입력 wt% 합은 {total:.2f}% 입니다. 엔진이 100%에 맞추며, "
            "미달분은 주로 Sn으로 보정합니다. 의도한 조성과 다를 수 있으니 가능하면 합이 100%가 되도록 맞춰 주세요."
        )
    elif total > 100.5:
        notes.append(
            f"입력 wt% 합은 {total:.2f}% 입니다. 엔진이 비율로 스케일합니다. "
            "의도한 조성과 다를 수 있으니 확인하세요."
        )
    return total, notes


class CompositionRequest(BaseModel):
    """합금 조성 입력 (wt%). 예: {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}"""

    comp: Dict[str, float] = Field(
        ..., description="원소 기호 → wt% 매핑 (예: {'Sn': 96.5, 'Ag': 3.0})"
    )
    mode: str | None = Field(
        default="eng",
        description="분석 모드: 'eng'(엔지니어 요약) 또는 'lab'(연구소 보고)",
    )
    literature_mode: str | None = Field(
        default="fast",
        description="문헌 검색 모드: 'fast'(빠름) 또는 'deep'(정밀)",
    )
    wetting_temp_c: float | None = Field(
        default=None,
        description="젖음 대표 온도(℃). 생략 시 액상선+30℃를 측정 DB 온도(250–290℃)에 맞춤.",
    )
    include_wetting_grid: bool = Field(
        default=False,
        description="True면 분석 응답에 250–290℃ 온도별 젖음 표를 포함. 기본은 생략(별도 /api/wetting_grid 권장).",
    )

    @field_validator("comp")
    @classmethod
    def _validate_comp(cls, v: Dict[str, float]) -> Dict[str, float]:
        return _validate_alloy_comp_dict(v, "comp")

    @field_validator("mode", mode="before")
    @classmethod
    def _validate_mode(cls, v: str | None) -> str:
        if not v:
            return "eng"
        v = v.strip().lower()
        return "lab" if v == "lab" else "eng"

    @field_validator("literature_mode", mode="before")
    @classmethod
    def _validate_literature_mode(cls, v: str | None) -> str:
        if not v:
            return "fast"
        v = v.strip().lower()
        return "deep" if v in ("deep", "precise", "detailed", "slow") else "fast"


class AnalysisResponse(BaseModel):
    """analyzer.analyze_all 결과의 핵심 필드만 노출."""

    norm: Dict[str, float]
    best_name: str | None
    score: float
    confidence: float
    confidence_overall: float

    solidus: float
    liquidus: float
    peak: float

    phase: str
    imc: list[str]
    risk: list[str]

    props: Dict[str, Any]
    melting_stage: int
    melting_detail: Dict[str, Any]
    evidence: Dict[str, Any]

    ai_summary: str
    ai_sources: list[str]
    ai_cited_sources: list[str]
    retrieved_candidates: list[str]
    ai_used_this_request: bool
    ai_source: str = Field(
        default="",
        description="api | cache | db_exact — AI 응답 출처(analyzer와 동일)",
    )
    element_roles: str
    dopant_rec: str
    eng_report: str
    lab_report: str
    ai_mode: str
    ai_status_detail: str
    ai_usage_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="AI 엔진 세션 누적 사용량(GUI 상단과 동일)",
    )
    comp_input_wt_sum: float = Field(
        default=0.0,
        ge=0.0,
        description="요청 body의 comp에서 계산한 wt% 합(엔진 정규화 전)",
    )
    composition_notes: list[str] = Field(
        default_factory=list,
        description="입력 합이 100% 근처가 아닐 때 정규화 안내 문구",
    )
    alloy_inference: Dict[str, Any] = Field(
        default_factory=dict,
        description="3-NN IDW+릿지 기반 고상/액상 추정, 권장 피크, 공정 주의 리포트",
    )

    @field_validator(
        "phase",
        "ai_summary",
        "element_roles",
        "dopant_rec",
        "eng_report",
        "lab_report",
        mode="before",
    )
    @classmethod
    def _coerce_text_fields(cls, v: Any) -> str:
        return _coerce_response_str(v)


class WettingGridRequest(BaseModel):
    """250–290℃ 온도별 젖음(Fmax/T0)만 조회(전체 분석과 분리)."""

    comp: Dict[str, float] = Field(..., description="wt% 조성")

    @field_validator("comp")
    @classmethod
    def _validate_wg_comp(cls, v: Dict[str, float]) -> Dict[str, float]:
        return _validate_alloy_comp_dict(v, "comp")


class CompareRequest(BaseModel):
    """두 합금 조성을 비교 분석하기 위한 요청"""

    comp_a: Dict[str, float]
    comp_b: Dict[str, float]
    wetting_temp_c: float | None = Field(
        default=None,
        description="젖음 대표 온도(℃). 생략 시 A·B 공통: 각 액상선+30℃ 스냅값 중 더 높은 BD 격자 온도.",
    )
    include_wetting_grid: bool = Field(
        default=False,
        description="각 조성 분석에 온도별 젖음 표 포함(무거움). 기본 False.",
    )
    literature_mode: str | None = Field(
        default="fast",
        description="문헌 검색 모드: 'fast'(빠름) 또는 'deep'(정밀)",
    )

    @field_validator("literature_mode", mode="before")
    @classmethod
    def _validate_compare_literature_mode(cls, v: str | None) -> str:
        if not v:
            return "fast"
        v = v.strip().lower()
        return "deep" if v in ("deep", "precise", "detailed", "slow") else "fast"

    @field_validator("comp_a")
    @classmethod
    def _validate_comp_a(cls, v: Dict[str, float]) -> Dict[str, float]:
        return _validate_alloy_comp_dict(v, "comp_a")

    @field_validator("comp_b")
    @classmethod
    def _validate_comp_b(cls, v: Dict[str, float]) -> Dict[str, float]:
        return _validate_alloy_comp_dict(v, "comp_b")


class CompareOne(BaseModel):
    name: str | None
    confidence: float
    solidus: float
    liquidus: float
    peak: float
    props: Dict[str, Any]
    imc_line: str = Field(
        default="",
        description="IMC(금속간화합물) 요약(비교 표용 전체 텍스트, 항목은 줄바꿈 구분)",
    )
    risk_line: str = Field(
        default="",
        description="위험도/리스크 요약(비교 표용 전체 텍스트)",
    )


class CompareResponse(BaseModel):
    a: CompareOne
    b: CompareOne
    ai_usage_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="비교 완료 시점의 AI 엔진 세션 누적 사용량",
    )


class FreeAxisSpec(BaseModel):
    """목표 융점 탐색에서 변화시킬 wt% 축."""

    element: str = Field(..., description="원소 기호 (예: Bi)")
    min: float = Field(..., description="최소 wt%")
    max: float = Field(..., description="최대 wt%")
    step: float = Field(..., gt=0, description="증분 wt%")


class MeltTargetPayload(BaseModel):
    """고상/액상(℃) 목표 — 둘 중 하나 이상 필요."""

    solidus_c: float | None = Field(default=None, description="목표 고상선(℃)")
    solidus_tolerance_c: float = Field(
        default=50.0,
        ge=0,
        description=(
            "고상 허용 ±℃(격자·penalty). "
            "DB 밴드는 한 축만 목표일 때 축별 max(이 값, 50℃); "
            "고상·액상 동시 목표일 때는 요청 허용만 사용(추가 ±50℃ 확장 없음)."
        ),
    )
    liquidus_c: float | None = Field(default=None, description="목표 액상선(℃)")
    liquidus_tolerance_c: float = Field(
        default=50.0,
        ge=0,
        description=(
            "액상 허용 ±℃(격자·penalty). "
            "DB 밴드는 한 축만 목표일 때 축별 max(이 값, 50℃); "
            "고상·액상 동시 목표일 때는 요청 허용만 사용."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_target(self) -> "MeltTargetPayload":
        if self.solidus_c is None and self.liquidus_c is None:
            raise ValueError("solidus_c 또는 liquidus_c 중 하나 이상을 지정하세요.")
        return self


class RecommendMeltRequest(BaseModel):
    """
    고정 조성·가변 축·밸런스 원소로 목표 고상/액상에 가까운 조성 후보를 격자 탐색합니다.
    결과는 모델 기반 후보이며 정답 조성이 아닙니다(meta.disclaimer 참고).
    """

    fixed_comp: Dict[str, float] = Field(
        default_factory=dict,
        description="고정 wt% (비어 있어도 됨). balance_element·free 축과 합이 100%가 되도록 맞춤.",
    )
    free_axes: List[FreeAxisSpec] = Field(
        ..., min_length=1, description="스윕할 원소별 min/max/step"
    )
    balance_element: str = Field(default="Sn", description="나머지 wt%를 채울 원소")
    target: MeltTargetPayload
    max_results: int = Field(
        default=10,
        ge=1,
        le=500,
        description="탐색 결과 표에 반환할 최대 행 수(격자+DB 병합 시 max_db_similar_alloys와 함께 상한에 사용).",
    )
    max_grid_points: int = Field(default=15_000, ge=50, le=200_000)
    balance_min: float = Field(default=0.02, ge=0, le=100)
    balance_max: float = Field(default=98.0, ge=0, le=100)
    max_db_similar_alloys: int = Field(
        default=12,
        ge=1,
        le=500,
        description=(
            "solder_db 밴드 일치 행을 가져올 때의 상한. "
            "탐색 결과 표에는 max(max_results, 이 값)건까지 격자+DB를 한 목록으로 합쳐 반환합니다."
        ),
    )
    max_db_registered_in_candidates: int = Field(
        default=4,
        ge=0,
        le=500,
        description=(
            "병합 표(`candidates`)에 넣을 solder_db 등록 행 최대 개수(목표 penalty가 낮은 순). "
            "밴드 일치 DB가 많을 때 표가 DB만으로 채워지지 않게 한다. **0**이면 개수 제한 없음."
        ),
    )
    rank_match_any_axis: bool = Field(
        default=False,
        description=(
            "고상·액상 목표를 **둘 다** 줄 때: True면 정렬 점수·penalty가 더 잘 맞는 축(min) 기준 "
            "(한 축만 목표에 가까워도 상위). False면 L1 합(|Δ고상|+|Δ액상|) — 이중 목표에 권장."
        ),
    )

    @field_validator("fixed_comp")
    @classmethod
    def _validate_fixed_comp(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not v:
            return {}
        return _validate_alloy_comp_dict(v, "fixed_comp")

    @field_validator("balance_element")
    @classmethod
    def _strip_balance_el(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("balance_element가 비어 있습니다.")
        return s

    @model_validator(mode="after")
    def _balance_bounds(self) -> "RecommendMeltRequest":
        if self.balance_min > self.balance_max:
            raise ValueError("balance_min은 balance_max 이하여야 합니다.")
        return self


class RecommendMeltRow(BaseModel):
    comp: Dict[str, float]
    norm: Dict[str, float]
    solidus: float
    liquidus: float
    peak: float
    melting_stage: int
    match_score: float
    match_confidence: float
    best_name: str | None = None
    db_close_names: str | None = Field(
        default=None,
        description="조성 최근접 + 예측 고상·액상에 가까운 solder_db 참고명(중점 구분)",
    )
    penalty: float = Field(
        ...,
        description=(
            "목표 대비 정렬용 점수(낮을수록 우선). 기본 L1 합; rank_match_any_axis 시 고상·액상 "
            "둘 다 지정된 경우 min(|ΔTs|,|ΔTl|)과 동일 계열."
        ),
    )
    plastic_range_c: float = Field(
        ...,
        description="과냉각 구간(액상−고상) ℃. Score 동점 시 좁은 순 우선.",
    )
    melting_detail_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="응답 크기 절약용 melting_detail 요약(family, layers_preview 등)",
    )
    melt_row_source: str = Field(
        default="predicted_grid",
        description="predicted_grid(모델 예측 융점) | solder_db_registered(DB 등록 고상·액상 우선)",
    )
    registered_name: str | None = Field(
        default=None,
        description="solder_db 등록명(melt_row_source가 solder_db_registered일 때)",
    )


class RecommendMeltDbSimilarRow(BaseModel):
    """레거시 스키마 호환용. DB 행은 ``candidates``에 병합되며 이 목록은 항상 비어 있습니다."""

    name: str
    comp: Dict[str, float]
    solidus: float
    liquidus: float
    penalty: float = Field(
        default=0.0,
        description="목표 고상·액상 대비 L1 오차 합(|ΔTs|+|ΔTl|), 지정된 목표 축만 합산",
    )
    plastic_range_c: float = Field(
        default=0.0,
        description="과냉각 구간(액상−고상) ℃. 목록 정렬 시 Score 동점용",
    )
    source: str = Field(default="solder_db")


class RecommendMeltResponse(BaseModel):
    candidates: List[RecommendMeltRow]
    meta: Dict[str, Any]
    db_similar_alloys: List[RecommendMeltDbSimilarRow] = Field(
        default_factory=list,
        description="스키마 호환용으로 항상 빈 배열. solder_db 행은 candidates에 포함됩니다.",
    )


def _shrink_melting_detail_for_api(md: Any) -> Dict[str, Any]:
    if not isinstance(md, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in ("family", "best_dist", "measured_anchor", "melt_temperatures_source", "registered_db_name"):
        if k in md:
            out[k] = md[k]
    layers = md.get("layers")
    if isinstance(layers, list):
        out["layers_preview"] = [str(x) for x in layers[:5]]
    return out


def _repair_legacy_korean_mojibake(value: str) -> str:
    """Repair UTF-8 Korean text that a legacy Windows path decoded as CP949."""
    has_cjk_ideograph = any("\u4e00" <= char <= "\u9fff" for char in value)
    if not has_cjk_ideograph:
        return value
    try:
        repaired = value.encode("cp949").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    has_hangul = any("\uac00" <= char <= "\ud7a3" for char in repaired)
    has_cjk_after = any("\u4e00" <= char <= "\u9fff" for char in repaired)
    return repaired if has_hangul and not has_cjk_after else value


class WebFavoriteItem(BaseModel):
    """웹 즐겨찾기 한 항목 (React localStorage와 동일 형태)."""

    name: str
    comp: Dict[str, float]

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        s = (v or "").strip()
        if not s:
            raise ValueError("이름이 비어 있습니다.")
        return _repair_legacy_korean_mojibake(s)

    @field_validator("comp")
    @classmethod
    def _validate_comp(cls, v: Dict[str, float]) -> Dict[str, float]:
        return _validate_alloy_comp_dict(v, "comp")


class WebFavoritesPayload(BaseModel):
    favorites: List[WebFavoriteItem] = Field(default_factory=list)
    storage: str = "local"
    allow_empty: bool = False

    @field_validator("favorites")
    @classmethod
    def _max_items(cls, v: List[WebFavoriteItem]) -> List[WebFavoriteItem]:
        if len(v) > 20:
            raise ValueError("즐겨찾기는 최대 20개까지 저장할 수 있습니다.")
        return v


def _web_favorites_path() -> Path:
    return Path(__file__).resolve().parent / "web_favorites.json"


def _gui_favorites_path() -> Path:
    """Tk GUI가 저장하는 favorites.json (이름 → 조성 dict)."""
    return Path(__file__).resolve().parent / "favorites.json"


def _read_gui_favorites_as_list() -> List[Dict[str, Any]]:
    """GUI favorites.json을 웹 형태 [{name, comp}, ...]로 변환."""
    path = _gui_favorites_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []
    out: List[Dict[str, Any]] = []
    for name, comp in raw.items():
        name = str(name).strip()
        if not name or not isinstance(comp, dict):
            continue
        try:
            clean = WebFavoriteItem(
                name=name, comp={str(k): float(v) for k, v in comp.items()}
            )
            out.append({"name": clean.name, "comp": clean.comp})
        except Exception:
            continue
    return out[:20]


def _read_web_favorites_file() -> List[Dict[str, Any]]:
    path = _web_favorites_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = raw.get("favorites") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        comp = it.get("comp")
        if not name or not isinstance(comp, dict):
            continue
        try:
            clean = WebFavoriteItem(name=name, comp={str(k): float(v) for k, v in comp.items()})
            out.append({"name": clean.name, "comp": clean.comp})
        except Exception:
            continue
    return out[:20]


def _write_web_favorites_file(items: List[Dict[str, Any]]) -> None:
    path = _web_favorites_path()
    tmp = path.with_suffix(".json.tmp")
    payload = {"favorites": items[:20]}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """기동 시 어떤 api_server.py·포트인지 터미널에 남겨, 8000에 구버전이 떠 있을 때 원인 추적이 쉽게 함."""
    melt_ok = any(
        getattr(route, "path", None) == "/api/recommend_melt" for route in app.routes
    )
    _here = Path(__file__).resolve()
    print(f"[api_server] 로드된 파일: {_here}", flush=True)
    print(f"[api_server] 작업 디렉터리: {os.getcwd()}", flush=True)
    print(
        f"[api_server] POST /api/recommend_melt: {'등록됨' if melt_ok else '없음 — 이 저장소의 api_server.py 로 다시 실행했는지 확인'}",
        flush=True,
    )
    yield


app = FastAPI(
    title=f"{PRODUCT_NAME} API",
    description="GUI와 동일한 합금 분석 엔진(test7)을 제공하는 HTTP API. `/api/about`에서 제품·면책 정보를 확인할 수 있습니다.",
    version=API_VERSION_SEMVER,
    lifespan=_lifespan,
)


@app.middleware("http")
async def _ensure_utf8_charset(request, call_next):
    """JSON/HTML 등 응답에 charset이 없으면 UTF-8을 명시(한글 깨짐 방지)."""
    response = await call_next(request)
    ct = response.headers.get("content-type") or ""
    if not ct or "charset=" in ct.lower():
        return response
    if ct.startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    elif ct.startswith("text/html"):
        response.headers["content-type"] = "text/html; charset=utf-8"
    elif ct.startswith("text/css"):
        response.headers["content-type"] = "text/css; charset=utf-8"
    elif ct.startswith(("application/javascript", "text/javascript")):
        base = ct.split(";")[0].strip()
        response.headers["content-type"] = f"{base}; charset=utf-8"
    return response


@app.middleware("http")
async def _no_cache_spa_assets(request, call_next):
    """UI 빌드 후에도 브라우저가 예전 index.html/JS를 쓰지 않도록 캐시 억제."""
    response = await call_next(request)
    path = request.url.path or ""
    if path == "/" or path.endswith((".html", ".js", ".css", ".mjs")):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# 다른 PC·다른 포트의 웹에서 API를 직접 호출할 때 브라우저 CORS 차단 방지.
# ALLOY_API_CORS=0 이면 비활성화(폐쇄망 전용 등).
if (os.getenv("ALLOY_API_CORS") or "").strip().lower() not in ("0", "false", "no", "off"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

_ai_engine: Any | None = None
_analyzer: Any | None = None
_analyzer_lock = threading.Lock()


def _get_engine_bundle() -> tuple[Any, Any]:
    """무거운 AI/Gemini 초기화를 첫 요청까지 지연해 `/openapi.json` 등 가벼운 엔드포인트 응답을 빠르게 합니다."""
    global _ai_engine, _analyzer
    if _analyzer is not None and _ai_engine is not None:
        return _ai_engine, _analyzer
    with _analyzer_lock:
        if _analyzer is None or _ai_engine is None:
            _ai_engine = AIEngine()  # GEMINI_API_KEY가 없으면 자동으로 로컬 폴백
            _, _, runtime_solder_db = _load_analysis_runtime()
            _analyzer = AlloyAnalyzer(runtime_solder_db, ai_engine=_ai_engine)
    return _ai_engine, _analyzer


@app.get("/api/about")
async def api_about() -> Dict[str, Any]:
    """제품명·버전·방법론·데이터 출처·면책(웹/GUI 정보 패널용)."""
    return about_api_payload()


@app.get("/api/favorites", response_model=WebFavoritesPayload)
async def get_favorites() -> WebFavoritesPayload:
    """
    웹 즐겨찾기 목록. 서버 파일(web_favorites.json)에 저장되어
    다른 PC·휴대폰에서 같은 주소로 접속해도 동일 목록을 불러올 수 있습니다.
    web이 비어 있으면 GUI용 favorites.json을 읽어 자동 이관합니다
    (localhost vs 192.168 접속 시 localStorage가 달라 비던 경우 대비).
    """
    if supabase_configured():
        try:
            items = await read_supabase_favorites()
        except FavoritesStoreError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return WebFavoritesPayload(
            favorites=[WebFavoriteItem(**x) for x in items],
            storage="supabase",
        )

    items = _read_web_favorites_file()
    if not items:
        items = _read_gui_favorites_as_list()
        if items:
            try:
                _write_web_favorites_file(items)
            except Exception:
                pass
    return WebFavoritesPayload(
        favorites=[WebFavoriteItem(**x) for x in items],
        storage="local",
    )


@app.put("/api/favorites", response_model=WebFavoritesPayload)
async def put_favorites(body: WebFavoritesPayload) -> WebFavoritesPayload:
    """웹 즐겨찾기 전체 교체(최대 20개)."""
    items = [{"name": x.name, "comp": dict(x.comp)} for x in body.favorites]
    if supabase_configured():
        try:
            if not items and not body.allow_empty:
                existing = await read_supabase_favorites()
                if existing:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Refusing to replace existing favorites with an empty "
                            "list without allow_empty=true."
                        ),
                    )
            await write_supabase_favorites(items)
        except FavoritesStoreError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return WebFavoritesPayload(favorites=body.favorites, storage="supabase")

    try:
        _write_web_favorites_file(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"즐겨찾기 저장 실패: {e}") from e
    return WebFavoritesPayload(favorites=body.favorites, storage="local")


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(req: CompositionRequest) -> AnalysisResponse:
    """
    합금 조성(wt%)을 받아 analyzer.analyze_all 결과를 JSON으로 반환.
    React 등 클라이언트에서는 이 엔드포인트만 호출하면 됩니다.
    """
    _ai_engine, _analyzer = _get_engine_bundle()
    try:
        _require_wt_sum_100_00(dict(req.comp), "comp")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    sum_in, comp_notes = _composition_notes_for_raw_comp(dict(req.comp))
    # Cerebras 폴백이 이번 요청에서 실제 응답을 만들었는지 카운터 델타로 판정
    _cb_before = int(((getattr(_ai_engine, "usage_stats", {}) or {}).get("ask_cerebras_success", 0)) or 0)
    try:
        result = _analyzer.analyze_all(
            req.comp,
            mode=req.mode or "eng",
            literature_mode=req.literature_mode or "fast",
            wetting_temp_c=req.wetting_temp_c,
            include_wetting_grid=bool(req.include_wetting_grid),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}") from e
    _cb_after = int(((getattr(_ai_engine, "usage_stats", {}) or {}).get("ask_cerebras_success", 0)) or 0)
    _cerebras_used_this_request = bool(_cb_after > _cb_before)

    best = result.get("best") or {}
    norm = result.get("norm") or {}
    # GUI와 동일한 형태의 엔지니어 보고서 텍스트 생성
    try:
        comp_str = ", ".join(
            f"{k}{float(v):.2f}%" for k, v in norm.items()  # type: ignore[arg-type]
        )
    except Exception:
        comp_str = str(norm)
    try:
        knn = _analyzer.find_knn(norm, k=3)  # type: ignore[arg-type]
    except Exception:
        knn = []
    try:
        eng_report = _ai_engine.build_eng_report(comp_str, result, knn)
    except Exception:
        eng_report = ""
    lab_report = ""
    if (req.mode or "eng").strip().lower() == "lab":
        try:
            lab_report = _ai_engine.build_lab_report(comp_str, result, knn)
        except Exception:
            lab_report = ""
    return AnalysisResponse(
        norm=result.get("norm") or {},
        best_name=best.get("name"),
        score=float(result.get("score", 0.0) or 0.0),
        confidence=float(result.get("confidence", 0.0) or 0.0),
        confidence_overall=float(result.get("confidence_overall", 0.0) or 0.0),
        solidus=float(result.get("solidus", 0.0) or 0.0),
        liquidus=float(result.get("liquidus", 0.0) or 0.0),
        peak=float(result.get("peak", 0.0) or 0.0),
        phase=result.get("phase") or "",
        imc=[str(x) for x in (result.get("imc") or [])],
        risk=[str(x) for x in (result.get("risk") or [])],
        props=result.get("props") or {},
        melting_stage=int(result.get("melting_stage", 0) or 0),
        melting_detail=result.get("melting_detail") or {},
        evidence=result.get("evidence") or {},
        ai_summary=result.get("ai_summary") or "",
        ai_sources=[str(x) for x in (result.get("ai_sources") or [])],
        ai_cited_sources=[str(x) for x in (result.get("ai_cited_sources") or [])],
        retrieved_candidates=[str(x) for x in (result.get("retrieved_candidates") or [])],
        ai_used_this_request=bool(result.get("ai_used_this_request", False)) or _cerebras_used_this_request,
        ai_source=str(result.get("ai_source") or ""),
        element_roles=result.get("element_roles") or "",
        dopant_rec=result.get("dopant_rec") or "",
        eng_report=eng_report,
        lab_report=lab_report,
        ai_mode=(
            "cerebras"
            if _cerebras_used_this_request
            else (
                "cache"
                if str(result.get("ai_source") or "").strip().lower() == "cache"
                else (
                    "gemini"
                    if bool(result.get("ai_used_this_request", False))
                    else "local"
                )
            )
        ),
        ai_status_detail=str(getattr(_ai_engine, "status_detail", "") or ""),
        ai_usage_snapshot=dict(
            getattr(_ai_engine, "get_usage_snapshot", lambda: {})() or {}
        ),
        comp_input_wt_sum=float(sum_in),
        composition_notes=list(comp_notes),
        alloy_inference=result.get("alloy_inference") or {},
    )


@app.post("/api/wetting_grid")
async def wetting_grid(req: WettingGridRequest) -> Dict[str, Any]:
    """
    측정 DB 온도(250–290℃)별 IDW 예측 Fmax(mN)·T₀(s).
    전체 분석과 분리해 필요할 때만 호출합니다.
    """
    _, _analyzer = _get_engine_bundle()
    try:
        rows = _analyzer.wetting_grid_for_comp(req.comp)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"온도별 젖음 표 계산 실패: {e}") from e
    return {"wetting_by_temp": rows}


@app.post("/api/recommend_melt", response_model=RecommendMeltResponse)
async def recommend_melt(req: RecommendMeltRequest) -> RecommendMeltResponse:
    """
    목표 고상/액상에 근접하는 조성을 격자로 탐색하고, 동일 목표·동일 밴드의 solder_db 등록 합금을
    한 목록(`candidates`)으로 합쳐 반환합니다. 등록 DB 행은 고상·액상에 실측/문헌값을 쓰며,
    표에는 `max_db_registered_in_candidates`로 DB 행 수를 제한해 격자(미지 조성) 후보가 밀리지 않게 합니다.

    solder_db 근접 행은 `candidates`에만 병합되어 반환됩니다(`db_similar_alloys`는 비어 있음).

    GUI 엔진과 동일하게 validate → normalize → find_best_match → calc_melting_with_detail 경로를 사용합니다.

    배포 시 `frontend/dist`를 같은 앱에서 서빙하면, 이 라우트가 없는 옛 프로세스로 POST가
    넘어가 StaticFiles가 405를 반환할 수 있으니 코드 갱신 후 api_server를 재시작하세요.
    """
    if recommend_compositions is None or MeltTarget is None:
        raise HTTPException(
            status_code=501,
            detail="composition_recommend 모듈을 불러오지 못했습니다.",
        )
    _, _analyzer = _get_engine_bundle()
    tgt = MeltTarget(
        solidus_c=req.target.solidus_c,
        solidus_tolerance_c=float(req.target.solidus_tolerance_c),
        liquidus_c=req.target.liquidus_c,
        liquidus_tolerance_c=float(req.target.liquidus_tolerance_c),
        rank_match_any_axis=bool(req.rank_match_any_axis),
    )
    axes = [ax.model_dump() for ax in req.free_axes]
    try:
        rows, meta = recommend_compositions(
            _analyzer,
            fixed_comp=dict(req.fixed_comp),
            free_axes=axes,
            balance_element=req.balance_element,
            target=tgt,
            max_results=req.max_results,
            max_grid_points=req.max_grid_points,
            balance_min=req.balance_min,
            balance_max=req.balance_max,
            unbounded_sorted_return=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"목표 융점 탐색 실패: {e}") from e

    db_meta: Dict[str, Any] = {}
    db_raw: List[Dict[str, Any]] = []
    dual_melt_target = (
        req.target.solidus_c is not None and req.target.liquidus_c is not None
    )
    if list_db_compositions_matching_melt_target:
        try:
            # 고상·액상 동시 목표: AND + 사용자 허용만(±50℃ 강제 확장 끔)으로 DB 밀림 방지.
            # 한 축만 목표: OR + 최소 밴드로 근사 행 회수 유지.
            db_raw, db_meta = list_db_compositions_matching_melt_target(
                _analyzer,
                tgt,
                match_any_specified_axis=not dual_melt_target,
                max_rows=int(req.max_db_similar_alloys),
                min_axis_band_tolerance_c=0.0 if dual_melt_target else 50.0,
            )
            if (
                dual_melt_target
                and db_raw
                and callable(_melt_target_l1_score)
            ):
                tol_sum = float(req.target.solidus_tolerance_c) + float(
                    req.target.liquidus_tolerance_c
                )
                l1_cap = max(15.0, 0.23 * tol_sum)
                before = len(db_raw)
                db_raw = [
                    r
                    for r in db_raw
                    if _melt_target_l1_score(
                        float(r["solidus"]),
                        float(r["liquidus"]),
                        tgt,
                    )
                    <= l1_cap
                ]
                db_meta = {
                    **db_meta,
                    "db_similar_l1_cap": round(l1_cap, 3),
                    "db_similar_pre_l1_filter": before,
                    "db_similar_post_l1_filter": len(db_raw),
                }
        except Exception as e:
            db_meta = {"db_similar_match_error": str(e)}
            db_raw = []

    unified_max = min(500, max(int(req.max_results), int(req.max_db_similar_alloys)))
    merge_fn = merge_db_registered_into_recommend_candidates
    if merge_fn is not None:
        merged, merge_meta = merge_fn(
            _analyzer,
            rows,
            db_raw,
            tgt,
            max_results=unified_max,
            max_db_registered_in_merged=int(req.max_db_registered_in_candidates),
        )
        rows = merged
        meta = {**meta, **merge_meta}
    else:
        rows = rows[: max(1, int(req.max_results))]

    meta = {
        **meta,
        **db_meta,
        "melt_unified_max_rows": unified_max,
        "melt_unified_list": True,
        "melt_rank_match_any_axis": bool(req.rank_match_any_axis),
        "db_similar_match_rule": (
            "dual_target_and_band_user_only_l1_cap"
            if dual_melt_target
            else "solidus_or_liquidus_in_band_merged_candidates_sorted_by_target_score"
        ),
        "melting_engine_version": str(MELTING_ENGINE_VERSION),
    }

    candidates: List[RecommendMeltRow] = []
    for r in rows:
        md = r.get("melting_detail") if isinstance(r, dict) else {}
        src = str(r.get("melt_row_source") or "predicted_grid")
        reg = r.get("registered_name")
        candidates.append(
            RecommendMeltRow(
                comp=dict(r["comp"]),
                norm=dict(r["norm"]),
                solidus=float(r["solidus"]),
                liquidus=float(r["liquidus"]),
                peak=float(r["peak"]),
                melting_stage=int(r["melting_stage"]),
                match_score=float(r["match_score"]),
                match_confidence=float(r["match_confidence"]),
                best_name=r.get("best_name"),
                db_close_names=r.get("db_close_names"),
                penalty=float(r["penalty"]),
                plastic_range_c=float(r.get("plastic_range_c", r["liquidus"] - r["solidus"])),
                melting_detail_summary=_shrink_melting_detail_for_api(md),
                melt_row_source=src,
                registered_name=str(reg).strip() if reg else None,
            )
        )

    return RecommendMeltResponse(
        candidates=candidates,
        meta=meta,
        db_similar_alloys=[],
    )


@app.post("/api/compare", response_model=CompareResponse)
async def compare(req: CompareRequest) -> CompareResponse:
    """
    합금 A/B 두 조성을 받아 각각 analyze_all을 수행하고
    비교 분석용 핵심 요약만 반환.
    """
    _ai_engine, _analyzer = _get_engine_bundle()
    try:
        _require_wt_sum_100_00(dict(req.comp_a), "comp_a")
        _require_wt_sum_100_00(dict(req.comp_b), "comp_b")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        lm = req.literature_mode or "fast"
        wet_t, wet_basis = _analyzer.compare_wetting_temp_c(
            req.comp_a, req.comp_b, req.wetting_temp_c
        )
        ra = _analyzer.analyze_all(
            req.comp_a,
            mode="eng",
            literature_mode=lm,
            wetting_temp_c=wet_t,
            wetting_temp_basis=wet_basis,
            include_wetting_grid=bool(req.include_wetting_grid),
        )
        rb = _analyzer.analyze_all(
            req.comp_b,
            mode="eng",
            literature_mode=lm,
            wetting_temp_c=wet_t,
            wetting_temp_basis=wet_basis,
            include_wetting_grid=bool(req.include_wetting_grid),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"비교 분석 실패: {e}") from e

    def _one(r: Dict[str, Any]) -> CompareOne:
        best = (r.get("best") or {}) if isinstance(r, dict) else {}
        imc_list = [str(x) for x in (r.get("imc") or [])]
        risk_list = [str(x) for x in (r.get("risk") or [])]

        def _one_line(items: List[str], empty: str) -> str:
            cleaned = [s.strip() for s in items if isinstance(s, str) and s.strip()]
            if not cleaned:
                return empty
            # 비교 표에서 IMC/리스크 본문 전체 표시(항목은 빈 줄로 구분). 극단적 크기만 상한.
            out = "\n\n".join(cleaned)
            _max = 12000
            if len(out) > _max:
                out = out[: _max - 3].rstrip() + "..."
            return out

        return CompareOne(
            name=best.get("name"),
            confidence=float(r.get("confidence", 0.0) or 0.0),
            solidus=float(r.get("solidus", 0.0) or 0.0),
            liquidus=float(r.get("liquidus", 0.0) or 0.0),
            peak=float(r.get("peak", 0.0) or 0.0),
            props=r.get("props") or {},
            imc_line=_one_line(imc_list, "IMC 요약 없음"),
            risk_line=_one_line(risk_list, "리스크 특이사항 없음"),
        )

    snap: Dict[str, Any] = {}
    try:
        fn = getattr(_ai_engine, "get_usage_snapshot", None)
        if callable(fn):
            snap = dict(fn() or {})
    except Exception:
        snap = {}
    return CompareResponse(a=_one(ra), b=_one(rb), ai_usage_snapshot=snap)


def _frontend_dist_dir() -> Optional[Path]:
    """Vite 빌드 산출물 `frontend/dist` (api_server.py 기준). 없으면 None."""
    dist = Path(__file__).resolve().parent / "frontend" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        return dist
    return None


def _should_serve_frontend_static() -> bool:
    """ALLOY_SERVE_STATIC=0 이면 끔. 그 외에는 dist가 있으면 서빙."""
    v = (os.getenv("ALLOY_SERVE_STATIC") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return _frontend_dist_dir() is not None


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    """브라우저 기본 요청 — public/favicon.svg 제공."""
    dist = _frontend_dist_dir()
    if dist is None:
        raise HTTPException(status_code=404, detail="Not found")
    svg = dist / "favicon.svg"
    if not svg.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(svg, media_type="image/svg+xml")


# 배포: `frontend`에서 npm run build 후, 같은 프로세스가 UI+API 제공 (fetch "/api/..." 동일 출처).
if _should_serve_frontend_static():
    _dist = _frontend_dist_dir()
    if _dist is not None:
        from starlette.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")


if __name__ == "__main__":
    # 개발용 편의 실행: python api_server.py
    # 기본 0.0.0.0 → 같은 네트워크의 다른 기기에서 http://<이PC_IP>:8000 접속 가능
    import uvicorn

    _host = (os.getenv("ALLOY_API_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    _port_raw = (os.getenv("ALLOY_API_PORT") or "8000").strip()
    try:
        _port = int(_port_raw)
    except ValueError:
        _port = 8000

    # 앱 객체를 직접 넘겨서, reload 시 문자열 모듈 재-임포트로 인해
    # (다른 경로의) 구 api_server 모듈이 섞이는 문제를 방지합니다.
    # reload=True는 import-string 형태가 아니면 경고가 뜨고,
    # (이 프로젝트는) 실제로는 수동 재시작으로 충분합니다.
    uvicorn.run(app, host=_host, port=_port, reload=False)
