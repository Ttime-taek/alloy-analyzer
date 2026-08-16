"""Regression coverage for shared favorites authorization."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import api_server as api_mod


# Regression: SECURITY-002 — shared favorites storage was publicly readable and writable.
# Found by /cso on 2026-08-12.
# Report: .gstack/security-reports/2026-08-12-155000.json
def test_favorites_backend_is_disabled_without_server_token() -> None:
    client = TestClient(api_mod.app)
    reader = AsyncMock(return_value=[])
    writer = AsyncMock()

    with (
        patch.dict(os.environ, {"ALLOY_FAVORITES_SYNC_TOKEN": ""}),
        patch.object(api_mod, "read_supabase_favorites", new=reader),
        patch.object(api_mod, "write_supabase_favorites", new=writer),
        patch.object(api_mod, "_read_web_favorites_file") as local_reader,
        patch.object(api_mod, "_write_web_favorites_file") as local_writer,
    ):
        get_response = client.get("/api/favorites")
        put_response = client.put("/api/favorites", json={"favorites": []})

    assert get_response.status_code == 404
    assert put_response.status_code == 404
    reader.assert_not_awaited()
    writer.assert_not_awaited()
    local_reader.assert_not_called()
    local_writer.assert_not_called()

    with patch.dict(
        os.environ,
        {"ALLOY_FAVORITES_SYNC_TOKEN": "predictable-short-token"},
    ):
        weak_token_response = client.get(
            "/api/favorites",
            headers={"Authorization": "Bearer predictable-short-token"},
        )

    assert weak_token_response.status_code == 404


def test_favorites_backend_requires_matching_bearer_token() -> None:
    client = TestClient(api_mod.app)
    sync_token = "server-only-test-token-with-at-least-32-chars"
    stored = [{"name": "SAC305", "comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}}]
    reader = AsyncMock(return_value=stored)
    writer = AsyncMock()

    with (
        patch.dict(os.environ, {"ALLOY_FAVORITES_SYNC_TOKEN": sync_token}),
        patch.object(api_mod, "supabase_configured", return_value=True),
        patch.object(api_mod, "read_supabase_favorites", new=reader),
        patch.object(api_mod, "write_supabase_favorites", new=writer),
    ):
        missing = client.get("/api/favorites")
        invalid = client.get(
            "/api/favorites",
            headers={"Authorization": "Bearer wrong-token"},
        )
        valid = client.get(
            "/api/favorites",
            headers={"Authorization": f"Bearer {sync_token}"},
        )
        updated = client.put(
            "/api/favorites",
            headers={"Authorization": f"Bearer {sync_token}"},
            json={"favorites": stored},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.headers["www-authenticate"] == "Bearer"
    assert valid.status_code == 200, valid.text
    assert valid.json()["favorites"] == stored
    assert updated.status_code == 200, updated.text
    reader.assert_awaited_once()
    writer.assert_awaited_once_with(stored)
