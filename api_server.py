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
frontend에서 `npm run dev`(vite server.host=true)로 접속하거나,
빌드 산출물을 같은 호스트의 정적 서버와 함께 배포하세요. Windows는
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
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# 패키지/직접 실행 모두 지원:
# - python -m test7.api_server
# - python -m api_server  (상위 경로를 PYTHONPATH에 추가한 경우)
try:
    from .analyzer import AlloyAnalyzer  # type: ignore
    from .solder_db import SOLDER_DB  # type: ignore
    from .ai_engine import AIEngine  # type: ignore
    from .app_meta import about_api_payload, API_VERSION_SEMVER, PRODUCT_NAME  # type: ignore
except ImportError:
    # package context가 아닐 때는 상위 디렉터리를 sys.path에 추가
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root.parent))
    from test7.analyzer import AlloyAnalyzer  # type: ignore
    from test7.solder_db import SOLDER_DB  # type: ignore
    from test7.ai_engine import AIEngine  # type: ignore
    from test7.app_meta import about_api_payload, API_VERSION_SEMVER, PRODUCT_NAME  # type: ignore


def _load_gemini_key_from_file() -> None:
    """
    uvicorn/별도 cmd에서 GEMINI_API_KEY가 비어 있을 때, 프로젝트 루트의
    .gemini_api_key 또는 gemini_api_key.txt(한 줄)에서 키를 읽어 환경변수에 넣습니다.
    환경변수가 이미 있으면 덮어쓰지 않습니다.
    """
    import os
    from pathlib import Path

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


def _coerce_response_str(v: Any) -> str:
    """analyzer/Gemini가 가끔 list를 넣어도 API 모델은 str만 받도록 정규화."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n".join(str(x).strip() for x in v if str(x).strip())
    return str(v)


def _validate_alloy_comp_dict(v: Any, label: str = "comp") -> Dict[str, float]:
    """CompositionRequest / CompareRequest 공통: wt% 조성 dict 검증."""
    if not isinstance(v, dict) or not v:
        raise ValueError(f"{label}는 최소 1개 이상의 원소를 포함해야 합니다.")
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
        clean[k.strip()] = f
    return clean


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
        description="젖음 대표 온도(℃). 생략 시 액상선+30℃를 BD 입력 온도(250–290℃) 격자로 스냅.",
    )
    include_wetting_grid: bool = Field(
        default=False,
        description="True면 분석 응답에 BD 온도별(250–290℃) 젖음 격자 포함. 기본은 생략(별도 /api/wetting_grid 권장).",
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
    """BD 250–290℃ 격자별 젖음(Fmax/T0)만 조회(전체 분석과 분리)."""

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
        description="젖음 대표 온도(℃). 생략 시 액상선+30℃ 기반 BD 스냅.",
    )
    include_wetting_grid: bool = Field(
        default=False,
        description="각 조성 분석에 BD 온도별 젖음 격자 포함(무거움). 기본 False.",
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
        return s

    @field_validator("comp")
    @classmethod
    def _validate_comp(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not isinstance(v, dict) or not v:
            raise ValueError("comp는 최소 1개 원소가 필요합니다.")
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
            clean[k.strip()] = f
        return clean


class WebFavoritesPayload(BaseModel):
    favorites: List[WebFavoriteItem] = Field(default_factory=list)

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


app = FastAPI(
    title=f"{PRODUCT_NAME} API",
    description="GUI와 동일한 합금 분석 엔진(test7)을 제공하는 HTTP API. `/api/about`에서 제품·면책 정보를 확인할 수 있습니다.",
    version=API_VERSION_SEMVER,
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

_ai_engine = AIEngine()  # GEMINI_API_KEY가 없으면 자동으로 로컬 폴백
_analyzer = AlloyAnalyzer(SOLDER_DB, ai_engine=_ai_engine)


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
    items = _read_web_favorites_file()
    if not items:
        items = _read_gui_favorites_as_list()
        if items:
            try:
                _write_web_favorites_file(items)
            except Exception:
                pass
    return WebFavoritesPayload(favorites=[WebFavoriteItem(**x) for x in items])


@app.put("/api/favorites", response_model=WebFavoritesPayload)
async def put_favorites(body: WebFavoritesPayload) -> WebFavoritesPayload:
    """웹 즐겨찾기 전체 교체(최대 20개)."""
    items = [{"name": x.name, "comp": dict(x.comp)} for x in body.favorites]
    try:
        _write_web_favorites_file(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"즐겨찾기 저장 실패: {e}") from e
    return WebFavoritesPayload(favorites=body.favorites)


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(req: CompositionRequest) -> AnalysisResponse:
    """
    합금 조성(wt%)을 받아 analyzer.analyze_all 결과를 JSON으로 반환.
    React 등 클라이언트에서는 이 엔드포인트만 호출하면 됩니다.
    """
    try:
        result = _analyzer.analyze_all(
            req.comp,
            mode=req.mode or "eng",
            literature_mode=req.literature_mode or "fast",
            wetting_temp_c=req.wetting_temp_c,
            include_wetting_grid=bool(req.include_wetting_grid),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실패: {e}") from e

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
        ai_used_this_request=bool(result.get("ai_used_this_request", False)),
        element_roles=result.get("element_roles") or "",
        dopant_rec=result.get("dopant_rec") or "",
        eng_report=eng_report,
        lab_report=lab_report,
        ai_mode="gemini" if bool(result.get("ai_used_this_request", False)) else "local",
        ai_status_detail=str(getattr(_ai_engine, "status_detail", "") or ""),
        ai_usage_snapshot=dict(
            getattr(_ai_engine, "get_usage_snapshot", lambda: {})() or {}
        ),
    )


@app.post("/api/wetting_grid")
async def wetting_grid(req: WettingGridRequest) -> Dict[str, Any]:
    """
    BD 측정 온도 격자(250–290℃)별 IDW 예측 Fmax(mN)·T₀(s).
    전체 분석과 분리해 필요할 때만 호출합니다.
    """
    try:
        rows = _analyzer.wetting_grid_for_comp(req.comp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"젖음 격자 계산 실패: {e}") from e
    return {"wetting_by_temp": rows}


@app.post("/api/compare", response_model=CompareResponse)
async def compare(req: CompareRequest) -> CompareResponse:
    """
    합금 A/B 두 조성을 받아 각각 analyze_all을 수행하고
    비교 분석용 핵심 요약만 반환.
    """
    try:
        lm = req.literature_mode or "fast"
        ra = _analyzer.analyze_all(
            req.comp_a,
            mode="eng",
            literature_mode=lm,
            wetting_temp_c=req.wetting_temp_c,
            include_wetting_grid=bool(req.include_wetting_grid),
        )
        rb = _analyzer.analyze_all(
            req.comp_b,
            mode="eng",
            literature_mode=lm,
            wetting_temp_c=req.wetting_temp_c,
            include_wetting_grid=bool(req.include_wetting_grid),
        )
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

