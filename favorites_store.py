"""Persistent favorites storage with optional Supabase backing."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx


class FavoritesStoreError(RuntimeError):
    """Raised when configured persistent storage cannot be used."""


def supabase_configured() -> bool:
    return bool(
        (os.getenv("SUPABASE_URL") or "").strip()
        and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    )


def _request_config() -> tuple[str, Dict[str, str]]:
    base_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not base_url or not service_key:
        raise FavoritesStoreError("Supabase environment variables are incomplete.")
    return (
        f"{base_url}/rest/v1/alloy_app_state",
        {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
    )


async def read_supabase_favorites() -> List[Dict[str, Any]]:
    url, headers = _request_config()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers=headers,
                params={"id": "eq.default", "select": "favorites"},
            )
            response.raise_for_status()
            rows = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FavoritesStoreError(f"Supabase favorites read failed: {exc}") from exc

    if not rows:
        return []
    favorites = rows[0].get("favorites") if isinstance(rows[0], dict) else None
    return favorites if isinstance(favorites, list) else []


async def write_supabase_favorites(items: List[Dict[str, Any]]) -> None:
    url, headers = _request_config()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers=headers,
                params={"on_conflict": "id"},
                json={"id": "default", "favorites": items},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FavoritesStoreError(f"Supabase favorites write failed: {exc}") from exc
