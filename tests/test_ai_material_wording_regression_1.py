"""Scientific explanation safeguards for AI-provided material wording."""

from test7.analyzer import _imc_line_to_plain_korean, _mentions_unentered_element


def test_bismuth_composition_rejects_ai_arsenic_hallucination():
    # Regression: QA-002 — a Bi alloy was described as containing arsenic (As).
    # Found by /qa on 2026-08-12
    # Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
    norm = {"Sn": 80.2, "Ag": 1.0, "Cu": 0.8, "In": 8.0, "Bi": 10.0}

    assert _mentions_unentered_element(
        "비소는 녹는 시작점을 낮춰 저온에서도 충분히 흐르게 한다.", norm
    )
    assert not _mentions_unentered_element(
        "비스무스(Bi)는 녹는 온도를 낮출 수 있습니다.", norm
    )


def test_ag3sn_uses_controlled_noncontradictory_wording():
    # Regression: QA-002 — Ag3Sn was called both a hard and a weak layer.
    # Found by /qa on 2026-08-12
    # Report: .gstack/qa-reports/qa-report-alloy-analyzer-vercel-app-2026-08-12.md
    text = "은(Ag)과 주석이 만나 약한 층(약칭: Ag3Sn)이 형성될 수 있습니다."

    assert _imc_line_to_plain_korean(text) == "은과 주석이 만나 생기는 단단한 층(약칭: Ag3Sn)"

