<!-- /autoplan restore point: /Users/ttime/.gstack/projects/Ttime-taek-alloy-analyzer/master-autoplan-restore-20260722-082456.md -->
# 합금 분석기 고도화 계획

**Status: APPROVED — user selected A on 2026-07-22**

## 목표

이 제품을 **DB로 검증되는 미등록 합금 조성 예측기**로 고도화한다. 사용자가 DB에 없는 조성을 입력해도 고상선·액상선·물성·리플로우 참고 범위를 예측하되, 결과마다 산출 경로·유사 합금·검증 오차·외삽 위험을 함께 제공한다. 원격 AI 설명은 늦거나 실패해도 수치 예측을 막거나 바꾸지 않는다.

## 사용자 확인을 통과한 핵심 전제

1. 대부분의 입력은 DB 정확 일치가 아니며 **미등록 조성 예측이 기본 경로**다.
2. DB는 입력 허용 목록이 아니라 학습·보간·검증·근거 데이터다.
3. 결정적 계산은 재현 가능한 산출 경로이지 곧바로 사실을 뜻하지 않는다. 예측값에는 오차와 적용 범위를 붙인다.
4. 정확 일치 DB 값은 모델 보정으로 변경하지 않는다. 미등록 조성은 근접 보간·회귀 보정·물리 제약을 결합한다.
5. 생성형 AI는 수치를 생성하거나 덮어쓰지 않고 설명·요약·문헌 후보만 보강한다.
6. 데이터 부족과 외삽 위험이 큰 경우에는 그럴듯한 생산 권고 대신 `판단 보류` 또는 잠정 범위를 제공한다.
7. AI 할당량·외부 API 장애는 핵심 수치 예측 사용을 막지 않아야 한다.

## 우선순위 범위

### P1. 미등록 조성 검증과 예측 근거 계약

- 정확 일치, 보간, 모델 추정, 적용 범위 밖의 네 경로를 명시한다.
- 알려진 합금을 의도적으로 제외하고 다시 예측하는 홀드아웃 평가기를 추가한다.
- 고상선·액상선·인장강도별 MAE와 오차 분포를 산출하고 모델/DB 버전과 함께 기록한다.
- 값마다 `prediction_method`, 유사 합금, 최근접 거리, 검증 MAE, 예측 범위, 외삽 위험, 권고 허용 수준을 제공한다.
- 현재 임의 가중 신뢰도는 `검증된 정확도`처럼 보이지 않도록 분리하고 의미를 명시한다.
- 재훈련 자체는 이번 범위 밖이지만 평가 결과로 재훈련 필요 여부를 판정한다.

### P1. 수치·공정 가드

- 정확 일치 DB 값 보존, 조성 합계, 지원 원소, 정상 온도 범위, `solidus <= liquidus < recommended_peak`를 검증한다.
- 권장 피크는 액상선 안전 여유와 장비/부품 한계를 함께 만족할 때만 확정 표현한다.
- 데이터 부족, 모델 불일치, 적용 범위 밖 입력은 자동 교정으로 숨기지 않고 판단 보류 사유를 노출한다.
- `DB 실측`, `DB 보간`, `모델 추정`, `문헌 참고` 라벨의 의미를 API와 UI에서 동일하게 사용한다.

### P1. 즉시 핵심 분석과 독립 AI 보강

- 기존 `/api/analyze`의 수치 엔진 결과와 원격 AI 서술 생성을 분리한다.
- 핵심 수치·예측 근거·리플로우 참고 범위를 먼저 표시한다.
- AI 설명은 독립 요청으로 로드하고 실패 시 규칙 기반 설명을 유지한다.
- 재분석 시 이전 요청을 취소하고 요청 ID가 다르면 늦게 도착한 응답을 버린다.

### P2. 결과 중심 UX

- 첫 화면 순서를 `사용 가능 수준 -> 예측 범위/중심값 -> 근거/오차 -> 다음 행동 -> 공정 참고 -> AI 설명`으로 고정한다.
- `핵심 예측 완료`, `AI 설명 생성 중`, `부분 실패`, `판단 보류` 상태를 구분한다.
- 모바일에서도 핵심 예측값과 외삽 위험은 접지 않고 먼저 보여준다.
- AI 오류는 문제·원인·해결 방법을 표시하고 AI 부분만 재시도한다.

### P2. 관측성과 회귀 방지

- 핵심 계산 시간, AI 시간, 캐시 여부, 예측 경로, 폴백/판단 보류 사유를 구조화된 메타데이터로 남긴다.
- API·엔진·React 테스트로 정확 일치 보존, 미등록 조성 경로, 수치 가드, 요청 경쟁, AI 실패, 모바일 핵심 상태를 검증한다.
- 운영 캐너리에서 핵심 분석 지연과 콘솔 오류를 점검한다.

## 완료 기준

- 미등록 조성 홀드아웃 평가 보고서에 속성별 표본 수·MAE·중앙 오차·95백분위 오차가 기록된다.
- 현재 모델 대비 평가 성능이 악화되지 않으며, 기준 미달 속성은 UI에서 확정값으로 표현되지 않는다.
- 정확 일치 DB 조성에서 측정 고상선·액상선이 모델 보정으로 변하는 회귀 0건.
- 모든 예측값에 산출 방식과 근거가 있으며, 적용 범위 밖 입력은 명시적으로 구분된다.
- 핵심 분석 첫 표시 p50 3초 이내, p95 8초 이내.
- AI 실패·할당량 초과 시에도 핵심 수치와 로컬 설명을 사용할 수 있다.
- 새 조성을 연속 분석해도 이전 AI 결과가 새 결과에 노출되지 않는다.
- Python·frontend 테스트, 빌드, 린트, 운영 브라우저 QA를 통과한다.
- 키보드 흐름, 비동기 상태 알림, 색상 외 상태 표현, 44px 터치 대상, 본문 대비 4.5:1 이상을 검증한다.

## 범위 제외

- 새로운 유료 AI 제공자 도입
- 검증 결과 확인 전의 전체 모델 재훈련
- CALPHAD 엔진 신규 도입 또는 상용 데이터베이스 구매
- DB 스키마 대규모 마이그레이션
- 데스크톱 GUI 전체 리디자인
- 목표 물성 기반 다목적 역설계·Pareto 후보 생성(후속 P3)

---

# Phase 1 — CEO Review

## 0A. 전제 검증

| 전제 | 평가 | 결정 |
|---|---|---|
| 미등록 조성이 기본 경로 | 사용자 확인과 코드 구조상 타당 | 최상위 목표로 승격 |
| 결정적 결과가 정답 | 재현성과 정확성을 혼동 | `산출 경로 + 검증 오차`가 신뢰의 근거가 되도록 수정 |
| 단일 신뢰도 점수로 충분 | 현재 가중치는 검증 정확도가 아님 | 거리·오차·외삽·모델 불일치를 분리 |
| 수치 순서만 맞으면 안전 | 필요조건일 뿐 충분조건이 아님 | 판단 보류 정책과 공정 한계 추가 |
| AI 설명은 핵심 기능 | 근거 없음 | 수치 경로와 격리하고 후순위 유지 |

## 0B. What already exists

| 하위 문제 | 재사용할 기존 코드 | 남은 간극 |
|---|---|---|
| 미등록 용융점 추정 | `alloy_property_inference.py`, `melting_ensemble.py`, `melting_predictor.py` | 홀드아웃 평가·오차 구간·통합 출처 계약 부재 |
| 정확 일치 보존 | `tests/test_alloy_property_inference.py`의 200°C 회귀 | API 전체 응답 가드와 다수 조성 회귀 필요 |
| 근접 합금 근거 | `alloy_inference.neighbors`, `melting_detail` | 거리 의미·적용 범위·검증 MAE 미노출 |
| 속성 예측 | `models.py`, `solder_properties.py`, 문헌/DB 폴백 | 속성별 불확실성과 권고 허용 수준 부재 |
| 수치/AI 생성 | `analyzer.py::analyze_all` | 한 호출에 결합되어 핵심 결과가 원격 AI를 기다림 |
| API 계약 | `api_server.py::AnalysisResponse` | 수치 근거와 AI 필드가 한 응답 모델에 결합 |
| 부분 상태 UI | `App.jsx` 로딩/오프라인/접기 패턴 | 핵심 완료·AI 진행·판단 보류 상태 부재 |
| 요청 취소 기반 | `frontend/src/api.js`의 `signal` 지원 | 분석 호출에서 AbortController/요청 ID 미사용 |

## 0C. Dream state

```text
CURRENT
조성 입력 -> 단일 분석 호출 -> 수치 + AI를 함께 기다림 -> 단일 신뢰도와 복수 출처가 혼재
   |
   v
THIS PLAN
조성 입력 -> 예측 경로 판정 -> 수치 + 근거 + 오차 먼저 표시 -> AI 설명은 독립 보강
                           \-> 적용 범위 밖이면 판단 보류
   |
   v
12-MONTH IDEAL
목표 물성/공정 제약 -> 검증된 후보군/Pareto 비교 -> 실험계획 -> 측정값 회수 -> 모델 재검증
```

