from __future__ import annotations

from types import SimpleNamespace

from test7.ai_engine import AIEngine, _remote_ai_timeout_s


class _FakeGeminiModel:
    def __init__(self) -> None:
        self.request_options = None

    def generate_content(self, _prompt, *, request_options):
        self.request_options = request_options
        return SimpleNamespace(text="OK")


def test_gemini_request_has_a_bounded_timeout(monkeypatch) -> None:
    monkeypatch.setenv("AI_REMOTE_TIMEOUT_S", "7.5")
    model = _FakeGeminiModel()
    engine = AIEngine.__new__(AIEngine)
    engine.available = True
    engine.model = model
    engine.client = None
    engine.request_timeout_s = _remote_ai_timeout_s()
    engine._cerebras = None
    engine.status_detail = ""
    engine.last_error_detail = ""
    engine.usage_stats = {}

    assert engine.ask("Return exactly OK") == "OK"
    assert model.request_options == {"timeout": 7.5}


def test_remote_timeout_is_clamped(monkeypatch) -> None:
    monkeypatch.setenv("AI_REMOTE_TIMEOUT_S", "999")
    assert _remote_ai_timeout_s() == 60.0
    monkeypatch.setenv("AI_REMOTE_TIMEOUT_S", "0")
    assert _remote_ai_timeout_s() == 2.0
