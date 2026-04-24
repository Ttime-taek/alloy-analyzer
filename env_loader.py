"""
env_loader.py

Project-local .env loader (no external deps).
We deliberately avoid importing python-dotenv to keep runtime simple.

Used for API keys that may be stored in:
- .env
- .env.local
in either repo root, current working directory, or this module's directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence


def _iter_candidate_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        here = Path(__file__).resolve().parent
        roots.append(here)
        roots.append(Path.cwd())
        roots.append(here.parent)
    except Exception:
        pass
    # de-dup while preserving order
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        try:
            key = str(r)
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _parse_env_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        key = k.strip()
        if not key:
            continue
        val = v.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if val:
            out[key] = val
    return out


def load_env_keys(keys: Sequence[str] | None = None, *, override: bool = False) -> dict[str, str]:
    """
    Load selected keys from .env files into os.environ.

    - keys: list of env var names to load. If None, loads all keys found.
    - override: if False, does not overwrite already-set environment variables.

    Returns: dict of loaded key->value (only those applied).
    """
    wanted = set(keys or [])
    loaded: dict[str, str] = {}
    env_files = (".env", ".env.local")

    for root in _iter_candidate_roots():
        for name in env_files:
            path = root / name
            if not path.is_file():
                continue
            try:
                data = _parse_env_text(path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue

            for k, v in data.items():
                if wanted and k not in wanted:
                    continue
                if not override and (os.getenv(k) or "").strip():
                    continue
                os.environ[k] = v
                loaded[k] = v
    return loaded


def load_env_key(key: str, *, override: bool = False) -> str:
    """Convenience wrapper for a single key."""
    if not override and (os.getenv(key) or "").strip():
        return str(os.getenv(key) or "").strip()
    load_env_keys([key], override=override)
    return str(os.getenv(key) or "").strip()

