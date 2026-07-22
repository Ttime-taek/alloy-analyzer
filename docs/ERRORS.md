# API 오류

v1 API의 업무 오류는 FastAPI `detail` 안에 구조화된 객체로 반환됩니다.

```json
{
  "detail": {
    "code": "COMPOSITION_SUM_INVALID",
    "message": "comp: wt% 합이 97.00% 입니다..."
  }
}
```

| HTTP | code | 의미 | 조치 |
|---:|---|---|---|
| 422 | `COMPOSITION_SUM_INVALID` | wt% 합이 100.00이 아님 | 입력 합계를 수정 |
| 422 | `COMPOSITION_INVALID` | 음수·비유한 값·미지원 기호 | 해당 원소 입력 수정 |
| 409 | `ANALYSIS_ID_MISMATCH` | 경로와 body ID 불일치 | 같은 핵심 분석 ID 사용 |
| 409 | `ANALYSIS_BINDING_INVALID` | 모델·DB 버전 또는 조성이 변경됨 | 핵심 분석 재실행 |
| 429 | `EXPLANATION_RATE_LIMITED` | 같은 클라이언트의 설명 요청 한도 초과 | `Retry-After` 이후 재시도 |
| 429 | `EXPLANATION_BUSY` | 서버가 다른 설명을 생성 중 | 잠시 후 수동 재시도 |
| 500 | `CORE_ANALYSIS_FAILED` | 핵심 계산 실패 | 서버 로그 확인 후 재시도 |
| 502 | `EXPLANATION_FAILED` | 선택적 AI 설명 실패 | 핵심 결과는 유지, AI만 수동 재시도 |

Pydantic 요청 스키마 오류는 기존 FastAPI 검증 배열 형식을 유지합니다.
