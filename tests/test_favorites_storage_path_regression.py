"""Regression coverage for writable favorites storage in the non-root container."""

from __future__ import annotations

import test7.api_server as api_mod
import test7.literature as literature


# Regression: pre-landing review found that the non-root container could not write
# web_favorites.json beside the root-owned application source (2026-08-17).
def test_favorites_storage_uses_configured_writable_path(monkeypatch, tmp_path) -> None:
    configured_path = tmp_path / "nested" / "web_favorites.json"
    favorites = [{"name": "SAC305", "comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}}]
    monkeypatch.setenv("ALLOY_FAVORITES_PATH", str(configured_path))

    api_mod._write_web_favorites_file(favorites)

    assert api_mod._web_favorites_path() == configured_path
    assert api_mod._read_web_favorites_file() == favorites
    assert configured_path.is_file()


def test_literature_cache_uses_configured_writable_path(monkeypatch, tmp_path) -> None:
    configured_path = tmp_path / "nested" / "literature_cache.json"
    monkeypatch.setenv("ALLOY_LITERATURE_CACHE_PATH", str(configured_path))
    fetch_count = 0

    def fetch():
        nonlocal fetch_count
        fetch_count += 1
        return [{"title": "Example"}]

    first = literature.cached_call("query", fetch)
    second = literature.cached_call("query", fetch)

    assert literature._cache_path() == str(configured_path)
    assert first == second == [{"title": "Example"}]
    assert fetch_count == 1
    assert configured_path.is_file()
