# `/api/analyze`에서 v1로 이전

기존 `/api/analyze`는 계속 지원합니다. 신규 UI와 통합은 v1을 권장합니다.

1. 분석 요청을 `POST /api/v1/analyses`로 변경합니다.
2. 기존 화면 데이터는 응답의 `result`에서 읽습니다.
3. `prediction_contract.properties`의 상태·범위·사유를 수치와 함께 표시합니다.
4. `process_recommendation.allowed=false`이면 피크 추천·튜너를 비활성화합니다.
5. AI 설명이 필요할 때만 반환된 `analysis_id`와 같은 조성으로 설명 엔드포인트를 호출합니다.
6. 새 분석을 시작하면 이전 요청을 취소하고, 늦게 도착한 응답의 ID가 현재 ID와 다르면 버립니다.

기존 flat 응답을 쓰는 클라이언트는 즉시 변경할 필요가 없습니다. 단, 기존 경로에는 경험적 오차범위와 공정 거부 정책이 없으므로 생산 의사결정 UI에는 v1 계약을 사용해야 합니다.