이번 계획은 미등록 조성의 **추적 가능한 예측**까지 도달한다. 실험 결과를 되먹임하는 능동학습, 상용 열역학 교차검증, 다목적 역설계는 12개월 이상 상태와의 차이로 남긴다.

## 0C-bis. 구현 대안

| 접근 | 구현량 | 장점 | 위험 | 결정 |
|---|---:|---|---|---|
| A. 기존 응답 유지 + 라벨만 추가 | 작음 | 호환성이 높음 | 정확도 검증과 지연 문제를 해결하지 못함 | 기각 |
| B. 검증 계약 + 핵심/AI 분리 | 중간 | 미등록 예측 신뢰성과 체감 속도를 함께 개선 | API/프론트 상태 전환이 늘어남 | **선택** |
| C. SSE 단일 스트림 + 실시간 모델 앙상블 | 큼 | 단계별 결과 전달이 자연스러움 | 배포·재연결·테스트 복잡도가 과도함 | 후속 검토 |

선택 원칙: 미등록 예측 검증을 놓치지 않는 가장 단순한 구조인 B를 채택한다.

## 0D. 선택적 확장 결정

| 항목 | 범위 결정 | 근거 |
|---|---|---|
| 홀드아웃 평가기 | 포함 | 핵심 가치의 검증이며 기존 DB/모델을 재사용 |
| 속성별 근거 계약 | 포함 | API와 UI에 직접 필요한 신뢰 경계 |
| 판단 보류 정책 | 포함 | 위험한 확정 표현을 막는 필수 안전장치 |
| 핵심/AI 분리 | 포함 | 현 17초대 신규 분석 지연과 외부 장애 결합 해소 |
| 전체 재훈련 | 제외 | 평가 결과 없이는 방법과 범위가 결정되지 않음 |
| 역설계·Pareto 추천 | 연기 | 전략적 가치가 크지만 현재 분석 경로보다 범위가 큼 |

## 0E. 시간축 검토

```text
HOUR 1  입력 정규화·지원 범위·정확 일치 보존 계약 고정
HOUR 2  홀드아웃 평가기와 현재 기준선 생성
HOUR 3  예측 근거/외삽/권고 수준 응답 모델 추가
HOUR 4  핵심 계산과 AI 보강 경계 분리
HOUR 5  React 부분 상태·취소·늦은 응답 차단
HOUR 6+ 회귀/통합/브라우저/성능 검증 및 문서화
```

## 0F. 모드

`SELECTIVE EXPANSION`을 유지한다. 사용자 확인에 따라 미등록 예측 검증은 확장하고, 재훈련·역설계·상용 엔진 도입은 연기한다.

## CEO dual voices

### CLAUDE SUBAGENT — strategic independence

- Critical: 계획이 응답 구조에 치우쳐 미등록 조성 예측 성능 검증이 주변화됨.
- Critical: 결정적 계산을 사실로 취급하지 말고 산출 경로와 오차를 신뢰의 기준으로 삼아야 함.
- High: 외삽·모델 불일치·판단 보류와 정확 일치 보존을 완료 기준에 포함해야 함.
- High: 전문 도구보다 약한 열역학 기반을 근거 추적성과 실제 시험 피드백으로 보완해야 함.

### CODEX SAYS — strategy challenge

- 사용자의 실제 의사결정을 정의하지 않은 채 응답 분리가 목표를 대신하고 있음.
- 현재 `confidence_overall`은 내부 휴리스틱이며 검증 정확도로 읽히면 안 됨.
- `solidus <= liquidus <= peak`만으로 공정 안전을 주장할 수 없으며 판단 불가 경로가 필요함.
- 장기적으로는 단일 분석보다 제약조건 기반 후보 선별과 실험 의사결정이 더 큰 가치일 수 있음.

### CEO DUAL VOICES — CONSENSUS TABLE

| Dimension | Subagent | Codex | Consensus |
|---|---|---|---|
| 1. Premises valid? | 수정 필요 | 수정 필요 | CONFIRMED |
| 2. Right problem to solve? | 미등록 예측 검증으로 재정의 | 의사결정/후보 선별로 재정의 | CONFIRMED |
| 3. Scope calibration correct? | 데이터 검증 부족 | 안전·책임 경계 부족 | CONFIRMED |
| 4. Alternatives sufficiently explored? | 부족 | 부족 | CONFIRMED |
| 5. Competitive/market risks covered? | 전문 도구 대비 근거 약함 | CALPHAD/사내 도구 대비 포지션 불명 | CONFIRMED |
| 6. 6-month trajectory sound? | 빠르지만 부정확할 위험 | 실패를 매끄럽게 감출 위험 | CONFIRMED |

합의된 구조 변경은 사용자가 확인한 “미등록 조성 예측이 키포인트”와 일치하므로 계획에 반영했다. 추가 사용자 도전 항목은 없다.

## Section 1. Architecture Review

현재 `analyze_all`이 수치 계산, 근거 조립, AI 호출, 보고서 생성을 한 덩어리로 수행한다. 예측 계약을 순수한 핵심 결과로 만들고 AI는 그 스냅샷을 읽는 보강 단계로 분리한다. 계산 모델과 출처 계약은 API/GUI가 공유하고, React만의 별도 수치 판단을 최소화한다.

## Section 2. Error & Rescue Registry

| 실패 | 감지 | 사용자 표현 | 복구 |
|---|---|---|---|
| 지원하지 않는 원소/합계 오류 | 입력 검증 | 잘못된 항목과 허용 범위 | 입력 수정 전 분석 중단 |
| 정확 일치 DB 값 변형 | 불변식/회귀 | 내부 오류, 확정값 미표시 | DB 측정값 보존 후 경고 로그 |
| 근접 데이터 부족 | 거리/표본 수 | 외삽 위험 높음 | 범위만 표시하거나 판단 보류 |
| 모델 간 큰 불일치 | 예측 차이 기준 | 신뢰 낮음과 원인 | 생산 권고 비활성화 |
| AI 시간초과/할당량 | 독립 요청 오류 | 핵심 예측은 유지 | AI 부분만 재시도/로컬 설명 |
| 늦은 이전 응답 | 요청 ID 불일치 | 사용자에게 노출하지 않음 | 응답 폐기 |
| 리플로우 한계 충돌 | 공정 가드 | 권고 불가 사유 | 사용자 제약 수정 또는 검증 요청 |

## Section 3. Security & Threat Model

새 인증 체계나 비밀 저장은 추가하지 않는다. API 키는 서버 `.env`에서만 읽고 응답·로그·프론트 번들에 포함하지 않는다. 조성 키·문헌 문자열·AI 응답의 크기와 형식을 검증하며, 개발 메타데이터에는 원문 프롬프트나 키를 남기지 않는다. CORS와 공개 API 남용은 현 배포 설정을 유지하되 분석/AI 호출 분리로 외부 호출이 증폭되지 않도록 재시도 상한을 둔다.

## Section 4. Data Flow & Interaction Edge Cases

정확 일치, 근접 보간, 희박 데이터, 적용 범위 밖의 네 경로를 테스트한다. 빈 조성, 100% 초과, 미지원 원소, 부동소수점 경계, A/B 비교 중 한쪽 실패, 빠른 연속 재분석, AI만 재시도, 탭 이동, 캐시 응답이 신규 응답보다 늦게 도착하는 경우를 명세한다. 핵심 결과는 요청 ID와 정규화 조성 해시를 함께 가져 서로 다른 조성에 합쳐지지 않게 한다.

## Section 5. Code Quality Review

`App.jsx`가 약 7천 줄로 결과·입력·리플로우를 모두 포함하는 구조는 새 상태를 직접 덧붙일수록 위험하다. 이번 범위에서는 예측 근거 카드와 분석 요청 상태를 작은 모듈/훅으로 추출한다. Python에서는 수치 핵심과 AI 보강을 명시적 함수로 분리하고, 출처 문자열은 열거형 또는 상수로 통일한다.

## Section 6. Test Review

현재 정확 일치 200°C 회귀와 다수 엔진 단위 테스트는 있으나 미등록 조성 성능을 계량하는 홀드아웃 테스트가 없다. 평가기는 정확 일치 행을 학습/이웃 집합에서 제외한 뒤 예측해야 하며 데이터 누수를 검사한다. API 계약, 판단 보류, 핵심/AI 독립 실패, React의 이전 응답 폐기까지 통합 테스트를 추가한다.

## Section 7. Performance Review

현 병목은 원격 AI가 단일 `/api/analyze` 반환을 막는 구조다. 핵심 계산 시간과 AI 시간을 분리 계측한다. A/B 비교가 두 번의 AI를 순차 호출하지 않게 하고, 홀드아웃 평가는 요청마다 실행하지 않고 개발/CI 보고서로 생성한다. 불필요한 DB 재구성과 전체 이웃 정렬을 프로파일링한다.

