# -*- coding: utf-8 -*-
import os

import pytest

from melting_ensemble import clear_ensemble_cache, get_ensemble_profile


def test_default_profile_keys():
    clear_ensemble_cache()
    p = get_ensemble_profile("SAC")
    assert p["l2_simple_mult"] == 3.0
    assert p["l4_if_l2_weak_mult"] == 0.3
    assert "l4_external_weight" in p


def test_family_override_from_env_json(tmp_path, monkeypatch):
    cfg = tmp_path / "m.json"
    cfg.write_text(
        '{"default": {"l2_simple_mult": 9.9}, "families": {"SnBi": {"l3_knn_default": 0.5}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("MELTING_ENSEMBLE_CONFIG", str(cfg))
    clear_ensemble_cache()
    try:
        assert get_ensemble_profile("other")["l2_simple_mult"] == 9.9
        assert get_ensemble_profile("SnBi")["l3_knn_default"] == 0.5
        assert get_ensemble_profile("SnBi")["l2_simple_mult"] == 9.9
    finally:
        monkeypatch.delenv("MELTING_ENSEMBLE_CONFIG", raising=False)
        clear_ensemble_cache()
