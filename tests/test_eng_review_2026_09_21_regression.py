"""Regression coverage for the 2026-09-21 gstack-plan-eng-review fix.

_explanation_requests was a defaultdict(deque) that never dropped a client
key once created, even after that client's window fully expired — a slow
memory leak on a public web app where visitor IPs are diverse. The fix adds
a periodic sweep (every _EXPLANATION_PRUNE_INTERVAL calls) that trims and
drops stale, empty client queues while leaving active ones untouched.
"""
from __future__ import annotations

from unittest.mock import patch

import api_server as api_mod


def test_explanation_quota_prunes_stale_client_keys() -> None:
    times = iter([0.0, 1.0, 15.0, 20.0])

    with patch.object(api_mod, "_EXPLANATION_RATE_LIMIT", 100), patch.object(
        api_mod, "_EXPLANATION_GLOBAL_RATE_LIMIT", 1000
    ), patch.object(api_mod, "_EXPLANATION_RATE_WINDOW_SEC", 10), patch.object(
        api_mod, "_EXPLANATION_PRUNE_INTERVAL", 4
    ), patch.object(
        api_mod, "_explanation_calls_since_prune", 0
    ), patch.dict(
        api_mod._explanation_requests, clear=True
    ), patch.object(
        api_mod.time, "monotonic", side_effect=lambda: next(times)
    ):
        # t=0: "a" 호출 — 곧 만료될 예정
        assert api_mod._consume_explanation_quota("client_a")[0] is True
        # t=1: "b" 호출 — 역시 곧 만료될 예정
        assert api_mod._consume_explanation_quota("client_b")[0] is True
        # t=15: "d" 호출 — 윈도우(10초) 안에 있어 스윕 시점에도 살아있어야 함
        assert api_mod._consume_explanation_quota("client_d")[0] is True
        # t=20: "c" 호출 — 이번이 4번째 호출이라 프루닝 스윕이 트리거됨.
        #       cutoff = 20 - 10 = 10 이므로 a(t=0), b(t=1)는 만료, d(t=15)는 아직 유효.
        assert api_mod._consume_explanation_quota("client_c")[0] is True

        keys = set(api_mod._explanation_requests.keys())

    # 만료된 채 재호출이 없던 클라이언트 키는 사전에서 제거되어야 함(메모리 누수 방지).
    assert "client_a" not in keys
    assert "client_b" not in keys
    # 아직 윈도우 안에 있는 클라이언트와 이번 호출의 클라이언트, 전역 키는 남아 있어야 함.
    assert "client_d" in keys
    assert "client_c" in keys
    assert api_mod._GLOBAL_EXPLANATION_KEY in keys


def test_explanation_quota_prune_does_not_touch_active_current_caller() -> None:
    """스윕 트리거를 유발한 호출 자신의 client_key 와 전역 키는 항상 정상 동작해야 함
    (스윕 루프가 실수로 자기 자신을 건드려 방금 넣은 항목을 지우면 안 됨)."""
    times = iter([0.0, 0.0, 0.0, 0.0])

    with patch.object(api_mod, "_EXPLANATION_RATE_LIMIT", 100), patch.object(
        api_mod, "_EXPLANATION_GLOBAL_RATE_LIMIT", 1000
    ), patch.object(api_mod, "_EXPLANATION_RATE_WINDOW_SEC", 10), patch.object(
        api_mod, "_EXPLANATION_PRUNE_INTERVAL", 1
    ), patch.object(
        api_mod, "_explanation_calls_since_prune", 0
    ), patch.dict(
        api_mod._explanation_requests, clear=True
    ), patch.object(
        api_mod.time, "monotonic", side_effect=lambda: next(times)
    ):
        # PRUNE_INTERVAL=1 이므로 매 호출마다 스윕이 트리거됨. 같은 client_key 로
        # 연속 호출해도 자기 자신의 큐 항목이 사라지면 안 됨(카운트가 정상적으로 쌓여야 함).
        ok1, _ = api_mod._consume_explanation_quota("solo_client")
        ok2, _ = api_mod._consume_explanation_quota("solo_client")
        assert ok1 is True
        assert ok2 is True
        assert len(api_mod._explanation_requests["solo_client"]) == 2
        assert len(api_mod._explanation_requests[api_mod._GLOBAL_EXPLANATION_KEY]) == 2
