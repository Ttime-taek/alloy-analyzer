"""Regression coverage for loading AI keys only from environment files."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
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


def test_api_server_loads_documented_runtime_settings_from_env_files() -> None:
    source = (Path(__file__).resolve().parents[1] / "api_server.py").read_text(
        encoding="utf-8"
    )
    module = ast.parse(source)
    assignments = {
        target.id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "_API_ENV_KEYS"
    }
    configured = set(assignments["_API_ENV_KEYS"])

    assert {
        "AI_REMOTE_TIMEOUT_S",
        "AI_CACHE_ENABLED",
        "AI_DB_EXACT_MODE",
        "ALLOY_API_CORS_ORIGINS",
        "ALLOY_API_HOST",
        "ALLOY_API_PORT",
        "ALLOY_EXPLANATION_RATE_LIMIT",
        "ALLOY_EXPLANATION_RATE_WINDOW_SEC",
        "ALLOY_EXPLANATION_CONCURRENCY",
        "ALLOY_FAVORITES_SYNC_TOKEN",
        "ALLOY_FAVORITES_PATH",
        "ALLOY_LITERATURE_CACHE_PATH",
    }.issubset(configured)
    assert "load_env_keys(_API_ENV_KEYS, override=False)" in source


def test_api_server_applies_env_file_settings_before_lazy_runtime_import(tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                "AI_CACHE_ENABLED=0",
                "AI_DB_EXACT_MODE=skip",
                "ALLOY_EXPLANATION_RATE_LIMIT=17",
                "ALLOY_EXPLANATION_RATE_WINDOW_SEC=75",
                "ALLOY_EXPLANATION_CONCURRENCY=3",
                "ALLOY_FAVORITES_PATH=/tmp/alloy-test-favorites.json",
            )
        ),
        encoding="utf-8",
    )
    script = """
import os
import sys
from pathlib import Path

import test7.env_loader as env_loader

root = Path(sys.argv[1])
env_loader._iter_candidate_roots = lambda: [root]
for key in (
    "AI_CACHE_ENABLED",
    "AI_DB_EXACT_MODE",
    "ALLOY_EXPLANATION_RATE_LIMIT",
    "ALLOY_EXPLANATION_RATE_WINDOW_SEC",
    "ALLOY_EXPLANATION_CONCURRENCY",
    "ALLOY_FAVORITES_PATH",
):
    os.environ.pop(key, None)

import test7.api_server as api_server
from test7 import ai_cache, analyzer

assert api_server._EXPLANATION_RATE_LIMIT == 17
assert api_server._EXPLANATION_RATE_WINDOW_SEC == 75
assert api_server._EXPLANATION_CONCURRENCY == 3
assert os.environ["ALLOY_FAVORITES_PATH"] == "/tmp/alloy-test-favorites.json"
assert ai_cache._CACHE_ENABLED is False
assert analyzer._AI_DB_EXACT_MODE == "skip"
"""
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
