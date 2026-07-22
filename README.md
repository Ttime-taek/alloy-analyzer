# AI 합금 분석기

합금 조성(wt%)으로 고상선·액상선·인장강도와 리플로우 참고값을 계산하는 FastAPI + React 프로그램입니다. DB에 없는 조성도 예측하며, 각 수치에 최근접 DB 거리, 그룹 홀드아웃 교차검증 오차, 경험적 90% 범위, 사용 가능 수준을 함께 표시합니다.

생성형 AI는 수치를 만들거나 덮어쓰지 않습니다. 핵심 수치가 먼저 반환되고, AI 설명은 사용자가 별도로 요청할 때만 생성됩니다.

## 5분 로컬 실행

macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-fastapi.txt -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
./scripts/dev.sh
```

Windows:

```powershell
py -3 -m pip install -r requirements-fastapi.txt -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
start_all.bat
```

브라우저에서 `http://127.0.0.1:8000/`을 엽니다. API 문서는 `http://127.0.0.1:8000/docs`입니다.

## 테스트

```bash
.venv/bin/python -m pytest tests -q
cd frontend
npm test -- --run
npm run lint
npm run build
```

## API 키

키는 Git에 커밋하지 않습니다. 프로젝트 루트의 `.env` 또는 운영 환경변수에서만 관리합니다.

```dotenv
GEMINI_API_KEY=...
CEREBRAS_API_KEY=...
```

`.env`, `.env.local`, 기존 키 파일명은 `.gitignore`에 포함됩니다. 새 v1 핵심 예측 API는 키가 없어도 동작합니다.

## 주요 API

- `POST /api/v1/analyses`: AI 비의존 핵심 수치·검증 범위
- `POST /api/v1/analyses/{analysis_id}/explanations`: 선택적 AI 설명
- `GET /api/v1/capabilities`: 서버 기능·AI 연결 가능 여부
- `GET /api/v1/models`: 모델·DB·교차검증 버전과 평가 요약
- `/api/analyze`, `/api/compare`: 기존 클라이언트 호환 경로

자세한 계약은 [docs/API_V1.md](docs/API_V1.md), 오류는 [docs/ERRORS.md](docs/ERRORS.md), 기존 API 이전은 [docs/MIGRATION_V1.md](docs/MIGRATION_V1.md)를 참고하세요.

## 해석 원칙

- `DB 등록값`: 동일 조성의 DB 고상선·액상선을 그대로 사용합니다.
- `검증 범위 내 예측`: 같은 합금족 홀드아웃 검증 거리 안의 미등록 조성입니다.
- `근거 부족 예측`: 합금족 표본 부족 또는 먼 거리로 임시 추정만 제공합니다.
- `DB 범위 밖`: 수치는 탐색 참고로 남겨도 생산 공정 추천은 중단합니다.

표시되는 예측 범위는 현재 내장 DB의 경험적 오차 범위입니다. 공인 DSC·인장 시험, 제조사 TDS, 사내 승인 절차를 대체하지 않습니다.