## Section 8. Observability & Debuggability Review

`request_id`, 정규화 조성 해시, 모델/DB 버전, 예측 경로, 핵심/AI 소요 시간, 캐시, 외삽 위험, 판단 보류 코드를 구조화한다. 사용자는 이해 가능한 원인만 보고 개발 로그는 민감정보 없이 진단 정보를 보유한다. 같은 값이 API 요약·추론 패널·리플로우 패널에서 다르게 표시되면 감지할 수 있는 계약 테스트를 둔다.

## Section 9. Deployment & Rollout Review

API 응답 필드 추가는 하위 호환으로 시작하고 프론트가 새 필드를 사용한 뒤 AI 분리를 기본화한다. Vercel 프론트와 Render API의 배포 시차를 견디도록 누락 필드 폴백을 둔다. 운영 캐너리에서 기존 정확 일치 예제, 대표 미등록 조성, AI 오프라인 상태를 확인한다. DB/모델 버전 변경 없이 배포하며 롤백은 이전 단일 호출 경로로 가능하게 유지한다.

## Section 10. Long-Term Trajectory Review

이번 변경이 성공하면 다음 경쟁력은 실제 시험값 회수와 모델 재검증이다. 단일 기준 합금 Δ는 목적 함수가 다른 사용자에게 오해를 줄 수 있으므로 후속으로 유사 기준 자동 선택 또는 사용자 목표 기준 비교가 필요하다. 상용 CALPHAD와 정면 경쟁하기보다 미등록 납땜 합금의 빠른 선별·근거 추적·실험 우선순위화에 집중한다.

## Section 11. Design & UX Review

핵심 정보 위계는 예측값보다도 **예측 방식과 사용 가능 수준**을 같은 화면에 붙이는 방향이어야 한다. `AI 분석` 문구가 수치의 출처로 오해되지 않도록 핵심 결과와 AI 설명을 시각적으로 분리한다. 로딩·부분 성공·판단 보류·AI 실패 상태를 독립적으로 설계하고 모바일에서 외삽 경고를 접지 않는다.

## Failure Modes Registry

| 모드 | 심각도 | 현재 공백 | 결정 |
|---|---|---|---|
| 미등록 조성의 과도한 외삽 | Critical | 휴리스틱 플래그 일부만 존재 | 거리·불일치·검증오차로 판단 보류 추가 |
| 정확 일치 DB 오염 | Critical | 단일 회귀만 존재 | 다수 앵커 및 API 계약 회귀 추가 |
| 신뢰도 오해 | High | 단일 백분율 | 검증 지표와 휴리스틱 분리 |
| 리플로우 자동 교정이 실패 은폐 | High | 권고 불가 상태 없음 | 확정/잠정/보류 수준 추가 |
| AI가 전체 응답 지연 | High | 단일 동기 경로 | 핵심/AI 분리 |
| 이전 요청 결과 혼입 | High | 취소/ID 가드 없음 | AbortController + 요청 ID |
| 프론트/API 버전 불일치 | Medium | 필드 누락 폴백 제한 | 단계적 호환 배포 |

## NOT in scope

- 상용 CALPHAD 데이터/엔진 도입: 구매·라이선스·검증 범위가 별도 프로젝트다.
- 전체 모델 재훈련: 먼저 홀드아웃 기준선을 생성해 필요성을 판단한다.
- 역설계·Pareto 후보 추천: 장기 가치가 높지만 이번 핵심 분석 계약보다 범위가 크다.
- 실험실 장비 자동 연동: 데이터 전략의 후속 단계다.
- 데스크톱 GUI 전체 재구성: 웹 핵심 흐름과 회귀 검증을 우선한다.

## CEO Decision Audit Trail

| 결정 | 원칙 | 결과 |
|---|---|---|
| 미등록 예측 검증을 P1로 승격 | 완전성 우선 | 포함 |
| 핵심/AI 분리 유지 | 사용자 가치 + 장애 격리 | 포함 |
| 판단 보류 정책 | 안전하고 명시적인 구조 | 포함 |
| 전체 재훈련 | 검증 전 성급한 확장 금지 | 연기 |
| 역설계 | 장기 가치 높으나 범위 큼 | `TODOS.md`로 연기 |
| SSE | 단순성 우선 | 채택하지 않음 |

## CEO Completion Summary

| 영역 | 상태 | 핵심 결과 |
|---|---|---|
| 전제 | 완료 | 미등록 예측 기본 경로로 사용자 확인 |
| 기존 코드 활용 | 완료 | 현재 추론·근거·테스트 자산 재사용 |
| 제품 범위 | 완료 | 검증 계약·가드·AI 분리 포함 |
| 오류/구조/보안 | 완료 | 판단 보류와 비밀 경계 명세 |
| 데이터/상태 | 완료 | 네 예측 경로와 요청 경합 명세 |
| 코드/테스트 | 완료 | 홀드아웃·API·React 회귀 필요 |
| 성능/관측 | 완료 | 핵심/AI 시간 분리 및 구조화 메타데이터 |
| 배포/장기 | 완료 | 하위 호환 배포, 역설계는 후속 |
| Dual voices | 완료 | 6/6 차원에서 방향 수정 합의 |

**Phase 1 complete.** Codex: 12 concerns. Independent subagent: 8 issues. Consensus: 6/6 confirmed, 0 unresolved disagreements. Passing to Phase 2.

---

# Phase 2 — Design Review

## Step 0. Design scope

- UI 범위: 있음. 핵심 결과, 불확실성, 판단 보류, AI 부분 상태가 변경된다.
- 초기 완성도: **5/10**. 데이터 필드는 구체적이지만 화면 위계·상태 전이·접근성이 구현자 판단에 남아 있었다.
- 10/10 기준: 데스크톱/모바일 구조, 속성별 읽기 단위, 전체/속성 상태, 판단 보류 동작, 모든 비동기 상태와 접근성 기준이 명시된 상태.
- 디자인 기준: `DESIGN.md`의 Pretendard, 다크 토큰, 720px 중단점, 44px 터치 대상, `prefers-reduced-motion`, `CollapsibleSection` 접근성 패턴을 재사용한다.
- 시각 시안: gstack designer 바이너리는 있으나 별도 OpenAI 이미지 키가 없어 생성하지 않았다. 프로젝트 키는 읽거나 복사하지 않았고 텍스트 와이어프레임으로 대체한다.

## Design dual voices

### CLAUDE SUBAGENT — independent design review

- Critical: 핵심값 내부의 순서와 판단 보류 시 허용 행동이 명시되지 않음.
- Critical: 로딩·부분 성공·AI 실패·재분석 상태가 이름만 있고 화면 계약이 없음.
- High: 값·범위·방법·사용 가능 수준을 하나의 읽기 단위로 묶어야 함.
- High: 새 배지/카드 증식보다 결과 요약·근거 상세·공정 판단의 작업 공간 구조가 필요함.

### CODEX SAYS — UX challenge

- 데이터 순서가 아니라 `사용 가능 여부 -> 범위 -> 근거 -> 다음 행동`의 결정 순서가 첫 화면을 지배해야 함.
- 전체 상태와 속성별 상태가 모두 필요하며, 판단 보류 시 생산 권고 생성 자체를 막아야 함.
- 모바일/접근성 명세가 사실상 없고, 불확실성 지표를 전부 나열하면 투명성이 아니라 인지 부하가 됨.
- UI뿐 아니라 복사·보고서에도 보류 상태와 모델/DB 버전이 보존되어야 함.

### Design litmus scorecard

| Litmus | Subagent | Codex | Consensus decision |
|---|---|---|---|
| 첫 화면에서 제품/상태가 분명한가 | 사용 수준을 먼저 | 사용 수준을 먼저 | CONFIRMED |
| 하나의 강한 시각적 중심이 있는가 | 속성 읽기 단위 | 상태 + 범위 테이블 | CONFIRMED |
| 제목/상태만 훑어도 이해되는가 | 현재 부족 | 현재 부족 | CONFIRMED — 카피 계약 추가 |
| 각 영역이 한 가지 역할만 하는가 | AI 분리 필요 | 근거/행동 분리 필요 | CONFIRMED |
| 카드가 실제 상호작용에 필요한가 | 카드 증식 반대 | 카드 모자이크 반대 | CONFIRMED |
| 모션이 위계를 개선하는가 | 상태 안정성 우선 | 포커스/레이아웃 이동 금지 | CONFIRMED |
| 장식 그림자 없이도 전문적인가 | 표/행 구조 권장 | 얇은 경계와 타이포 권장 | CONFIRMED |

## Pass 1. Information Architecture — 5/10 -> 9/10

전체 상태와 속성별 상태를 분리하고, 미등록 예측에서는 단일 중심값보다 예측 범위를 우선한다. 정확 일치 DB 측정값은 측정값을 우선하고 범위가 없음을 명시한다.

