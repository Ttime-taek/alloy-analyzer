# Design audit — AI 합금 분석기 (localhost)

**Date:** 2026-04-11  
**URL:** http://127.0.0.1:5173/  
**Classifier:** **APP UI** (도구형, 데이터·입력 중심)  
**Repo:** `test7` (git 없음 → diff-aware 모드·clean-tree 게이트 생략)

## Evidence

- 스크린샷: `.gstack-design-audit/screenshots/first-impression.png` (Temp 원본과 동일)
- Browse: `goto` 200, `perf` total ~56ms (로컬)

---

## Phase 1 — First impression

- **한 줄:** “실험실/엔지니어링용 다크 툴”로 읽힌다. 장식보다는 입력·결과 구조가 먼저다.
- **눈에 들어오는 순서:** (1) 제목·버전 배지 (2) 좌측 주기율표 그리드 (3) 우측 빈 결과 패널 가이드.
- **한 단어로:** *utility* (목적이 분명한 실무 UI)

---

## Phase 2 — Inferred design system (렌더 기준)

| 축 | 관찰 |
|----|------|
| **Fonts** | `system-ui, …, Segoe UI, sans-serif` + 일부 `Times New Roman` / `Arial` (소수 요소). 스킬이 경고하는 “Inter만 쓴 느낌”보다는 **시스템 스택**에 가깝다. |
| **Color** | 다크 배경 + 블루 액센트. **CSS 변수** (`:root`에 `--bg-page`, `--accent` 등) — `frontend/src/index.css`에 정의됨. |
| **Motion** | `prefers-reduced-motion` 존재 (접근성 플러스). |
| **Performance feel** | 로컬 TTFB·DOM 매우 빠름. **콘솔에 500 다수** → “빠르게 그려지지만 백엔드 연동은 깨져 보일 수 있음”. |

**DESIGN.md:** 저장소에 없음. 원하면 스냅샷 기준으로 추출한 토큰을 `DESIGN.md`로 고정할 수 있음.

---

## Phase 3 — 핵심 이슈 (우선순위)

### High — 신뢰·완성도

1. **Console: Failed to load resource 500 (여러 건)**  
   즐겨찾기/`/api/about` 등 API가 실패하면 상단 배지·동기화 문구가 “깨진 제품” 인상을 준다. **디자인 감사 관점에서도** 빈 화면보다 치명적이다.  
   → 백엔드 기동 또는 프록시 확인, 실패 시 UI를 **조용한 오프라인 모드**로 정리하는 편이 낫다.

### Medium — 앱 UI 규칙 정합

2. **좌측 패널 밀도**  
   주기율표 + 즐겨찾기 + 모드가 한 화면에 몰려 있다. **앱 UI 규칙** (“calm surface, strong typography”)에 맞추려면 구역 간 여백·구분선(이미 일부 있음)을 한 단계 더 명확히 할 여지가 있다.

3. **빈 결과 패널**  
   가이드가 잘 되어 있음 (스킬의 “empty state” 기준 통과에 가깝다).

### Polish

4. **반응형**  
   이번 스냅샷은 데스크톱 폭. 모바일에서 그리드·두 컬럼이 어떻게 쌓이는지 별도 `responsive` 스샷 권장.

---

## AI Slop (독립 점수)

- **패턴:** 보라 그라데이션 3열 카드 류는 **해당 없음**.  
- **판정:** **B** (템플릿 느낌보다 “내부 도구”에 가깝다. 다만 다크 + 시스템 폰트는 여전히 **무난한 SaaS 다크** 스펙트럼 안에 있음.)

---

## 총점 (스킬 스키마)

| 지표 | 등급 | 메모 |
|------|------|------|
| **Design Score** | **B-** | 구조·토큰·빈 상태 양호. API 500이 체감 품질을 깎음. |
| **AI Slop Score** | **B** | 전형적인 AI 랜딩 냄새는 약함. |

---

## Quick wins (각 ~30분 이내 목표)

1. API 500 원인 제거 또는 **로딩/오프라인 카피**로 실패를 숨기지 말고 명확히 표시.  
2. `DESIGN.md` 초안: `index.css`에 있는 변수만이라도 문서화.  
3. 좁은 뷰포트에서 한 번 `browse responsive`로 스샷 3장 확보.

---

## Fix loop (스킬 Phase 8)

- **이번 실행:** 감사·보고만 수행. 코드 수정은 **커밋 가능한 git 저장소**가 생기면, finding 단위로 `style(design): …` 커밋 권장.

---

## Outside voices

- Codex / 서브에이전트 미실행 (이 환경에서 전체 파이프라인 생략).

---

**PR 한 줄 요약 (향후):**  
Design review (localhost): Design B- / AI Slop B; 주요 리스크는 **API 500으로 인한 신뢰도 하락**과 좌측 패널 밀도.
