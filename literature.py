import json
import os
import socket
import time
import urllib.parse
import urllib.request


def _http_get_json(url: str, timeout_s: float = 6.0):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AutoAlloyAnalyzer/1.0 (mailto:example@example.com)",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None


def _cache_path():
    configured = (os.getenv("ALLOY_LITERATURE_CACHE_PATH") or "").strip()
    if configured:
        return os.path.expanduser(configured)
    try:
        base = os.path.dirname(__file__)
    except Exception:
        base = "."
    return os.path.join(base, "literature_cache.json")


def _load_cache():
    path = _cache_path()
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache: dict):
    path = _cache_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        return


def _cache_get(key: str, ttl_s: float):
    cache = _load_cache()
    rec = cache.get(key)
    if not isinstance(rec, dict):
        return None
    ts = rec.get("ts")
    if ts is None:
        return None
    try:
        ts = float(ts)
    except Exception:
        return None
    if (time.time() - ts) > float(ttl_s):
        return None
    return rec.get("data")


def _cache_set(key: str, data):
    cache = _load_cache()
    cache[key] = {"ts": time.time(), "data": data}
    _save_cache(cache)


def cached_call(key: str, fetch_fn, ttl_days: float = 7.0):
    ttl_s = float(ttl_days) * 86400.0
    got = _cache_get(key, ttl_s=ttl_s)
    if got is not None:
        return got
    data = fetch_fn()
    _cache_set(key, data)
    return data


def _year_from_item(item: dict):
    for k in ("published-print", "published-online", "created", "issued"):
        v = item.get(k)
        if isinstance(v, dict):
            parts = v.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                try:
                    return int(parts[0][0])
                except Exception:
                    pass
    return None


def _first(x):
    if isinstance(x, list) and x:
        return x[0]
    return x


def crossref_search(query: str, rows: int = 5, timeout_s: float = 6.0):
    """
    Crossref Works API search (no key required).
    Returns a list of dicts: {title, year, doi, url, publisher, type}
    """
    q = (query or "").strip()
    if not q:
        return []

    params = {
        "query": q,
        "rows": str(int(max(1, min(20, rows)))),
        "select": "title,DOI,URL,publisher,type,issued,published-print,published-online,created",
        "sort": "relevance",
        "order": "desc",
    }
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    key = f"crossref:q={q}|rows={rows}"
    try:
        data = cached_call(
            key,
            lambda: _http_get_json(url, timeout_s=timeout_s),
            ttl_days=7.0,
        )
    except (socket.timeout, OSError, ValueError):
        return []

    if not isinstance(data, dict):
        return []
    msg = data.get("message")
    if not isinstance(msg, dict):
        return []
    items = msg.get("items")
    if not isinstance(items, list):
        return []

    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = _first(it.get("title"))
        if isinstance(title, str):
            title = title.strip()
        else:
            title = ""
        doi = it.get("DOI") if isinstance(it.get("DOI"), str) else ""
        url_ = it.get("URL") if isinstance(it.get("URL"), str) else ""
        publisher = it.get("publisher") if isinstance(it.get("publisher"), str) else ""
        typ = it.get("type") if isinstance(it.get("type"), str) else ""
        year = _year_from_item(it) if isinstance(it, dict) else None

        if not title:
            continue
        out.append(
            {
                "title": title,
                "year": year,
                "doi": doi,
                "url": url_,
                "publisher": publisher,
                "type": typ,
            }
        )
    return out


def semantic_scholar_search(query: str, limit: int = 5, timeout_s: float = 6.0):
    """
    Semantic Scholar API search (no key required for basic usage; may rate-limit).
    Returns list of dicts: {title, year, url, doi, citationCount, venue}
    """
    q = (query or "").strip()
    if not q:
        return []
    limit = int(max(1, min(20, limit)))

    params = {
        "query": q,
        "limit": str(limit),
        "fields": "title,year,url,externalIds,citationCount,venue",
    }
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    key = f"s2:search:q={q}|limit={limit}"
    try:
        data = cached_call(
            key,
            lambda: _http_get_json(url, timeout_s=timeout_s),
            ttl_days=3.0,
        )
    except (socket.timeout, OSError, ValueError):
        return []

    if not isinstance(data, dict):
        return []
    items = data.get("data")
    if not isinstance(items, list):
        return []

    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = it.get("title") if isinstance(it.get("title"), str) else ""
        title = title.strip()
        if not title:
            continue
        year = it.get("year", None)
        try:
            year = int(year) if year is not None else None
        except Exception:
            year = None
        url_ = it.get("url") if isinstance(it.get("url"), str) else ""
        venue = it.get("venue") if isinstance(it.get("venue"), str) else ""
        citation_count = it.get("citationCount", None)
        try:
            citation_count = int(citation_count) if citation_count is not None else None
        except Exception:
            citation_count = None
        doi = ""
        ex = it.get("externalIds")
        if isinstance(ex, dict):
            v = ex.get("DOI")
            if isinstance(v, str):
                doi = v.strip()
        out.append(
            {
                "title": title,
                "year": year,
                "url": url_,
                "doi": doi,
                "citationCount": citation_count,
                "venue": venue,
            }
        )
    return out


def semantic_scholar_lookup_by_doi(doi: str, timeout_s: float = 6.0):
    """
    Semantic Scholar paper lookup by DOI. Returns dict or None.
    """
    d = (doi or "").strip()
    if not d:
        return None
    # Normalize prefix
    d = d.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    url = "https://api.semanticscholar.org/graph/v1/paper/DOI:" + urllib.parse.quote(d) + "?" + urllib.parse.urlencode(
        {"fields": "title,year,url,externalIds,citationCount,venue"}
    )
    key = f"s2:doi:{d}"
    try:
        data = cached_call(
            key,
            lambda: _http_get_json(url, timeout_s=timeout_s),
            ttl_days=14.0,
        )
    except (socket.timeout, OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
