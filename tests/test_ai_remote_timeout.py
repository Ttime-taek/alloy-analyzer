from __future__ import annotations

from types import SimpleNamespace

from test7 import ai_engine
from test7.ai_engine import AIEngine, _remote_ai_timeout_s


class _FakeGenaiClient:
    last_http_options = None

    def __init__(self, *, api_key, http_options) -> None:
        assert api_key == "test-key-not-real"
        type(self).last_http_options = http_options


def test_gemini_client_has_a_bounded_timeout(monkeypatch) -> None:
    monkeypatch.setenv("AI_REMOTE_TIMEOUT_S", "7.5")
    fake_genai = SimpleNamespace(
        Client=_FakeGenaiClient,
        types=SimpleNamespace(HttpOptions=lambda *, timeout: {"timeout": timeout}),
    )
    monkeypatch.setattr(ai_engine, "genai", fake_genai)
    monkeypatch.setattr(ai_engine, "_GENAI_BACKEND", "google.genai")

    engine = AIEngine(api_key="test-key-not-real")

    assert engine.available is True
    assert _FakeGenaiClient.last_http_options == {"timeout": 7500}


def test_remote_timeout_is_clamped(monkeypatch) -> None:
    monkeypatch.setenv("AI_REMOTE_TIMEOUT_S", "999")
    assert _remote_ai_timeout_s() == 60.0
    monkeypatch.setenv("AI_REMOTE_TIMEOUT_S", "0")
    assert _remote_ai_timeout_s() == 2.0


def _engine_with_client(client) -> AIEngine:
    engine = AIEngine.__new__(AIEngine)
    engine.available = True
    engine.client = client
    engine._cerebras = None
    engine.status_detail = ""
    engine.last_error_detail = ""
    engine.usage_stats = {}
    return engine


def test_google_genai_ask_uses_client_models_generate_content() -> None:
    calls = []

    class FakeModels:
        @staticmethod
        def generate_content(*, model, contents):
            calls.append((model, contents))
            return SimpleNamespace(text="OK")

    engine = _engine_with_client(SimpleNamespace(models=FakeModels()))

    assert engine.ask("Return exactly OK") == "OK"
    assert calls == [("gemini-2.5-flash", "Return exactly OK")]
    assert engine.usage_stats["ask_success"] == 1


def test_google_genai_ask_reports_client_error_without_retrying_gemini() -> None:
    calls = []

    class FailingModels:
        @staticmethod
        def generate_content(*, model, contents):
            calls.append((model, contents))
            raise RuntimeError("test transport failure")

    engine = _engine_with_client(SimpleNamespace(models=FailingModels()))

    result = engine.ask("Return exactly OK")

    assert result.startswith("AI 오류:")
    assert calls == [("gemini-2.5-flash", "Return exactly OK")]
    assert engine.usage_stats["ask_errors"] == 1