### Desktop wireframe

```text
+-----------------------------------------------------------------------+
| 입력 조성 스냅샷 · 요청 상태 · [다시 분석]                            |
+-----------------------------------------------------------------------+
| 사용 가능 수준: 잠정 참고만                                           |
| 유사 데이터가 적어 생산 조건 확정에는 사용할 수 없습니다.             |
+----------------------------------------+------------------------------+
| 핵심 예측 (약 60%)                     | 근거·사용 범위 (약 40%)      |
| 속성     예측 범위    중심   사용 수준 | 예측 방식 / 유사 합금 3개   |
| 고상선   151–166°C    159    검토 가능 | 홀드아웃 MAE / 외삽 위험     |
| 액상선   191–208°C    200    잠정 참고 | 모델·DB 버전 / 상세 보기     |
| 인장     62–75 MPa    69.8   잠정 참고 |                              |
+----------------------------------------+------------------------------+
| 다음 행동: [조성 수정] [유사 합금 보기] [실험 검증 항목 확인]         |
+-----------------------------------------------------------------------+
| 공정 참고: 생산 권고 보류 · 연구용 예상 범위만 표시                   |
+-----------------------------------------------------------------------+
| AI 설명: 독립 영역 · 생성 중/실패/완료가 위 영역 높이를 바꾸지 않음    |
+-----------------------------------------------------------------------+
```

### Mobile wireframe (<=720px)

```text
[사용 수준 상태 띠 — 접지 않음]
[액상선 191–208°C / 중심 200 / 잠정 참고]
[고상선 151–166°C / 중심 159 / 검토 가능]
[인장 62–75 MPa / 중심 69.8 / 잠정 참고]
[왜 이런 판정인가 — 핵심 사유 1줄]
[다음 행동 44px 세로 버튼]
[근거 상세 — 펼치기]
[공정 참고]
[AI 설명 — 독립 부분 상태]
```

화면에서 세 가지만 남겨야 한다면 `사용 가능 수준`, `핵심 범위`, `다음 행동`을 남긴다.

## Pass 2. Interaction State Coverage — 4/10 -> 9/10

| Feature/state | Loading | Empty | Error | Success | Partial/refusal |
|---|---|---|---|---|---|
| 조성 입력 | 해당 없음 | 입력 예시와 합계 조건 | 필드 근처 원인 + 첫 오류 포커스 | 정규화 합계 표시 | 미지원 원소는 분석 중단 |
| 핵심 분석 | 조성 스냅샷 + `핵심 예측 계산 중`, 취소 가능 | 결과 대신 분석 가능 범위 안내 | 입력 보존, 문제·원인·해결 표시 | 상태 띠와 속성 행 즉시 표시 | 속성별 성공/보류를 같은 행에 표시 |
| 재분석 | 이전 결과에 `이전 조성 결과` 표시, 새 결과와 혼합 금지 | 해당 없음 | 이전 결과를 복구하되 조성 라벨 유지 | 새 request ID에서만 교체 | 취소 시 입력과 이전 결과 유지 |
| AI 설명 | 고정 높이 영역에 AI만 스켈레톤 | 로컬 설명 표시 | 핵심 유지 + `AI 설명만 다시 시도` | 출처와 완료 상태 표시 | 시간초과/할당량 사유 표시 |
| 공정 참고 | 핵심 완료까지 비활성 | 핵심값 없음 안내 | 규칙 충돌 사유 | 확정 또는 잠정 수준 표시 | 판단 보류면 생산 피크 미생성 |
| 유사 합금 | 근거 영역만 로딩 | `가까운 등록 합금이 없음` + 의미 설명 | 근거 조회 재시도 | 3개 요약, 상세 펼치기 | 한계가 크면 외삽 위험을 상향 |
| 비교 분석 | A/B 자리 유지 | 각 조성 입력 안내 | 실패한 쪽에 이유 유지 | 동일 속성 행 정렬 | 비교 불가는 `—` 대신 이유 표시 |

상태는 직렬 상태 하나가 아니라 `core: idle|loading|success|error`와 `ai: idle|loading|success|error|disabled`의 독립 축으로 관리한다. `refused`는 성공 응답 안의 사용 수준이지 네트워크 오류가 아니다.

## Pass 3. User Journey & Emotional Arc — 4/10 -> 9/10

| Step | User does | Expected feeling | UI support |
|---|---|---|---|
| 1 | 미등록 조성 입력 | 이 조성도 분석 가능한지 불안 | 지원 범위·합계·미등록 예측 설명 |
| 2 | 분석 실행 | 오래 걸리거나 틀릴까 걱정 | 핵심/AI 단계를 분리해 현재 단계 표시 |
| 3 | 핵심 결과 확인 | 숫자를 얼마나 믿을지 판단 | 사용 수준과 예측 범위를 먼저 표시 |
| 4 | 근거 확인 | 검증 가능성을 찾음 | 유사 합금, 홀드아웃 오차, 외삽 사유 |
| 5 | 공정 사용 여부 결정 | 행동의 책임 경계를 원함 | 확정/잠정/보류와 다음 행동 |
| 6 | AI 설명 확인 | 추가 해석을 원함 | 수치와 분리된 선택적 설명 |

- 5초: 사용 가능 수준과 액상선 범위를 이해한다.
- 5분: 유사 합금과 오차를 검토해 실험 후보인지 판단한다.
- 장기: 보고서의 모델/DB 버전과 근거로 과거 판단을 재현한다.

## Pass 4. AI Slop Risk — 6/10 -> 9/10

분류는 **APP UI**다. 기존 수치 카드 모자이크 위에 배지를 더 쌓지 않는다. 속성은 행 기반의 한 읽기 단위로, 근거는 우측/접힌 상세로, AI는 별도 보고서 영역으로 둔다. 보라색 장식 그라데이션·아이콘 원·반복 카드·장식 그림자·작은 저대비 설명을 새로 추가하지 않는다. 핵심 카피는 다음처럼 고정한다.

- `검토 가능`: 등록 데이터와 가까우며 연구 후보 선별에 사용할 수 있습니다.
- `잠정 참고만`: 예측 오차가 커 생산 조건 확정 전 실험 검증이 필요합니다.
- `판단 보류`: 적용 범위를 벗어나 생산용 권고를 생성하지 않았습니다.
- `AI 설명 생성 중`: 핵심 수치 예측은 완료되었습니다.

## Pass 5. Design System Alignment — 8/10 -> 10/10

- `--bg-page`, `--bg-elevated`, `--border-default`, `--text-primary`, `--text-secondary`, `--accent`를 그대로 사용한다.
- 상태는 기존 색을 보조로 쓰되 항상 제목과 문구를 함께 표시한다.
- `TactileButton`과 `CollapsibleSection`을 재사용한다.
- 새 결과 요약은 `PredictionEvidencePanel`과 `PropertyPredictionRow`로 분리하되 기존 앱 셸과 720px 규칙을 따른다.
- AI 영역 로딩은 핵심 영역의 위치를 이동시키지 않도록 최소 높이를 예약한다.

## Pass 6. Responsive & Accessibility — 2/10 -> 9/10

- 데스크톱: 결과/근거 60:40 2열, 공정·AI 영역은 전체 폭.
- 태블릿: 단일 열로 전환하되 속성 행은 3열(속성/범위/상태)을 유지한다.
- 모바일: 범위와 중심값을 한 행 두 줄로, 상태 띠와 판단 보류 사유는 접지 않는다.
- A/B 비교: 모바일에서 한 번에 한 조성을 보는 토글 + 동일 속성 순서, 비교 요약은 아래에 유지한다.
- 모든 버튼·토글은 최소 44x44px, 본문 대비 4.5:1 이상, 포커스 링을 유지한다.
- 상태 변화는 `aria-live="polite"`, 핵심 오류는 `role="alert"`; AI 완료는 포커스를 탈취하지 않는다.
- 입력 오류 메시지는 필드와 `aria-describedby`로 연결하고 첫 오류로 포커스를 이동한다.
- 상태는 색상만으로 전달하지 않으며, 접기 컨트롤은 `aria-expanded`를 사용한다.
- `prefers-reduced-motion`에서는 스켈레톤/전환 애니메이션을 줄인다.

## Pass 7. Resolved Design Decisions — 3/10 -> 9/10

