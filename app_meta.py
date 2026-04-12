"""
제품 표시용 메타데이터 — GUI·FastAPI·웹 UI에서 동일한 출처로 문구를 씁니다.
데모·공유 시 버전·방법론·면책을 명확히 보여 신뢰도를 높입니다.
"""

from __future__ import annotations

DISPLAY_VERSION = "6.4"
API_VERSION_SEMVER = "1.0.0"

PRODUCT_NAME = "AI 합금 분석기"
TAGLINE = (
    "납·무납 솔더 등 합금 조성(wt%)을 입력하면 융점 추정, 상·IMC 인사이트, "
    "문헌 후보, 선택적 AI 요약을 한 화면에서 제공하는 공정·연구 보조 도구입니다."
)

METHODOLOGY_POINTS = [
    "내장 합금 DB와 조성 정규화·유사도(KNN) 매칭으로 고상선·액상선·피크 온도를 추정합니다.",
    "문헌 모드(빠름/정밀)에 따라 공개 메타데이터 API를 통해 DOI·논문 후보를 수집합니다.",
    "IPC-J-STD·JIS 계열 표준 메타 참조(합금·리플로우·플럭스·시험)가 문헌 파이프라인에 자동 포함됩니다(표준 전문 본문은 미제공).",
    "Gemini API가 설정된 경우 자연어 요약·역할·미량 첨가(도핑) 권장을 생성하고, 미설정 시에도 동일 파이프라인의 로컬 규칙 결과로 동작합니다.",
]

DATA_SOURCES = [
    "패키지에 포함된 솔더 참조 데이터베이스",
    "선택: Google Gemini(사용자 API 키)",
    "선택: Crossref·Semantic Scholar 등 공개 메타데이터(네트워크 상태에 따라 제한)",
    "메타 인용: IPC-J-STD(006·020E·033·A-610·TM-650 등), JIS(Z 3282·Z 3198·H 1561 등) — 최신판은 발행 기관에서 확인",
]

# 조성 계열별 규칙(요약): 어떤 입력이 들어와도 적용되는 규칙 기반 설명의 범위를 명시
ALLOY_RULES = [
    {
        "family": "Sn-Ag-Cu (SAC)",
        "when": "Ag>0, Cu>0",
        "phases": "Ag3Sn, Cu6Sn5(및 Cu3Sn 가능)",
        "notes": "범용 무연 솔더. 냉각속도/TAL에 따라 조직 조절",
    },
    {
        "family": "Sn-Cu",
        "when": "Cu>0, Ag≈0",
        "phases": "Cu6Sn5 중심, Cu 과량·장 TAL에서 Cu3Sn",
        "notes": "Cu-rich일수록 계면 IMC 성장 관리 중요",
    },
    {
        "family": "Sn-In",
        "when": "In>=1",
        "phases": "In 농화상 / In-Sn 금속간화합물(예: InSn4)",
        "notes": "저온 공정·젖음 개선에 유리",
    },
    {
        "family": "Sn-Bi",
        "when": "Bi>=3",
        "phases": "Bi 농화 공정/분산상 + Sn 기지",
        "notes": "저융점화 장점, 고함량에서는 취성 주의",
    },
    {
        "family": "Sn-Sb",
        "when": "Sb>0",
        "phases": "SnSb",
        "notes": "고온 강도·크리프 개선, 과량 시 취성 증가 가능",
    },
    {
        "family": "Sn-Ni(미량첨가)",
        "when": "Ni>=0.03",
        "phases": "(Ni,Cu)6Sn5 / Ni3Sn4 가능",
        "notes": "계면 IMC 안정화 및 열피로 특성 개선 경향",
    },
    {
        "family": "Sn-Zn",
        "when": "Zn>=1",
        "phases": "Zn 농화상(분산상)",
        "notes": "원가 이점, 산화·공정 안정성 관리 필요",
    },
    {
        "family": "Sn-Pb",
        "when": "Pb>0",
        "phases": "Pb 농화 공정/분산상",
        "notes": "공정 창은 넓으나 규제(RoHS) 검토 필수",
    },
]

DISCLAIMER = (
    "본 소프트웨어의 수치·그래프·AI 생성 텍스트는 설계 참고용이며, "
    "계약 적합성, 규제 준수, 안전 인증, 원자재 매입의 유일한 근거로 사용하지 마십시오. "
    "최종 판단은 공인 시험, 제조사 공식 TDS, 귀사 내부 표준에 따릅니다."
)


def window_title() -> str:
    return f"{PRODUCT_NAME} — v{DISPLAY_VERSION}"


def header_banner_text() -> str:
    return f"{PRODUCT_NAME}  ·  v{DISPLAY_VERSION}"


def about_text_gui() -> str:
    lines = [
        PRODUCT_NAME,
        f"버전 {DISPLAY_VERSION}",
        "",
        TAGLINE,
        "",
        "【처리 개요】",
        *[f"· {p}" for p in METHODOLOGY_POINTS],
        "",
        "【데이터·연동】",
        *[f"· {p}" for p in DATA_SOURCES],
        "",
        "【조성별 적용 규칙(요약)】",
        "· 형식: 계열 | 적용 조건 | 주요 상/IMC | 해석 포인트",
        *[
            f"· {r['family']} | {r['when']} | {r['phases']} | {r['notes']}"
            for r in ALLOY_RULES
        ],
        "",
        "【면책】",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def about_api_payload() -> dict:
    return {
        "product": PRODUCT_NAME,
        "version": DISPLAY_VERSION,
        "api_version": API_VERSION_SEMVER,
        "tagline": TAGLINE,
        "methodology": METHODOLOGY_POINTS,
        "data_sources": DATA_SOURCES,
        "alloy_rules": ALLOY_RULES,
        "disclaimer": DISCLAIMER,
    }
