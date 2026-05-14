# -*- coding: utf-8 -*-
"""SOLDER_PROPERTIES_DB 조회 헬퍼."""
from __future__ import annotations

from .SOLDER_PROPERTIES_DB import SOLDER_PROPERTIES_DB


def rows_for_alloy(alloy: str) -> list[dict]:
    """주어진 BD 합금명과 일치하는 물성 시험 행만 반환한다."""
    return [r for r in SOLDER_PROPERTIES_DB if r["alloy"] == alloy]


def unique_alloy_names() -> list[str]:
    """물성 DB에 등장하는 합금명을 중복 없이 정렬해 반환한다."""
    return sorted({r["alloy"] for r in SOLDER_PROPERTIES_DB})
