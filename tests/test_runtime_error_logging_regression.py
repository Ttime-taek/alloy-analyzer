"""Regression coverage for container-safe runtime exception logging."""

from __future__ import annotations

import logging

from test7.utils import log_exception


# Regression: pre-landing review found error.log was unwritable under USER alloy
# and failures disappeared silently (2026-08-17).
def test_runtime_exception_is_emitted_to_standard_logging(caplog) -> None:
    try:
        raise RuntimeError("wetting prediction failed")
    except RuntimeError as exc:
        with caplog.at_level(logging.ERROR, logger="test7.utils"):
            log_exception("predict_wetting fallback", exc)

    assert "predict_wetting fallback" in caplog.text
    assert "RuntimeError: wetting prediction failed" in caplog.text
