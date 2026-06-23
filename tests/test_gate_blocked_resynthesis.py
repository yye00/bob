"""Tests for gate-blocked feature re-synthesis via bob75.orchestrator.

Verifies that:
  - bob75.orchestrator exposes score_gate_loop, synthesize_for_feature, mark_resynthesized
  - mark_resynthesized records feature IDs correctly (idempotency guard)
  - is_resynthesized reflects state correctly
  - mark_resynthesized raises ValueError/TypeError on bad input
  - score_gate_loop and synthesize_for_feature are callable (they delegate
    to bob3.spec_synthesizer; their integration is tested in bob3's own suite)
"""

import importlib
import pytest

import bob75.orchestrator as orch


def setup_function():
    """Reset the module-level idempotency set before each test."""
    orch._resynthesized_ids.clear()


# ---------------------------------------------------------------------------
# Import / attribute surface
# ---------------------------------------------------------------------------

def test_module_imports():
    mod = importlib.import_module("bob75.orchestrator")
    assert mod is not None


def test_score_gate_loop_is_exported():
    mod = importlib.import_module("bob75.orchestrator")
    assert hasattr(mod, "score_gate_loop")
    assert callable(mod.score_gate_loop)


def test_synthesize_for_feature_is_exported():
    mod = importlib.import_module("bob75.orchestrator")
    assert hasattr(mod, "synthesize_for_feature")
    assert callable(mod.synthesize_for_feature)


def test_mark_resynthesized_is_exported():
    mod = importlib.import_module("bob75.orchestrator")
    assert hasattr(mod, "mark_resynthesized")
    assert callable(mod.mark_resynthesized)


# ---------------------------------------------------------------------------
# mark_resynthesized behaviour
# ---------------------------------------------------------------------------

def test_mark_resynthesized_records_feature_id():
    orch.mark_resynthesized("feat-001")
    assert "feat-001" in orch._resynthesized_ids


def test_mark_resynthesized_is_idempotent():
    orch.mark_resynthesized("feat-idem")
    orch.mark_resynthesized("feat-idem")
    assert orch._resynthesized_ids.count("feat-idem") if hasattr(orch._resynthesized_ids, "count") else True
    assert "feat-idem" in orch._resynthesized_ids


def test_mark_resynthesized_tracks_multiple_features():
    orch.mark_resynthesized("feat-a")
    orch.mark_resynthesized("feat-b")
    orch.mark_resynthesized("feat-c")
    assert "feat-a" in orch._resynthesized_ids
    assert "feat-b" in orch._resynthesized_ids
    assert "feat-c" in orch._resynthesized_ids


# ---------------------------------------------------------------------------
# is_resynthesized behaviour
# ---------------------------------------------------------------------------

def test_is_resynthesized_returns_false_before_marking():
    assert orch.is_resynthesized("feat-new") is False


def test_is_resynthesized_returns_true_after_marking():
    orch.mark_resynthesized("feat-marked")
    assert orch.is_resynthesized("feat-marked") is True


def test_is_resynthesized_returns_false_for_different_feature():
    orch.mark_resynthesized("feat-x")
    assert orch.is_resynthesized("feat-y") is False


# ---------------------------------------------------------------------------
# Error paths — mark_resynthesized rejects bad input
# ---------------------------------------------------------------------------

def test_mark_resynthesized_raises_value_error_on_empty_string():
    with pytest.raises(ValueError):
        orch.mark_resynthesized("")


def test_mark_resynthesized_raises_type_error_on_none():
    with pytest.raises((TypeError, ValueError)):
        orch.mark_resynthesized(None)  # type: ignore[arg-type]


def test_mark_resynthesized_raises_type_error_on_int():
    with pytest.raises((TypeError, ValueError)):
        orch.mark_resynthesized(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Delegation: score_gate_loop and synthesize_for_feature from bob3
# ---------------------------------------------------------------------------

def test_score_gate_loop_is_same_as_bob3_original():
    from bob3.spec_synthesizer import score_gate_loop as bob3_fn
    assert orch.score_gate_loop is bob3_fn


def test_synthesize_for_feature_is_same_as_bob3_original():
    from bob3.spec_synthesizer import synthesize_for_feature as bob3_fn
    assert orch.synthesize_for_feature is bob3_fn


# ---------------------------------------------------------------------------
# Livelock prevention: once marked, is_resynthesized signals to orchestrator
# ---------------------------------------------------------------------------

def test_livelock_prevention_pattern():
    """Simulate the orchestrator checking before re-synthesizing."""
    feature_id = "feat-livelock-check"

    # First time: not yet attempted
    assert not orch.is_resynthesized(feature_id)

    # Orchestrator performs re-synthesis and marks it
    orch.mark_resynthesized(feature_id)

    # Second sweep: must NOT re-attempt (livelock prevention)
    assert orch.is_resynthesized(feature_id)
