from __future__ import annotations

from test7.ai_engine import AIEngine


# Regression: ISSUE-004 — malformed remote JSON retried the full AI fallback chain
# Found by /qa on 2026-07-22
# Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-07-22.md
def test_malformed_remote_analysis_falls_back_without_a_second_ai_call() -> None:
    engine = AIEngine.__new__(AIEngine)
    engine.available = True
    engine._cerebras = None
    engine.usage_stats = {}

    prompts: list[str] = []
    engine.ask = lambda prompt: prompts.append(prompt) or "not valid json"
    engine._collect_literature_lines = lambda *_args, **_kwargs: []
    local_fallback = {
        "phase": "local phase",
        "imc": ["local imc"],
        "roles": "local roles",
        "dopant": "local dopant",
        "summary": "local summary",
        "sources": [],
        "ai_used_this_request": False,
    }
    engine._build_local_fallback = lambda *_args, **_kwargs: local_fallback

    result = engine.get_full_analysis(
        {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
        "Sn96.5%, Ag3.0%, Cu0.5%",
        {
            "norm": {"Sn": 96.5, "Ag": 3.0, "Cu": 0.5},
            "best": {"name": "SAC305", "solidus": 217.0, "liquidus": 220.0},
            "score": 0.0,
        },
        [],
        mode="eng",
        literature_mode="fast",
    )

    assert result is local_fallback
    assert len(prompts) == 1
    assert engine.usage_stats["full_analysis_fallbacks"] == 1