| Decision | Auto-decision | Why |
|---|---|---|
| 전체와 속성별 상태 | 둘 다 제공, 전체는 선택 작업의 의존 속성으로 파생 | 무관한 속성의 보류가 다른 작업을 막지 않음 |
| 단일값 vs 범위 | 미등록은 범위 우선·중심값 보조, DB 정확 일치는 측정값 우선 | 과도한 정밀도 방지 |
| 판단 보류 | 생산 리플로우 권고 미생성, 연구용 범위와 다음 행동만 허용 | 경고와 처방의 동시 노출 방지 |
| 오차 기준 | 속성별 홀드아웃 집단과 표본 수를 상세에 표시 | `예상 오차`의 모호성 방지 |
| 출처 라벨 | 주 산출 방식 1개 + 보조 근거 목록 | 복합 근거를 숨기지 않으면서 위계 유지 |
| 부분 성공 | 속성/공정/AI가 독립 상태 | 핵심값 하나의 실패가 전체를 가리지 않음 |
| 이전 결과 | 입력 조성 스냅샷과 묶어 명확히 흐리며 새 결과 도착 후 교체 | 조성 혼동 방지 |
| 내보내기 | 상태·보류 사유·모델/DB 버전을 강제 포함 | 화면 밖에서도 신뢰 경계 보존 |
| 전문가 상세 | 기본은 해석된 결론, 상세는 거리·표본·모델 불일치 | 인지 부하와 투명성 균형 |
| 시각 취향 | 기존 다크 시스템 유지, 새 장식 스타일 없음 | 기능 고도화 범위에 집중 |

## Design Completion Summary

| Dimension | Before | After | Remaining |
|---|---:|---:|---|
| Information architecture | 5 | 9 | 실제 시안 검증 |
| Interaction states | 4 | 9 | 브라우저 구현 확인 |
| User journey | 4 | 9 | 사용자 관찰 데이터 |
| AI slop resistance | 6 | 9 | 기존 카드 모자이크 정리 범위 |
| Design system | 8 | 10 | 없음 |
| Responsive/accessibility | 2 | 9 | 자동/수동 접근성 QA |
| Decisions resolved | 3 | 9 | 시안 키 미설정으로 시각 비교 미수행 |

**Phase 2 complete.** Codex: 10 concerns. Independent subagent: 10 issues. Consensus: 7/7 litmus checks confirmed, 0 unresolved disagreements. Passing to Phase 3.

---

# Phase 3 — Engineering Review

## Step 0. Scope challenge and actual-code map

실제 코드를 기준으로 계획을 다시 잠갔다.

- `alloy_property_inference.py`는 3-NN IDW 기준값에 질의-이웃 조성 차이만 릿지 보정하지만, 예측 오차·적용 범위·판단 보류가 없다.
- 정확 일치 200°C 회귀는 있으나 `test_alloy_property_inference.py`의 한 조성만 보호한다.
- `analyzer.py::analyze_all`은 핵심 계산 뒤 원격 AI까지 동기 실행한다.
- `api_server.py::analyze`는 `async def` 안에서 동기 CPU/네트워크 작업을 직접 호출하며 전역 `usage_stats`의 전후 차이로 요청별 AI 사용을 추정한다.
- `/api/compare`는 A와 B의 `analyze_all`을 순차 실행해 AI도 최대 두 번 호출한다.
- `frontend/src/api.js`는 모든 POST의 502/503/504를 자동 재시도한다. AI 분리 후 그대로 쓰면 중복 비용이 발생한다.
- `App.jsx::handleAnalyze`는 AbortController와 요청 ID 없이 전체 결과를 한 번에 교체한다.
- `api_server.py`는 `.env` 외 레거시 키 파일도 읽는다. 사용자 정책에 맞춰 제거 대상이다.

복잡도 판정: API·도메인 계약·평가·React 상태가 모두 바뀌므로 단순 라벨 패치가 아니다. 기능을 한꺼번에 숨은 임계값으로 구현하지 않고 계약 -> 평가 -> UI -> AI 분리 순서로 진행한다.

## Eng dual voices

### CLAUDE SUBAGENT — independent architecture review

- Critical: 조성/합금족 그룹 홀드아웃이 아니면 유사 행 데이터 누수로 성능이 과대평가됨.
- Critical: 공개 AI 엔드포인트는 인증 없는 비용 공격면이며 멱등성과 동시성 제한이 필요함.
- High: 서버가 클라이언트 수치 스냅샷을 신뢰하면 안 되고 버전형 핵심 계약을 재생성·검증해야 함.
- High: 전역 AI 사용 통계와 동기 `async` 경로가 동시 요청에서 오귀속·이벤트 루프 차단을 일으킬 수 있음.

### CODEX SAYS — architecture challenge

- 예측 범위의 통계적 의미와 실제 포함률이 정의되지 않으면 신뢰 UI가 검증되지 않음.
- OOD 신호 목록을 서버 상태 머신과 버전형 정책으로 고정해야 함.
- 정확 일치 DB 자체가 모순될 때 원본을 자동 수정하지 말고 데이터 품질 오류로 파생 권고를 거부해야 함.
- 전체 상태를 단순 최저값으로 합치지 말고 리플로우·물성 판단별 의존성으로 파생해야 함.

### ENG DUAL VOICES — CONSENSUS TABLE

| Dimension | Subagent | Codex | Consensus |
|---|---|---|---|
| Architecture sound? | 핵심 계약/AI 수명주기 부족 | 정책 상태 머신 부족 | CONFIRMED — 수정 필요 |
| Test coverage sufficient? | 그룹 홀드아웃 부재 | 누수·coverage 부재 | CONFIRMED |
| Performance risks addressed? | 동기 async/공유 상태 | SLO 경계 불명 | CONFIRMED |
| Security threats covered? | AI 비용 공격·로그 기밀 | 공개 재시도 엔드포인트 | CONFIRMED |
| Error paths handled? | 판단 보류 임계값 불명 | 데이터 품질 충돌 불명 | CONFIRMED |
| Deployment risk manageable? | 버전/TTL/멱등성 필요 | 호환 행렬 필요 | CONFIRMED |

## Section 1. Architecture

### Dependency graph

```text
React App
  └─ useAnalysisRun (request ID, AbortController, independent core/AI state)
       ├─ POST /api/v1/analyses
       │    └─ CoreAnalysisService (threadpool boundary)
       │         ├─ CompositionNormalizer
       │         ├─ existing AlloyAnalyzer numeric stages
       │         ├─ PredictionPolicy v1
       │         │    ├─ ValidationCalibration artifact
       │         │    └─ exact/in-domain/weak/OOD/data-quality states
       │         └─ AnalysisCoreResponse v1
       │              ├─ property evidence contract
       │              └─ process decision contract
       └─ POST /api/v1/analyses/{analysis_id}/explanations
            ├─ validate analysis_id against recomputed core input/version
            ├─ idempotency + concurrency/rate budget
            ├─ existing AI cache/engine
            └─ AIExplanationResponse v1 (same analysis_id)

Offline/CI
  └─ prediction_validation.py
       ├─ deduplicate + family/near-composition groups
       ├─ group holdout with no neighbor/training leakage
       ├─ nearest/family-mean baselines
       └─ versioned calibration/report JSON
```

기존 `/api/analyze`와 `/api/compare`는 먼저 유지한다. 새 웹 흐름은 `POST /api/v1/analyses`를 사용하고, AI 요청은 `POST /api/v1/analyses/{analysis_id}/explanations`에 **원래 조성 + core가 발급한 단기 explanation token**만 보낸다. 서버는 핵심 결과를 재계산해 ID/버전을 검증하므로 클라이언트가 보낸 수치를 신뢰하거나 인메모리 스냅샷에 의존하지 않는다. 분석 리소스는 서버에 영구 저장되지 않음을 문서화한다.

핵심 계산은 동기 FastAPI 핸들러 또는 `run_in_threadpool` 경계에서 실행한다. AI는 별도 동시성 상한을 사용해 포화되어도 핵심 API를 막지 않는다.

### Versioned result contract

```text
AnalysisCoreResult v1
  analysis_id              # 정규화 조성 + 계약/코드/DB/모델/정책 버전의 결정적 ID
  request_id               # 화면 요청 상관관계용 임의 ID, 로그에 원조성 미기록
  composition              # 응답/보고서용 정규화 wt%, 로그 제외
  versions
    contract, code, db_fingerprint, melting_engine, inference_policy, calibration
  properties
    solidus | liquidus | tensile
      point, unit
      interval {kind, coverage_target, lower, upper, sample_count, actual_coverage}
      method                # exact_db | idw_ridge | model | literature
      state                 # exact_match | in_domain | weak_support | out_of_domain | unavailable | data_quality_error
      usage_level           # reference | review | provisional | refused
      validation {mae, median_abs_error, p95_abs_error, cohort}
      evidence {nearest_rows, distance, source_ids}
      reason_codes[]
  decisions
    reflow {usage_level, recommended_peak|null, reference_range|null, reason_codes[]}
  timing {core_ms}
```

`confidence_overall`은 호환을 위해 남기되 `heuristic_support_score`로 설명하고 새 UI의 검증 정확도로 사용하지 않는다.

### Input normalization contract

- API 단위는 wt%만 허용한다. at%는 명시적으로 거부한다.
- 원소 기호를 표준화하고 중복 키는 합산하며 0 항목은 거리/해시에서 제거한다.
- 모든 값은 유한수·0 이상이어야 한다. `NaN`, `Infinity`, 음수, 빈 원소는 거부한다.
- 표시 기준과 동일하게 소수 둘째 자리 합계가 100.00일 때만 분석한다. API에서 묵시적 Sn 보정이나 비율 스케일을 하지 않는다.
- 정확 일치, 거리, 캐시, analysis_id는 동일한 정규화 조성을 사용한다.
- 정확 일치 허용오차와 조성 거리 가중치는 정책 버전에 포함한다.

