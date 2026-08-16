"""Regression coverage for loading AI keys only from environment files."""

from __future__ import annotations

from pathlib import Path

import test7.ai_engine as ai_engine
import test7.env_loader as env_loader


# Regression: pre-landing review found legacy plaintext key filenames could be
# copied into a Docker build context (2026-08-17).
def test_ai_key_loader_ignores_legacy_plaintext_files(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ai_engine, "__file__", str(tmp_path / "ai_engine.py"))
    (tmp_path / "gemini_api_key.txt").write_text("legacy-key-must-not-load\n", encoding="utf-8")

    assert ai_engine.AIEngine._load_key_from_env_files() == ""

    Path(tmp_path / ".env").write_text("GEMINI_API_KEY=env-file-key\n", encoding="utf-8")
    assert ai_engine.AIEngine._load_key_from_env_files() == "env-file-key"


def test_shared_env_loader_ignores_legacy_key_files(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(env_loader, "_iter_candidate_roots", lambda: [tmp_path])
    (tmp_path / ".gemini_api_key").write_text("legacy-key-must-not-load\n", encoding="utf-8")

    assert env_loader.load_env_key("GEMINI_API_KEY") == ""

    (tmp_path / ".env.local").write_text("GEMINI_API_KEY=local-env-key\n", encoding="utf-8")
    assert env_loader.load_env_key("GEMINI_API_KEY") == "local-env-key"


def test_desktop_entrypoint_uses_env_loader_only() -> None:
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    assert 'load_env_key("GEMINI_API_KEY")' in source
    assert 'log_exception("desktop startup", e)' in source
    assert ".gemini_api_key" not in source
    assert "gemini_api_key.txt" not in source
    assert "save_error" not in source
