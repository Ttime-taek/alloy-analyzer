"""One-off QA smoke for composition 100% gate (report-only helper)."""
from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path: str) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(BASE + path)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, dict(r.headers.items()), r.read()


def post(path: str, body: dict) -> tuple[int, object]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> None:
    st, hdrs, html = get("/")
    print("GET /", st, hdrs.get("Cache-Control", hdrs.get("cache-control", "")))
    js_name = ""
    for part in html.decode("utf-8", errors="replace").split('"'):
        if part.startswith("/assets/index-") and part.endswith(".js"):
            js_name = part
            break
    print("bundle", js_name)
    if js_name:
        _, _, js = get(js_name)
        text = js.decode("utf-8", errors="replace")
        print("strict_100_in_bundle", "100.00" in text and "toFixed(2)" in text)
        print("old_tolerance_in_bundle", "0.5%에" in text)

    s1, b1 = post("/api/analyze", {"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.0}})
    print("POST 99.5%", s1, b1)
    s2, b2 = post("/api/analyze", {"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}})
    print("POST 100%", s2, "ok" if s2 == 200 else b2)


if __name__ == "__main__":
    main()
