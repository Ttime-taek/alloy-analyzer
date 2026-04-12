"""
Lightweight regression checks for alloy predictor core paths.

Usage:
    python regression_check.py
    python -m test7.regression_check
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Dict, List


if __package__ in (None, ""):
    # direct run: python test7/regression_check.py
    import pathlib

    ROOT = pathlib.Path(__file__).resolve().parent
    sys.path.insert(0, str(ROOT.parent))
    from test7.analyzer import AlloyAnalyzer  # type: ignore
    from test7.solder_db import SOLDER_DB  # type: ignore
else:
    from .analyzer import AlloyAnalyzer
    from .solder_db import SOLDER_DB


class DummyAI:
    available = False
    status_detail = "dummy"

    def get_full_analysis(self, norm, comp_str, result, knn, mode="eng", literature_mode="fast"):
        return {
            "phase": "dummy_phase",
            "imc": ["dummy_imc"],
            "roles": "dummy_roles",
            "dopant": "dummy_dopant",
            "summary": "dummy_summary",
            "sources": [],
        }


@dataclass
class GoldenCase:
    name: str
    comp: Dict[str, float]
    expect_family: str


GOLDEN_CASES: List[GoldenCase] = [
    GoldenCase("SAC305", {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5}, "SAC"),
    GoldenCase("SnBi25Ag1", {"Sn": 74.0, "Bi": 25.0, "Ag": 1.0}, "SnBi"),
    GoldenCase("SnBi_eutectic", {"Sn": 42.0, "Bi": 58.0}, "SnBi"),
    GoldenCase("SnIn_eutectic", {"Sn": 52.0, "In": 48.0}, "SnIn"),
    GoldenCase("SnCu_eutectic", {"Sn": 99.3, "Cu": 0.7}, "SnCu"),
    GoldenCase("SnZn9", {"Sn": 91.0, "Zn": 9.0}, "SnZn"),
    GoldenCase("SnPb63_37", {"Sn": 63.0, "Pb": 37.0}, "SnPb"),
    GoldenCase("SnSb10", {"Sn": 90.0, "Sb": 10.0}, "SnSb"),
]


def _assert(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def run_analyzer_regression() -> None:
    analyzer = AlloyAnalyzer(SOLDER_DB, ai_engine=DummyAI())
    for case in GOLDEN_CASES:
        logs = []
        out = analyzer.analyze_all(case.comp, mode="eng", progress_cb=lambda p, m: logs.append((p, m)))
        _assert(isinstance(out, dict), f"{case.name}: output is not dict")

        md = out.get("melting_detail") or {}
        fam = md.get("family")
        _assert(fam == case.expect_family, f"{case.name}: family mismatch ({fam} != {case.expect_family})")

        s = float(out.get("solidus", 0.0) or 0.0)
        l = float(out.get("liquidus", 0.0) or 0.0)
        p = float(out.get("peak", 0.0) or 0.0)
        _assert(s <= l <= p, f"{case.name}: temperature invariant violated (s={s}, l={l}, p={p})")

        c = float(out.get("confidence", 0.0) or 0.0)
        co = float(out.get("confidence_overall", 0.0) or 0.0)
        _assert(0.0 <= c <= 100.0, f"{case.name}: confidence out of range ({c})")
        _assert(0.0 <= co <= 100.0, f"{case.name}: confidence_overall out of range ({co})")

        _assert("evidence" in out and isinstance(out["evidence"], dict), f"{case.name}: evidence missing")
        _assert("knn" in out and isinstance(out["knn"], list), f"{case.name}: knn missing")
        _assert(out.get("ai_summary") == "dummy_summary", f"{case.name}: ai_summary mismatch")

        # progress callback should emit multiple step messages
        _assert(len(logs) >= 5, f"{case.name}: progress steps too few ({len(logs)})")


def run_contract_regression() -> None:
    # verify key fields expected by web UI/API serialization
    try:
        if __package__ in (None, ""):
            from test7.api_server import AnalysisResponse  # type: ignore
        else:
            from .api_server import AnalysisResponse  # type: ignore
    except Exception as e:
        raise AssertionError(f"api_server import failed: {e}") from e

    fields = getattr(AnalysisResponse, "model_fields", {})
    for key in (
        "ai_mode",
        "ai_status_detail",
        "ai_usage_snapshot",
        "confidence_overall",
        "evidence",
    ):
        _assert(key in fields, f"AnalysisResponse missing field: {key}")


def run_compare_api_regression() -> None:
    """POST /api/compare 스모크 (DummyAI로 분석기 교체, literature_mode 포함)."""
    try:
        from fastapi.testclient import TestClient
    except ImportError as e:
        raise AssertionError(
            "compare API regression needs httpx (FastAPI TestClient). "
            "Install: pip install httpx"
        ) from e

    if __package__ in (None, ""):
        import test7.api_server as api_mod  # type: ignore
    else:
        from . import api_server as api_mod

    saved: Any = api_mod._analyzer
    try:
        api_mod._analyzer = AlloyAnalyzer(SOLDER_DB, ai_engine=DummyAI())
        client = TestClient(api_mod.app)
        r = client.post(
            "/api/compare",
            json={
                "comp_a": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
                "comp_b": {"Sn": 50.0, "Bi": 50.0},
                "literature_mode": "deep",
            },
        )
        _assert(r.status_code == 200, f"compare expected 200 got {r.status_code}: {r.text}")
        data = r.json()
        _assert("a" in data and "b" in data, "compare response missing a/b")
        for side in ("a", "b"):
            _assert("solidus" in data[side], f"compare {side} missing solidus")
            _assert("name" in data[side], f"compare {side} missing name")
        r_bad = client.post(
            "/api/compare",
            json={"comp_a": {}, "comp_b": {"Sn": 50.0, "Bi": 50.0}},
        )
        _assert(r_bad.status_code == 422, f"empty comp_a expected 422 got {r_bad.status_code}")
    finally:
        api_mod._analyzer = saved


def run_about_api_regression() -> None:
    try:
        from fastapi.testclient import TestClient
    except ImportError as e:
        raise AssertionError(
            "about API regression needs httpx (FastAPI TestClient). "
            "Install: pip install httpx"
        ) from e

    if __package__ in (None, ""):
        import test7.api_server as api_mod  # type: ignore
    else:
        from . import api_server as api_mod

    client = TestClient(api_mod.app)
    r = client.get("/api/about")
    _assert(r.status_code == 200, f"/api/about expected 200 got {r.status_code}: {r.text}")
    data = r.json()
    for key in ("product", "version", "tagline", "methodology", "data_sources", "disclaimer"):
        _assert(key in data, f"/api/about missing key: {key}")
    _assert(isinstance(data.get("methodology"), list), "about.methodology must be list")
    _assert(len(data.get("methodology") or []) >= 1, "about.methodology empty")


def main() -> int:
    checks = [
        ("analyzer regression", run_analyzer_regression),
        ("api contract regression", run_contract_regression),
        ("compare API regression", run_compare_api_regression),
        ("about API regression", run_about_api_regression),
    ]
    failed = []
    for title, fn in checks:
        try:
            fn()
            print(f"[PASS] {title}")
        except Exception as e:
            failed.append((title, str(e)))
            print(f"[FAIL] {title}: {e}")

    if failed:
        print("\nRegression check failed:")
        for title, msg in failed:
            print(f"- {title}: {msg}")
        return 1
    print("\nRegression check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

