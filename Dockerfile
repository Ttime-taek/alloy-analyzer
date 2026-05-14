# 합금 분석기: FastAPI + Vite 빌드 UI를 한 프로세스에서 제공 (웹사이트처럼 URL로 접속)
#
# 로컬 빌드:  docker build -t alloy-web .
# 실행:       docker run --rm -p 8000:8000 -e GEMINI_API_KEY=여기에키 alloy-web
# Render 등:  PORT 환경변수를 서비스가 넣어 주면 그 포트로 바인딩됩니다.

# ── 1) 프론트 빌드 ─────────────────────────────────────────────
FROM node:20-bookworm-slim AS frontend
WORKDIR /src/test7/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── 2) API + 정적 UI ────────────────────────────────────────────
FROM python:3.12-slim-bookworm
WORKDIR /workspace
ENV PYTHONPATH=/workspace
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-fastapi.txt /workspace/test7/
RUN pip install --no-cache-dir -r /workspace/test7/requirements-fastapi.txt

COPY . /workspace/test7/
COPY --from=frontend /src/test7/frontend/dist /workspace/test7/frontend/dist

EXPOSE 8000
# ALLOY_SERVE_STATIC=0 이면 API만 (정적 미마운트). 기본은 dist 있으면 UI+API.
CMD ["sh", "-c", "exec uvicorn test7.api_server:app --host 0.0.0.0 --port ${PORT:-8000}"]
