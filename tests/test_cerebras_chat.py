from __future__ import annotations

from types import SimpleNamespace

from test7.cerebras_chat import CerebrasChatEngine


class _FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _engine_with_response(response, model="gpt-oss-120b") -> tuple[CerebrasChatEngine, _FakeCompletions]:
    completions = _FakeCompletions(response)
    engine = CerebrasChatEngine.__new__(CerebrasChatEngine)
    engine.model = model
    engine.api_key = "test"
    engine.available = True
    engine.last_error = ""
    engine._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return engine, completions


def test_gpt_oss_uses_low_reasoning_and_completion_tokens() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content="OK"))
        ]
    )
    engine, completions = _engine_with_response(response)

    assert engine.ask("Return exactly OK", max_tokens=123) == "OK"

    assert completions.kwargs["model"] == "gpt-oss-120b"
    assert completions.kwargs["max_completion_tokens"] == 123
    assert completions.kwargs["reasoning_effort"] == "low"
    assert completions.kwargs["timeout"] == 15.0
    assert "max_tokens" not in completions.kwargs


def test_empty_cerebras_content_is_reported_as_failure() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=None))
        ]
    )
    engine, _ = _engine_with_response(response)

    assert engine.ask("Return exactly OK") == ""
    assert "no message content" in engine.last_error
