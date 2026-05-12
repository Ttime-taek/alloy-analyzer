"""
AI 응답 디스크 캐시
====================
- 조성/모드/리터러처모드 해시를 키로 `get_full_analysis` 결과(JSON)를 파일로 저장.
- 같은 조성을 재분석하면 Gemini/Cerebras 호출 없이 캐시를 그대로 반환.
- 기본 TTL 30일 (오래된 항목은 stale로 간주).

저장 위치: <repo_root>/.cache/ai/<prefix>/<hash>.json
키: sha256(정규화조성 소트 + mode + literature_mode + schema_version + extra)
  extra: analyzer에서 melting_engine_version(mv=…) + solder DB 지문(dbfp=…) 등을 넣어
  용융 엔진·실측 DB 변경 시 캐시 무효화.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

# 프롬프트·스키마가 크게 바뀌면 버전을 올려 기존 캐시를 자동 무효화.
SCHEMA_VERSION = "v1"

# 기본 TTL: 30일
DEFAULT_TTL_SEC = 30 * 24 * 60 * 60

# 캐시 활성화 플래그 (env로 끌 수 있음)
_CACHE_ENABLED = os.environ.get("AI_CACHE_ENABLED", "1").lower() not in ("0", "false", "no")


def _cache_dir() -> Path:
    # 이 파일이 있는 디렉터리(test7 패키지 루트 = git 저장소 루트) → <test7>/.cache/ai
    here = Path(__file__).resolve().parent
    d = here / ".cache" / "ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _round_comp(comp: Dict[str, Any]) -> Dict[str, float]:
    """부동소수 미세차이로 키가 달라지지 않도록 소수 4자리 반올림."""
    out: Dict[str, float] = {}
    for k, v in (comp or {}).items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if abs(f) < 1e-6:
            continue
        out[str(k)] = round(f, 4)
    return out


def make_key(
    norm: Dict[str, Any],
    mode: str = "eng",
    literature_mode: str = "fast",
    extra: Optional[str] = None,
) -> str:
    """캐시 키: 조성+모드+스키마버전 sha256 hex (16자로 축약)."""
    comp = _round_comp(norm)
    items = sorted(comp.items())
    payload = {
        "schema": SCHEMA_VERSION,
        "mode": (mode or "eng").strip().lower(),
        "lit": (literature_mode or "fast").strip().lower(),
        "comp": items,
    }
    if extra:
        payload["extra"] = str(extra)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _key_path(key: str) -> Path:
    # 2글자 prefix로 폴더 분산 (파일 폭주 방지)
    prefix = key[:2]
    d = _cache_dir() / prefix
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def get(key: str, ttl_sec: int = DEFAULT_TTL_SEC) -> Optional[Dict[str, Any]]:
    """캐시 hit이면 dict 반환, miss/만료/손상이면 None."""
    if not _CACHE_ENABLED or not key:
        return None
    try:
        p = _key_path(key)
        if not p.exists():
            return None
        age = time.time() - p.stat().st_mtime
        if age > ttl_sec:
            return None
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        # 캐시 메타 표시 (호출부에서 AI 호출 여부 판단용)
        data = dict(data)
        data["_cache_hit"] = True
        data["_cache_age_sec"] = int(age)
        return data
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def put(key: str, value: Dict[str, Any]) -> bool:
    """캐시 저장. 성공 시 True. 캐시 비활성화거나 실패 시 False."""
    if not _CACHE_ENABLED or not key or not isinstance(value, dict):
        return False
    try:
        # 캐시 메타 필드는 저장하지 않는다 (읽을 때 다시 붙임)
        clean = {k: v for k, v in value.items() if not str(k).startswith("_cache_")}
        p = _key_path(key)
        tmp = p.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except (OSError, TypeError, ValueError):
        return False


def purge_expired(ttl_sec: int = DEFAULT_TTL_SEC) -> int:
    """TTL 만료된 파일 제거. 반환: 지운 파일 수."""
    n = 0
    try:
        root = _cache_dir()
        now = time.time()
        for p in root.rglob("*.json"):
            try:
                if now - p.stat().st_mtime > ttl_sec:
                    p.unlink()
                    n += 1
            except OSError:
                continue
    except OSError:
        pass
    return n


def stats() -> Dict[str, Any]:
    """캐시 현황 요약 (hit/miss 집계는 호출부가 관리; 여기선 용량만)."""
    total = 0
    size = 0
    try:
        root = _cache_dir()
        for p in root.rglob("*.json"):
            try:
                total += 1
                size += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return {
        "enabled": _CACHE_ENABLED,
        "schema": SCHEMA_VERSION,
        "ttl_sec": DEFAULT_TTL_SEC,
        "dir": str(_cache_dir()),
        "entries": total,
        "total_bytes": size,
    }
