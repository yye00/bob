"""Tests that the default concurrency cap is 3.

AC: pytest: tests/test_dispatch_concurrency_default_three.py
"""

from __future__ import annotations

import unittest.mock as mock
import types

import pytest

from bob3.orchestrator.run_loop import (
    _resolve_max_concurrent_features,
    _DEFAULT_MAX_CONCURRENT_FEATURES,
    dispatch_up_to_concurrency,
    current_concurrency_slots,
)


def test_default_max_concurrent_features_constant_is_three():
    """The module-level default constant is 3."""
    assert _DEFAULT_MAX_CONCURRENT_FEATURES == 3


def test_resolve_max_concurrent_features_returns_three_by_default(monkeypatch):
    """_resolve_max_concurrent_features returns 3 when env var is absent."""
    monkeypatch.delenv("BOB3_MAX_CONCURRENT_FEATURES", raising=False)
    assert _resolve_max_concurrent_features() == 3


def test_orchestration_loop_default_concurrency_is_one_for_backward_compat():
    """OrchestrationLoop still defaults max_concurrent_features=1 for backward compat.

    The env-var default (3) is used when operators want parallel dispatch;
    the class constructor default stays at 1 to avoid breaking existing callers
    that don't explicitly set the parameter.
    """
    from bob3.orchestrator.run_loop import OrchestrationLoop
    with mock.patch("bob3.orchestrator.run_loop.db") as mock_db:
        mock_db.get_project.return_value = mock.MagicMock(total_cost_usd=0.0, max_cost_usd=None)
        loop = OrchestrationLoop(project_id="proj-default")
    assert loop.max_concurrent_features == 1


def test_current_concurrency_slots_with_default_cap_three():
    """current_concurrency_slots reports correct open slots for cap=3."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 3

    assert current_concurrency_slots(loop, active_feature_ids=set()) == 3
    assert current_concurrency_slots(loop, active_feature_ids={"a"}) == 2
    assert current_concurrency_slots(loop, active_feature_ids={"a", "b"}) == 1
    assert current_concurrency_slots(loop, active_feature_ids={"a", "b", "c"}) == 0


def _make_feature(fid: str):
    f = types.SimpleNamespace()
    f.id = fid
    f.status = "ready"
    return f


def test_dispatch_up_to_concurrency_with_cap_three_fills_three(monkeypatch):
    """dispatch_up_to_concurrency with cap=3 claims up to 3 features."""
    loop = mock.MagicMock()
    loop.max_concurrent_features = 3
    loop.project_id = "proj-default-3"
    ready = [_make_feature(f"feat-{i}") for i in range(5)]
    loop.find_next_ready_feature = mock.MagicMock(side_effect=list(ready) + [None])

    with mock.patch("bob3.orchestrator.run_loop.db") as mock_db:
        mock_db.update_feature = mock.MagicMock()
        claimed = dispatch_up_to_concurrency(loop, active_feature_ids=set())

    assert len(claimed) == 3


def test_dispatch_up_to_concurrency_with_env_var_override(monkeypatch):
    """BOB3_MAX_CONCURRENT_FEATURES=5 is honoured via _resolve_max_concurrent_features."""
    monkeypatch.setenv("BOB3_MAX_CONCURRENT_FEATURES", "5")
    assert _resolve_max_concurrent_features() == 5
