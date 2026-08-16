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
