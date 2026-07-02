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
        self.assertTrue(data["api_features"].get("compare_shared_wetting"))

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

    def test_favicon_not_404_when_dist_built(self) -> None:
        favicon = _ROOT / "frontend" / "dist" / "favicon.svg"
        if not favicon.is_file():
            self.skipTest("frontend/dist/favicon.svg missing — run: cd frontend && npm run build")
        r = self.client.get("/favicon.ico")
        self.assertEqual(r.status_code, 200, r.text)
        ct = (r.headers.get("content-type") or "").lower()
        self.assertTrue("image" in ct or "svg" in ct, ct)

    def test_api_routes_not_blocked_by_spa_mount(self) -> None:
        """StaticFiles on / must not return 405 for POST /api/*."""
        r = self.client.post("/api/compare", json={"comp_a": {}, "comp_b": {"Sn": 50, "Bi": 50}})
        self.assertEqual(r.status_code, 422, r.text)

    def test_analyze_rejects_incomplete_wt_sum(self) -> None:
        r = self.client.post(
            "/api/analyze",
            json={"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.0}},
        )
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn("100.00", r.text)

    def test_analyze_accepts_exact_100_wt_sum(self) -> None:
        r = self.client.post(
            "/api/analyze",
            json={"comp": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}},
        )
        self.assertNotEqual(r.status_code, 422, r.text[:500])

    def test_analyze_accepts_p_alloy_and_returns_density(self) -> None:
        r = self.client.post(
            "/api/analyze",
            json={"comp": {"Sn": 99.455, "Cu": 0.5, "Ni": 0.03, "P": 0.015}},
        )
        self.assertEqual(r.status_code, 200, r.text[:500])
        data = r.json()
        self.assertEqual(data["best_name"], "Sn-0.5Cu-0.03Ni-0.015P")
        self.assertAlmostEqual(float(data["props"]["density"]), 7.3, places=3)

    def test_compare_uses_shared_wetting_temp(self) -> None:
        r = self.client.post(
            "/api/compare",
            json={
                "comp_a": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
                "comp_b": {"Sn": 96.2, "Ag": 0.3, "Cu": 0.5, "Bi": 3.0},
                "literature_mode": "fast",
            },
        )
        self.assertEqual(r.status_code, 200, r.text[:800])
        data = r.json()
        ta = data["a"]["props"].get("wetting_temp_c")
        tb = data["b"]["props"].get("wetting_temp_c")
        self.assertEqual(ta, tb)
        self.assertEqual(ta, 260.0)
        self.assertEqual(data["a"]["props"].get("wetting_temp_basis"), "compare_shared")
        self.assertEqual(data["b"]["props"].get("wetting_temp_basis"), "compare_shared")

    def test_docker_frontend_stage_copies_shared_rules_before_build(self) -> None:
        dockerfile = (_ROOT / "Dockerfile").read_text(encoding="utf-8")
        shared_copy = "COPY shared/ /src/test7/shared/"
        build_command = "RUN npm run build"

        self.assertIn(shared_copy, dockerfile)
        self.assertLess(dockerfile.index(shared_copy), dockerfile.index(build_command))
