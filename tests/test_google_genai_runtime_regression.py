"""Regression coverage for the supported Google Gen AI runtime."""

from pathlib import Path

from test7 import ai_engine


_ROOT = Path(__file__).resolve().parents[1]


def test_supported_google_genai_sdk_is_the_only_declared_runtime() -> None:
    """SECURITY-003: do not restore the deprecated Gemini Python SDK."""
    # Found by /cso on 2026-08-12.
    # Report: .gstack/security-reports/2026-08-12-155000.json
    requirements = (_ROOT / "requirements-fastapi.txt").read_text(encoding="utf-8")
    source = (_ROOT / "ai_engine.py").read_text(encoding="utf-8")

    assert "google-genai" in requirements
    assert "google-generativeai" not in requirements
    assert "google.generativeai" not in source


def test_google_genai_client_initializes_without_a_network_request() -> None:
    assert ai_engine._GENAI_BACKEND == "google.genai"

    engine = ai_engine.AIEngine(api_key="test-key-not-real")

    assert engine.available is True
    assert engine.client is not None
