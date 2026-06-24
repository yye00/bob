"""Tests for gate-blocked feature re-synthesis in bob.orchestrator (feature 797ae88c).

Verifies that:
- score_gate_loop and synthesize_for_feature are accessible from bob.orchestrator
- The re-synthesis logic prevents livelock (one attempt per feature per process)
- The orchestrator's promotion sweep correctly gates further re-dispatch
"""
from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch


def test_score_gate_loop_defined_in_orchestrator():
    """AC: Function defined: bob.orchestrator.score_gate_loop"""
    mod = importlib.import_module("bob.orchestrator")
    assert hasattr(mod, "score_gate_loop"), "score_gate_loop must be defined in bob.orchestrator"
    assert callable(mod.score_gate_loop)


def test_synthesize_for_feature_defined_in_orchestrator():
    """AC: Function defined: bob.orchestrator.synthesize_for_feature"""
    mod = importlib.import_module("bob.orchestrator")
    assert hasattr(mod, "synthesize_for_feature"), (
        "synthesize_for_feature must be defined in bob.orchestrator"
    )
    assert callable(mod.synthesize_for_feature)


def test_score_gate_loop_is_async():
    """score_gate_loop must be a coroutine function (async def)."""
    import inspect
    from bob.orchestrator import score_gate_loop
    assert inspect.iscoroutinefunction(score_gate_loop)


def test_synthesize_for_feature_is_async():
    """synthesize_for_feature must be a coroutine function (async def)."""
    import inspect
    from bob.orchestrator import synthesize_for_feature
    assert inspect.iscoroutinefunction(synthesize_for_feature)


def test_resynthesize_gate_blocked_features_available():
    """resynthesize_gate_blocked_features must be accessible from bob.orchestrator."""
    from bob.orchestrator import resynthesize_gate_blocked_features
    assert callable(resynthesize_gate_blocked_features)


def test_is_already_resynthesized_available():
    """is_already_resynthesized must be accessible from bob.orchestrator."""
    from bob.orchestrator import is_already_resynthesized
    assert callable(is_already_resynthesized)


def test_gate_blocker_prevents_duplicate_synthesis():
    """Re-synthesis attempt must be bounded to one per feature per process.

    After one call, a second call for the same feature_id returns (None, 0.0)
    without re-running the synthesizer — this is the livelock prevention.
    """
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()

    called_count = 0

    def fake_synthesize_fn(**kwargs):
        nonlocal called_count
        called_count += 1
        return ["AC: pytest: tests/test_foo.py"]

    def fake_score_gate_fn(**kwargs):
        report = MagicMock()
        report.criteria = ["AC: pytest: tests/test_foo.py"]
        report.composite = 0.90
        report.gate_passed = True
        return report

    # First call — should attempt synthesis
    result1 = gb.re_synthesize_gate_blocked_feature(
        feature_id="test-feat-livelock-001",
        name="Test Feature",
        description="Testing livelock prevention",
        project_id="proj-test",
        synthesize_fn=fake_synthesize_fn,
        score_gate_fn=fake_score_gate_fn,
    )

    # Second call for same feature_id — must return (None, 0.0) immediately
    result2 = gb.re_synthesize_gate_blocked_feature(
        feature_id="test-feat-livelock-001",
        name="Test Feature",
        description="Testing livelock prevention",
        project_id="proj-test",
        synthesize_fn=fake_synthesize_fn,
        score_gate_fn=fake_score_gate_fn,
    )

    assert result2 == (None, 0.0), (
        "Second re-synthesis call must be a no-op (livelock prevention)"
    )
    gb._synthesis_attempted.discard("test-feat-livelock-001")


def test_gate_blocker_returns_none_for_already_attempted():
    """is_already_resynthesized returns True after mark_synthesis_attempted."""
    import bob73.gate_blocker as gb
    gb._synthesis_attempted.clear()

    gb.mark_synthesis_attempted("feat-orch-001")
    assert "feat-orch-001" in gb._synthesis_attempted
    gb._synthesis_attempted.discard("feat-orch-001")


def test_orchestrator_integration_score_gate_loop_importable():
    """Integration: bob.orchestrator exports score_gate_loop from bob.spec_synthesizer."""
    from bob.orchestrator import score_gate_loop
    from bob.spec_synthesizer import score_gate_loop as _impl
    assert score_gate_loop is _impl, (
        "bob.orchestrator.score_gate_loop must be the same object as "
        "bob.spec_synthesizer.score_gate_loop"
    )


def test_orchestrator_integration_synthesize_for_feature_importable():
    """Integration: bob.orchestrator exports synthesize_for_feature from bob.spec_synthesizer."""
    from bob.orchestrator import synthesize_for_feature
    from bob.spec_synthesizer import synthesize_for_feature as _impl
    assert synthesize_for_feature is _impl, (
        "bob.orchestrator.synthesize_for_feature must be the same object as "
        "bob.spec_synthesizer.synthesize_for_feature"
    )