### Prediction state/refusal policy v1

| State | Server evidence | Numeric output | Process decision |
|---|---|---|---|
| `exact_match` | DB 거리 <= exact epsilon, 데이터 품질 통과 | 원본 DB 등록값, 보정 금지 | `reference`; 생산 승인값으로 표현하지 않음 |
| `in_domain` | 알려진 합금족, 그룹 홀드아웃 표본 충분, 최근접 거리가 해당 집단 q90 이내 | 중심 + 보정된 경험적 90% 구간 | 액상선 구간과 사용자 공정 제약이 있으면 `review` |
| `weak_support` | q90 초과 q99 이하, 전역 구간 폴백, 모델 불일치 큼 중 하나 | 중심 + 넓은 잠정 범위 | `provisional`, 생산 피크 확정 금지 |
| `out_of_domain` | 거리 q99 초과, 지원 데이터 없는 원소축, 다중 위험 신호 | 연구용 중심/범위는 근거가 있을 때만 | `refused`, 생산 권고 없음 |
| `unavailable` | 유효 이웃/모델/문헌 없음 | null | `refused` |
| `data_quality_error` | exact DB 속성 모순, 단위/출처 충돌 | 원본은 근거 상세에만 보존 | 관련 파생 권고 거부 |

초기 예측 구간은 **그룹 홀드아웃 절대 잔차의 경험적 90% 구간**으로 명시한다. 합금족 표본이 최소 8개 미만이면 전역 구간을 `global_fallback`으로 표시하고 최대 `provisional`만 허용한다. 실제 포함률과 표본 수를 함께 표시하며 MAE를 구간으로 오인하지 않는다. 물리 범위로 구간을 자르면 `interval_clipped`를 기록한다.

리플로우 의존성은 `solidus + liquidus + 사용자 장비/부품 제약`이다. 제약 입력이 없으면 `일반 참고 프로파일`만 제공하고 생산용 확정 표현을 하지 않는다. 인장강도 보류는 리플로우 상태를 자동으로 낮추지 않는다.

## Section 2. Code Quality

- `analyze_all`을 `analyze_core`와 `enrich_with_ai` 경계로 나누되 기존 래퍼를 유지해 GUI/구 API 회귀를 줄인다.
- 출처·상태·거부 사유 문자열은 `prediction_contract.py` 상수/열거형 한 곳에서 정의한다.
- 평가 로직을 런타임 UI 코드와 섞지 않고 `prediction_validation.py`에 둔다.
- `App.jsx`에 상태를 더 쌓지 않고 `useAnalysisRun.js`, `PredictionEvidencePanel.jsx`, `PropertyPredictionRow.jsx`로 추출한다.
- 요청별 AI 정보는 누적 `usage_stats` 차이로 추론하지 않고 해당 호출 반환값에 포함한다.
- `.gemini_api_key`와 `gemini_api_key.txt` 로딩을 제거하고 `.env`/배포 환경변수만 사용한다.
- 조성 또는 일반 해시를 운영 로그에 남기지 않는다. 필요한 상관관계는 임의 `request_id`만 사용한다.

## Section 3. Test Review — full diagram

```text
INPUT
 ├─ finite wt% + exact 100.00 ──> normalize/hash/version test
 ├─ duplicate/case/zero ────────> canonicalization test
 └─ invalid/unsupported ────────> 422 + focus/error UI test

PREDICTION
 ├─ exact DB ───────────────────> multi-anchor preservation + data-quality conflict
 ├─ in-domain unseen ───────────> group holdout no-leak + interval coverage
 ├─ weak support ───────────────> provisional + no production peak
 ├─ OOD/unavailable ────────────> refusal + null production recommendation
 └─ property partial success ───> independent status/dependency tests

REQUESTS
 ├─ core success ───────────────> immediate render
 ├─ core success + AI success ──> matching analysis_id only
 ├─ AI timeout/quota/bad JSON ──> core preserved + retry AI only
 ├─ duplicate AI POST ──────────> idempotent single provider attempt
 ├─ rapid re-analysis/cancel ───> late response discarded
 └─ A/B partial/version mismatch > explicit comparison refusal/reason

OUTPUT
 ├─ desktop/mobile hierarchy ───> component + browser assertions
 ├─ refusal export/report ──────> reason/version preserved
 └─ a11y ───────────────────────> keyboard, aria-live, alert, 44px/contrast audit
```

| Codepath/branch | Existing coverage | Required decision |
|---|---|---|
| 3-NN prediction basic result | 단위 스모크 있음 | 유지 |
| exact DB 159/200/225 | 단일 회귀 있음 | 다중 합금족 앵커 추가 |
| group holdout leakage | 없음 | 새 평가 테스트 필수 |
| calibrated interval/coverage | 없음 | 새 단위+스냅샷 필수 |
| OOD/refusal policy | 휴리스틱 일부 | 정책 테이블 매개변수 테스트 필수 |
| NaN/Infinity/100.00 boundary | 일부 합계 검증 | 유한수/경계 API 테스트 추가 |
| request-local AI telemetry | 없음 | 동시 요청 테스트 추가 |
| core/AI independent endpoints | 없음 | FastAPI 계약 테스트 추가 |
| POST retry/idempotency | 일반 fetch 재시도 테스트 | AI 무자동재시도/중복 테스트 추가 |
| React partial states | import/포맷 중심 | 실제 fetch 상태 전이 테스트 추가 |
| compare A/B partial failure | 없음 | API/UI 테스트 추가 |
| old/new deploy compatibility | 없음 | 응답 필드 누락/구 API 회귀 추가 |

테스트 계획 산출물: `~/.gstack/projects/Ttime-taek-alloy-analyzer/ttime-master-test-plan-20260722-085536.md`.

## Section 4. Performance

- 핵심 SLO는 브라우저 분석 클릭부터 첫 유효 핵심 결과 렌더까지 측정한다.
- cold start와 warm, 캐시 hit/miss를 분리하고 각 시나리오 최소 20회 측정한다.
- 동시 1/5/10 핵심 요청과 AI 포화 중 핵심 요청을 측정한다.
- 홀드아웃 평가는 요청 경로에서 실행하지 않고 버전된 산출물만 런타임이 읽는다.
- A/B 핵심 계산은 같은 버전 계약으로 수행하고 AI 비교 설명은 한 번만 선택적으로 생성한다.
- 목표: warm core p50 <=3s, p95 <=8s, AI 포화 중 core 오류율 0%; cold start는 별도 보고한다.

## Security, deployment, and failure registry

| Risk/failure | Severity | Control |
|---|---|---|
| 공개 AI 비용 증폭 | Critical | core 발급 analysis_id 검증, ID별 멱등성, 전역 동시성 상한, 분당 예산, Origin 허용 목록 |
| 클라이언트 수치 변조 | High | AI endpoint가 숫자를 받지 않고 원 조성으로 core를 재계산 |
| API 키 유출 | Critical | `.env`/배포 환경만 사용, 응답/로그/번들 금지, 레거시 키 파일 로더 제거 |
| 요청 간 AI 상태 혼입 | High | 요청별 telemetry 반환, 누적 통계는 운영 지표로만 사용 |
| 이벤트 루프 차단 | High | core/AI 동기 작업을 threadpool 경계로 이동, AI 동시성 분리 |
| AI POST 중복 재시도 | High | AI fetch 자동재시도 비활성, 서버 idempotency |
| 조성 기밀 역추정 | High | 원조성/일반 해시 로그 금지, 임의 request ID만 로그 |
| 데이터 누수 평가 | Critical | 그룹 분할, 전처리/이웃/보정에서 held-out 그룹 완전 제외 |
| DB 원본 모순 | High | 자동 교정 금지, data_quality_error와 파생 권고 거부 |
| Vercel/Render 배포 시차 | Medium | 새 필드 하위 호환, 구 endpoint 유지, 양방향 호환 테스트 |

배포 순서는 `계약·평가 코드 -> 새 core API -> 최소 안전 UI -> AI 분리 -> 전체 UI`다. 새 프론트는 새 API가 없으면 기존 단일 호출로 폴백하되 판단 보류 필드를 모르는 구 프론트가 새 정책 결과를 확정값으로 렌더하지 않도록 기존 endpoint의 의미는 배포 중 바꾸지 않는다.

## What already exists

- 기존 추론 엔진, DB fingerprint, AI cache, 신호별 `melting_detail`, 유사 이웃, API 유효성 검사, React API 오프라인 처리와 디자인 토큰을 재사용한다.
- 이번 변경은 새 모델을 발명하기보다 기존 예측의 **검증·상태·출처 계약**을 만든다.

