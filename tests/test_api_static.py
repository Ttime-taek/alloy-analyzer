# -*- coding: utf-8 -*-
"""api_server HTTP smoke: API routes coexist with optional frontend/dist SPA mount."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import api_server as api_mod  # noqa: E402


class ApiStaticSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from fastapi.testclient import TestClient
        except ImportError as e:
            raise unittest.SkipTest("httpx required for TestClient") from e
        cls.client = TestClient(api_mod.app)

    def test_about_includes_recommend_melt(self) -> None:
        r = self.client.get("/api/about")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("api_features", data)
        self.assertTrue(data["api_features"].get("recommend_melt"))

    def test_openapi_lists_recommend_melt(self) -> None:
        r = self.client.get("/openapi.json")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("/api/recommend_melt", (r.json().get("paths") or {}))

    def test_root_serves_spa_when_dist_built(self) -> None:
        index = _ROOT / "frontend" / "dist" / "index.html"
        if not index.is_file():
            self.skipTest("frontend/dist not built — run: cd frontend && npm run build")
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200, r.text)
        ct = (r.headers.get("content-type") or "").lower()
        self.assertIn("text/html", ct)
        self.assertGreater(len(r.text), 100)

    def test_api_routes_not_blocked_by_spa_mount(self) -> None:
        """StaticFiles on / must not return 405 for POST /api/*."""
        r = self.client.post("/api/compare", json={"comp_a": {}, "comp_b": {"Sn": 50, "Bi": 50}})
        self.assertEqual(r.status_code, 422, r.text)
