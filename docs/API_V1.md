# API v1 예측 계약

## 핵심 분석

`POST /api/v1/analyses`

```json
{
  "comp": {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0},
  "mode": "eng",
  "literature_mode": "fast",
  "process_constraints": {
    "max_component_temp_c": 260,
    "oven_tolerance_c": 5
  }
}
```

응답은 `result`에 기존 UI 호환 수치를, `prediction_contract`에 검증 근거를 제공합니다. `analysis_id`는 정규화 조성, 분석·문헌 모드, 실제 젖음 온도, API·모델·DB·검증·정책 버전을 묶은 결정적 식별자입니다.

`overall_state`는 고상선·액상선·인장강도 중 가장 보수적인 판정이고, `melting_state`는 고상선·액상선만의 판정입니다. 전체 물성 중 인장 근거가 약해도 등록 융점값은 바뀌지 않으며, 리플로우 정책은 `melting_state`와 공정 제약을 따로 사용합니다.

각 물성은 다음 필드를 가집니다.

- `point`, `unit`: 중심 예측값
- `interval`: 그룹 홀드아웃 절대잔차로 계산한 경험적 90% 범위
- `method`: DB 직접값 또는 예측 경로
- `state`: `exact_match`, `in_domain`, `weak_support`, `out_of_domain`, `unavailable`, `data_quality_error`
- `usage`: `reference`, `review`, `provisional`, `refused`
- `validation`: 표본 수, MAE, 중앙 절대오차, p90/p95 절대오차, 실제 포함률
- `evidence`: 최근접 거리와 이웃 DB 행
- `reason_codes`: 기계 판독 가능한 판정 사유

리플로우는 `process_recommendation.allowed=false`이면 `recommended_peak_c=null`입니다. `reference_peak_c`는 비교 연구용 계산값일 뿐 생산 권장값이 아닙니다. 공정 제약이 없으면 항상 `production_ready=false`입니다.

## AI 설명

`POST /api/v1/analyses/{analysis_id}/explanations`

```json
{
  "analysis_id": "ana_...",
  "comp": {"Sn": 94.1, "Ag": 2.4, "Cu": 0.5, "Bi": 3.0},
  "mode": "eng",
  "literature_mode": "fast"
}
```

서버는 현재 조성·분석 모드·문헌 모드·젖음 온도와 모델·DB 버전으로 ID를 다시 계산합니다. 핵심 분석에서 `wetting_temp_c`를 지정했다면 설명 요청에도 같은 값을 보내야 합니다. 일치할 때만 `result_patch`에 AI 요약·출처·보고서를 반환합니다. AI 실패는 앞서 받은 핵심 수치의 유효성을 바꾸지 않습니다. 설명 요청은 비용·중복 생성을 막기 위해 클라이언트에서 자동 재시도하지 않으며, 서버에서도 IP별 호출량과 동시 실행 수를 제한합니다.

## 검증 방법

고상선·액상선은 같은 조성 또는 매우 가까운 변형을 한 그룹으로 묶어 함께 제외한 뒤 하이브리드 엔진으로 다시 예측합니다. 인장강도도 같은 방식으로 물성 DB 합금 그룹을 제외한 뒤 거리 가중 예측합니다. 인장 이웃은 합금명 중복을 제거하고, 최근접 거리 `d0`를 기준으로 상위 5개 중 `max(d0+0.25, 1.20×d0)` 안의 국소 후보만 사용합니다. 현재 26개 합금 그룹 홀드아웃의 MAE는 8.430 MPa, p90 절대오차는 17.639 MPa입니다. 합금족 검증 표본이 8개 미만이면 전체 DB 오차를 사용하며 상태는 최대 `weak_support`입니다.