## NOT in scope

- 평가 결과를 보지 않은 모델 재훈련과 새 ML 프레임워크 도입.
- 분산 작업 큐/Redis 신규 인프라. 현 단일 Render 배포에 맞는 멱등 캐시·동시성 상한을 먼저 둔다.
- 사용자 계정·조직별 권한 시스템. 공개 배포의 최소 비용 보호만 포함한다.
- 상용 CALPHAD 교차검증과 실험 장비 자동 수집.
- 목표 물성 역설계와 Pareto 탐색.

## Eng Decision Audit Trail

| Finding | Decision | Principle |
|---|---|---|
| 한 행 leave-one-out 누수 | 합금족+근접 조성 그룹 홀드아웃 | 완전성 |
| 예측 범위 의미 없음 | 경험적 90% 잔차 구간 + 실제 coverage | 명시적 계약 |
| OOD 임계값 임의성 | 검증 분포 q90/q99 + 정책 버전 | 재현성 |
| AI snapshot 저장 복잡도 | 서버 재계산 + analysis_id 검증 | 단순성 |
| CPU/AI 이벤트 루프 차단 | threadpool + 분리 동시성 | 운영 안전 |
| 인장 보류가 리플로우까지 차단 | 의사결정별 의존성 | 사용자 과업 일치 |
| Redis/분산 큐 | 이번에는 도입하지 않음 | 범위 통제 |

## Engineering Completion Summary

| Area | Status | Output |
|---|---|---|
| Scope/code map | Complete | 실제 결합·공유 상태·재시도 위험 확인 |
| Architecture | Complete | 버전형 core 계약 + 서버 재계산 AI 경계 |
| Prediction policy | Complete | 6상태, 4 사용 수준, 리플로우 의존성 |
| Evaluation | Complete | 그룹 홀드아웃·90% 구간·coverage 규칙 |
| Code quality | Complete | Python/React 분리 단위 지정 |
| Tests | Complete | 모든 새 UX/data/code branch 매핑 |
| Performance | Complete | warm/cold/concurrency 경계 지정 |
| Security/deploy | Complete | 비용·키·기밀·호환 통제 |
| Deferred scope | Complete | 재훈련/분산 큐/역설계 분리 |

**Phase 3 complete.** Codex: 17 concerns. Independent subagent: 10 issues. Consensus: 6/6 confirmed, 0 unresolved disagreements. Passing to Phase 3.5.

---

# Phase 3.5 — Developer Experience Review

## Step 0. DX scope and persona

- Product type: web application with a public FastAPI integration surface and offline validation tooling.
- Primary developer persona: an internal process/research engineer or application developer who can run Python/Node but should not need to read model internals.
- Current DX completeness: **4/10**.
- Current TTHW (time to first successful unseen-composition core response): **10+ minutes or indeterminate**, because there is no root `README.md`, cross-platform quickstart, or copy-paste API call.
- Target TTHW: **<=5 minutes**, with the core path requiring no AI key.

## DX dual voices

### CLAUDE SUBAGENT — independent DX review

- Critical: no root README and no complete first-run path; existing docs stop before the first API request.
- Critical: errors are not a stable machine-readable contract with problem, cause, fix, link, and retryability.
- High: API naming/lifetime, evidence detail, policy escape hatches, and legacy migration are unspecified.

### CODEX SAYS — developer experience challenge

- The plan defines internals but not a five-minute first success, actual JSON, OpenAPI examples, or a one-command validation run.
- `core/explain` verb-layer naming is less discoverable than versioned analysis resources.
- `refused` is a successful domain result, so docs must show it alongside exact and in-domain examples.
- Deployment ordering is not a public deprecation policy; compatibility, headers, enum growth, and field removal rules are needed.

### DX DUAL VOICES — CONSENSUS TABLE

| Dimension | Subagent | Codex | Consensus |
|---|---|---|---|
| Getting started <5 min? | No, 10+ min | No, indeterminate | CONFIRMED |
| API/CLI naming guessable? | Lifecycle unclear | resource/version unclear | CONFIRMED |
| Error messages actionable? | no stable schema | FastAPI detail leaks | CONFIRMED |
| Docs findable & complete? | README absent | examples/IA absent | CONFIRMED |
| Upgrade path safe? | migration missing | deprecation contract missing | CONFIRMED |
| Dev environment friction-free? | Windows-only shortcut | cross-platform path absent | CONFIRMED |

## 9-stage developer journey

| Stage | Developer goal | Current friction | Planned experience |
|---|---|---|---|
| 1. Discover | understand what the repo does | no README | one-sentence value and safety boundary at README top |
| 2. Evaluate | see supported input/output | must read source | exact/unseen/refused examples and `/api/v1/capabilities` |
| 3. Install | prepare Python/Node | multiple files/scripts | OS-specific 3-step quickstart and one setup script per OS |
| 4. Configure | decide whether keys are required | key path unclear | core works without keys; AI keys only in `.env`/deployment env |
| 5. First run | start API and UI | command path fragmented | `scripts/dev.sh` or `start_all.bat`, health confirmation |
| 6. First success | analyze unseen composition | no curl example | copy-paste request with expected usage/range fields |
| 7. Integrate/debug | handle refusal/errors | string `detail` only | stable error codes, fix text, docs link, request ID |
| 8. Validate/extend | reproduce model report | evaluator not defined | one deterministic validation command and artifact schema |
| 9. Upgrade | move from legacy API | no mapping/sunset policy | v0->v1 guide, deprecation headers, compatibility tests |

## Developer empathy narrative

> 저장소를 처음 연 나는 모델 구현보다 먼저 “어떤 Python을 설치하고, AI 키 없이도 실행되는지, wt%를 96.5로 보내는지 0.965로 보내는지”를 알고 싶다. 첫 요청이 거부되면 서버 장애인지 안전한 판단 보류인지 구분하고 싶고, 오류가 나면 소스 검색 없이 무엇을 고쳐야 하는지 알고 싶다. 모델을 바꿀 때는 같은 DB·정책 버전으로 검증 보고서를 다시 만들어 결과가 좋아졌는지 확인하고 싶다. 이 모든 경로가 README와 OpenAPI에서 이어져야 이 API를 믿고 통합할 수 있다.

## Pass 1. Getting Started — 2/10 -> 9/10

루트 `README.md` 상단에 다음 순서를 둔다.

1. 제품 목적과 `연구/공정 의사결정 보조이며 생산 승인값이 아님`을 한 문단으로 설명한다.
2. Python/Node 요구 버전과 Mac/Linux, Windows 설치 명령을 분리한다.
3. AI 키 없이 core API를 실행하고 `/api/about`과 미등록 조성 curl을 호출한다.
4. UI 실행, API 문서, 검증 보고서, 배포 문서 링크를 제공한다.

Unix 계열은 `scripts/dev.sh`, Windows는 기존 `scripts/setup_dev_env.ps1` + `start_all.bat`을 공식 경로로 둔다. 깨끗한 환경에서 README만 보고 5분 안에 첫 core 응답을 얻는 테스트를 완료 기준에 추가한다.

## Pass 2. API/CLI Design — 4/10 -> 9/10

### Public API v1

```text
POST /api/v1/analyses
POST /api/v1/analyses/{analysis_id}/explanations
GET  /api/v1/capabilities
GET  /api/v1/models
```

첫 요청은 핵심 결과만 반환하고 AI explanation은 명시적 선택 호출이다. 요청은 `composition`, `basis: weight_percent`, `normalization: strict`, `mode`를 사용한다. 응답 기본 필드는 point/range/usage/method이고 검증 통계와 근거는 `evidence`에 계층화한다.

`analysis_id`는 논리적 분석/버전 결합 ID이고 서버 영구 저장을 뜻하지 않는다. core는 별도의 서명된 `explanation_token`을 발급하며 기본 TTL은 10분이다. 토큰 만료/버전 변경은 410/409로 구분한다. 동일 analysis ID·mode의 explanation은 멱등 처리한다.

`GET /api/v1/capabilities`는 지원 basis, 원소, 입력 한계, 정책/계약 버전, AI 활성 여부를 제공한다. 오프라인 검증은 `python -m prediction_validation --output ...` 한 명령을 공식화하고 종료 코드와 산출물 스키마를 문서화한다. 전체 사용자용 CLI는 이번 범위에서 만들지 않는다.

## Pass 3. Error Messages & Debugging — 2/10 -> 9/10

```json
{
  "error": {
    "code": "COMPOSITION_TOTAL_INVALID",
    "message": "조성 합계가 99.70 wt%입니다.",
    "cause": "strict 모드에서는 합계가 100.00 wt%여야 합니다.",
    "fix": "원소 함량을 조정한 뒤 다시 요청하세요.",
    "field": "/composition",
    "actual": 99.70,
    "expected": 100.00,
    "retryable": false,
    "docs_url": "/docs/errors#COMPOSITION_TOTAL_INVALID"
  },
  "request_id": "..."
}
```

