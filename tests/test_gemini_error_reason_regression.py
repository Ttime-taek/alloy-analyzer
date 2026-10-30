# Regression: 2026-10-30 실행 점검 — 운영에서 AI 설명이 "Gemini 호출 오류 — Cerebras 폴백"으로만 표시되고
# 원인을 볼 수 없었다(예외 원문은 로그에도 남지 않음). 이제 HTTP·상태 코드만 상태 문구에 붙이고,
# 원문은 서버 로그에 남긴다. API 키 등 원문 내용은 화면으로 나가지 않는다.
# Found by 운영 화면 직접 실행 점검 (Claude) on 2026-10-30
from __future__ import annotations

from test7.ai_engine import AIEngine


def test_reason_extracts_only_codes() -> None:
    r = AIEngine._gemini_error_reason(
        "403 PERMISSION_DENIED. {'error': {'code': 403, 'message': 'Your API key AIzaSyFAKEKEY was reported as leaked'}}"
    )
    assert r == "403 PERMISSION_DENIED"
    assert "AIza" not in r
    assert AIEngine._gemini_error_reason("404 NOT_FOUND. models/gemini-x is not found") == "404 NOT_FOUND"
    assert AIEngine._gemini_error_reason("400 INVALID_ARGUMENT API key not valid") == "400 INVALID_ARGUMENT"
    assert AIEngine._gemini_error_reason("Request timed out") == "timeout"
    assert AIEngine._gemini_error_reason("something odd") == ""


def test_status_detail_carries_reason_on_cerebras_fallback() -> None:
    engine = object.__new__(AIEngine)
    engine.available = True
    engine.usage_stats = {}
    engine.last_error_detail = ""
    engine.status_detail = ""

    class _Models:
        @staticmethod
        def generate_content(**_kw):
            raise RuntimeError("404 NOT_FOUND. {'error': {'message': 'model not found'}}")

    class _Client:
        models = _Models()

    engine.client = _Client()
    engine._cerebras_ask = lambda prompt, parse_list=False: "fallback text"
    out = engine.ask("hello")
    assert out == "fallback text"
    assert engine.status_detail == "Cerebras 폴백 사용 중 (Gemini 호출 오류: 404 NOT_FOUND)"
