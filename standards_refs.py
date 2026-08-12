"""
IPC-J-STD·JIS 등 솔더/조립 관련 업계 표준 참조 문구.

- 본 패키지는 표준 전문을 제공하지 않으며, 분석·요약 시 **인용·범위 정렬**용 메타 참고입니다.
- 최종 적합성은 발행 최신판 표준 및 고객 규격으로 확인해야 합니다.
"""

from __future__ import annotations

# 문헌 후보·프롬프트·sources에 넣을 한 줄 형식 (URL 포함 → ai_engine 필터 통과)
IPC_JIS_LITERATURE_LINES: list[str] = [
    "[IPC] IPC-J-STD-006 — Requirements for Electronic Grade Solder Alloys and Fluxed and Solid Solders (전자 납땜용 등급 납합금·플럭스 함유/고체 납땜재) "
    "URL:https://www.ipc.org/ipc-standards",
    "[IPC] IPC-J-STD-020E — Moisture/Reflow Sensitivity Classification for Nonhermetic Surface-Mount Devices (습기·리플로우 민감도 등급, 리플로우 피크 설계 시 참고) "
    "URL:https://www.ipc.org/ipc-standards",
    "[IPC] IPC-J-STD-033 — Handling, Packing, Shipping and Use of Moisture/Reflow Sensitive Surface-Mount Devices (습기 민감 SMD 취급·포장·운송) "
    "URL:https://www.ipc.org/ipc-standards",
    "[IPC] IPC-A-610 — Acceptability of Electronic Assemblies (전자 조립물 허용 품질·납땜 외관 등) URL:https://www.ipc.org/ipc-standards",
    "[IPC] IPC-TM-650 — Test Methods Manual (인쇄회로·재료 시험 방법 모음) URL:https://www.ipc.org/ipc-standards",
    "[JIS] JIS Z 3282 — 소프트솔더용 플럭스(납플럭스) URL:https://www.jisc.go.jp/",
    "[JIS] JIS Z 3198 시리즈 — 솔더 페이스트 시험 방법 URL:https://www.jisc.go.jp/",
    "[JIS] JIS H 1561 등 — 주석·납 납땜 합금 재료(규격·개정판 확인) URL:https://www.jisc.go.jp/",
]

# evidence·UI용 짧은 레이블
IPC_JIS_SUMMARY_FOR_EVIDENCE: list[dict[str, str]] = [
    {
        "family": "IPC",
        "id": "J-STD-006",
        "note": "전자용 등급 납합금·플럭스 함유 납·고체 납땜재 요구",
        "url": "https://www.ipc.org/ipc-standards",
    },
    {
        "family": "IPC",
        "id": "J-STD-020E",
        "note": "습기·리플로우 민감도 등급(MSL), 피크 설계 참고",
        "url": "https://www.ipc.org/ipc-standards",
    },
    {
        "family": "IPC",
        "id": "J-STD-033",
        "note": "습기 민감 SMD 취급·포장·운송",
        "url": "https://www.ipc.org/ipc-standards",
    },
    {
        "family": "IPC",
        "id": "A-610",
        "note": "전자 조립물 허용 품질(납땜 등)",
        "url": "https://www.ipc.org/ipc-standards",
    },
    {
        "family": "IPC",
        "id": "TM-650",
        "note": "시험 방법 모음(매뉴얼)",
        "url": "https://www.ipc.org/ipc-standards",
    },
    {
        "family": "JIS",
        "id": "Z 3282",
        "note": "소프트솔더용 플럭스",
        "url": "https://www.jisc.go.jp/",
    },
    {
        "family": "JIS",
        "id": "Z 3198",
        "note": "솔더 페이스트 시험 방법",
        "url": "https://www.jisc.go.jp/",
    },
    {
        "family": "JIS",
        "id": "H 1561",
        "note": "주석·납 납땜 합금 재료",
        "url": "https://www.jisc.go.jp/",
    },
]


def standards_search_hints() -> list[str]:
    """Crossref/S2 검색어 보강용 (논문·기술문서 검색)."""
    return [
        "IPC J-STD-006 solder alloy",
        "IPC J-STD-020 reflow",
        "JIS Z 3282 flux",
        "JIS Z 3198 solder paste",
    ]


def ipc_jis_literature_lines() -> list[str]:
    """AI·문헌 블록에 삽입할 고정 참조 줄(복사본 반환)."""
    return list(IPC_JIS_LITERATURE_LINES)