- 422: 입력/합계/원소 오류
- 409: analysis/model/DB/policy 버전 충돌
- 410: explanation token 만료
- 429: AI 예산/속도 제한, `Retry-After` 포함
- 503: 일시적 AI provider 장애; core 결과는 별도 유지

모든 오류는 문제·원인·해결·문서 링크·재시도 가능 여부를 가진다. `reason_codes`는 공개 enum 카탈로그와 계약 테스트를 둔다. FastAPI 기본 validation 형식은 공용 오류 모델로 변환한다.

## Pass 4. Documentation & Learning — 1/10 -> 9/10

```text
README Quickstart
  -> Concepts: exact / in-domain / weak / OOD / refused
  -> Tutorial: first unseen analysis, optional AI explanation
  -> API reference: OpenAPI /docs + schemas/examples
  -> Validation: grouped holdout report and reproduction
  -> Troubleshooting: error-code catalog
  -> Migration: legacy /api/analyze to /api/v1/analyses
  -> Deployment: DEPLOYMENT.md
```

curl, Python, JavaScript로 exact, supported unseen, refused의 세 예제를 제공한다. OpenAPI에는 성공·부분 성공·refused·오류 응답 예제를 넣고 문서 예제는 테스트에서 실제 호출/스키마 검증한다.

## Pass 5. Upgrade & Migration — 5/10 -> 9/10

- 기존 `/api/analyze`는 최소 한 안정 배포 주기 동안 유지한다.
- v0 응답 의미는 배포 중 바꾸지 않고 `Deprecation`, `Link` 헤더로 v1 가이드를 알린다. 실제 종료일이 정해질 때만 `Sunset`을 보낸다.
- `confidence_overall`은 값을 바꾸지 않고 deprecated 처리하며 새 `heuristic_support_score`를 별도 제공한다. 제거는 다음 major API에서만 한다.
- additive field와 enum 확장은 허용하되 클라이언트는 알 수 없는 enum을 `unknown`으로 처리하도록 문서화한다.
- 새 프론트에서 v1 안전 계약이 없으면 구 API로 조용히 폴백하지 않고 `안전 계약을 사용할 수 없어 분석 보류`를 표시한다.
- v0/v1 필드 매핑과 Vercel/Render 선후 배포 양방향 계약 테스트를 둔다.

## Pass 6. Developer Environment & Tooling — 5/10 -> 9/10

- `.venv`와 requirements 파일, bundled Node 사용법을 README에서 한 경로로 설명한다.
- `scripts/dev.sh`와 Windows 스크립트가 API/UI 기동 전 의존성과 포트를 확인하고 문제·원인·수정 명령을 출력한다.
- API 키는 `.env`와 배포 환경에서만 읽는다. `.gemini_api_key`/텍스트 키 파일 지원을 제거한다.
- `python -m prediction_validation` 결과는 결정적 JSON/Markdown을 만들며 CI가 기준선 악화를 검사한다.
- formatter/lint/test/build 명령을 OS별로 복사 가능하게 제공한다.

## Pass 7. Community & Ecosystem — 2/10 -> 7/10

대규모 커뮤니티 기능은 범위 밖이다. 대신 버그 보고 템플릿에 조성 원문을 공개하지 말라는 안내, request ID, 계약/모델/DB/정책 버전, error code를 받는다. 보안/키 유출은 공개 이슈가 아닌 비공개 신고 경로를 문서화한다. API 예제와 validation artifact가 외부 확장의 최소 생태계 표면이 된다.

## Pass 8. DX Measurement & Feedback — 2/10 -> 8/10

- 깨끗한 Mac/Linux 및 Windows 환경에서 TTHW를 측정하고 목표 <=5분을 CI/릴리스 체크리스트에 기록한다.
- Quickstart 명령, curl 예제, OpenAPI example을 자동 검증한다.
- 지원 문의/QA에서 error code별 빈도를 집계하되 원조성은 기록하지 않는다.
- deprecated endpoint 사용량, AI 429/503, v1 refused 처리 오류를 관측한다.
- 개발자가 문서를 2분 안에 찾고 exact/unseen/refused 차이를 설명할 수 있는지 릴리스 전 점검한다.

## DX Scorecard

| Dimension | Before | After target |
|---|---:|---:|
| Getting started | 2 | 9 |
| API/CLI ergonomics | 4 | 9 |
| Errors/debugging | 2 | 9 |
| Documentation/learning | 1 | 9 |
| Upgrade/migration | 5 | 9 |
| Environment/tooling | 5 | 9 |
| Community/ecosystem | 2 | 7 |
| Measurement/feedback | 2 | 8 |
| **Overall** | **2.9** | **8.6** |

## DX Implementation Checklist

- [ ] Root README with <=5 minute AI-key-free core quickstart
- [ ] Cross-platform dev/start commands and requirements table
- [ ] Versioned resource API and capabilities endpoint
- [ ] Actual exact/unseen/refused request-response examples
- [ ] Stable error envelope and public error-code catalog
- [ ] OpenAPI success/partial/refused/error examples
- [ ] One-command grouped validation report
- [ ] v0->v1 field map, deprecation headers, compatibility matrix
- [ ] Policy override documentation with immutable safety rules
- [ ] Documentation example tests and measured TTHW
- [ ] `.env`-only key loading and secret-redaction checks

**Phase 3.5 complete.** DX overall: 2.9/10 -> target 8.6/10. TTHW: 10+ min -> <=5 min. Codex: 7 major concerns. Independent subagent: 7 issues. Consensus: 6/6 confirmed, 0 unresolved disagreements. Passing to Phase 4.

---

# Cross-phase themes

1. **Uncertainty must control actions, not decorate numbers.** CEO, Design, and Eng independently required verified ranges, OOD detection, and refusal that disables production recommendations.
2. **AI is optional enrichment.** CEO, Design, Eng, and DX agreed numeric core must work without provider latency, quota, or keys.
3. **Traceability is the competitive advantage.** CEO and Eng required model/DB/policy/version evidence; Design and DX required it to survive UI, exports, and API use.
4. **The current confidence percentage is not validated accuracy.** CEO and Eng flagged the heuristic blend; Design/DX require range and usage language instead.
5. **Data and request boundaries must be explicit.** Eng/DX agreed on group holdout, request-local telemetry, versioned contracts, structured errors, and safe migration.

# AUTONOMOUS DECISION LOG

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---:|---|---|---|---|---|---|
| 1 | CEO | 미등록 조성 검증을 P1로 승격 | auto | completeness | 사용자 핵심 가치이며 두 외부 검토 합의 | 응답 속도만 개선 |
| 2 | CEO | 결정적 수치를 정답이 아닌 버전형 산출로 정의 | auto | explicitness | 재현성과 정확성을 분리 | 단일 정본 선언 |
| 3 | CEO | 재훈련 전 그룹 홀드아웃 감사를 수행 | auto | simplest complete path | 필요성을 먼저 증명 | 즉시 전체 재훈련 |
| 4 | Design | 사용 수준과 범위를 단일값보다 우선 | auto | user decision | 과도한 정밀도 방지 | 기존 KPI 카드에 배지만 추가 |
| 5 | Design | 판단 보류 시 생산 피크 미생성 | auto | safety | 경고와 처방 동시 노출 방지 | 경고 후 값 유지 |
| 6 | Design | 기존 다크 디자인 시스템 유지 | auto | alignment | DESIGN.md와 회귀 범위 준수 | 새 시각 테마 |
| 7 | Eng | 합금족+근접 조성 그룹 홀드아웃 | auto | completeness | 유사 행 데이터 누수 방지 | 단순 leave-one-row-out |
| 8 | Eng | 경험적 90% 잔차 구간과 실제 coverage 사용 | auto | measurable truth | MAE를 구간으로 오인하지 않음 | 임의 ±MAE |
| 9 | Eng | 서버 재계산 + analysis ID/token 검증 | auto | explicit simplicity | client 숫자 신뢰와 분산 저장 회피 | client snapshot 신뢰 |
| 10 | Eng | 속성별 상태와 작업별 의존성 | auto | task fit | 인장 보류가 리플로우를 불필요하게 막지 않음 | 단일 최저 상태 |
| 11 | DX | `/api/v1/analyses` 자원형 API | auto | consistency | 신규 개발자에게 의미와 버전이 명확 | `/api/analyze/core` |
| 12 | DX | 안정적 오류 envelope | auto | actionable errors | problem/cause/fix/docs/retry 제공 | `detail=str(e)` |
| 13 | DX | v1 부재 시 안전하지 않은 legacy 자동 폴백 금지 | auto | safety | OOD/refusal 계약 유실 방지 | 조용한 v0 폴백 |
| 14 | DX | README/문서 예제를 계약과 함께 구현 | auto | findability | TTHW <=5분 달성 | 마지막에 문서화 |

No unresolved taste decisions or user challenges remain. The original strategic challenge was resolved when the user confirmed that unseen-composition prediction is the key product requirement.
