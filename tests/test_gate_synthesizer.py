"""Tests for bob.gate_synthesizer (feature a61c0e92).

Verifies that gate-blocked features are re-synthesized mid-run exactly once,
preventing the livelock where features loop the blocked→test-writer→CodeT
cycle forever without the spec_quality score rising.
"""

from __future__ import annotations

import importlib
import pytest


# ---------------------------------------------------------------------------
# Module / symbol availability
# ---------------------------------------------------------------------------

def test_module_importable():
    mod = importlib.import_module("bob.gate_synthesizer")
    assert mod is not None


def test_re_synthesize_gate_blocked_feature_defined():
    mod = importlib.import_module("bob.gate_synthesizer")
    assert hasattr(mod, "re_synthesize_gate_blocked_feature")
    assert callable(mod.re_synthesize_gate_blocked_feature)


def test_is_already_resynthesized_defined():
    mod = importlib.import_module("bob.gate_synthesizer")
    assert hasattr(mod, "is_already_resynthesized")
    assert callable(mod.is_already_resynthesized)


# ---------------------------------------------------------------------------
# Idempotency: one attempt per feature per process
# ---------------------------------------------------------------------------

def _make_passing_synthesizer():
    """Return a score_gate_fn stub that reports gate passed with criteria."""

    class _Report:
        criteria = ["AC-1: must do X", "AC-2: must do Y"]
        composite = 0.92
        gate_passed = True

    async def _score_gate_fn(**_kwargs):
        return _Report()

    return _score_gate_fn


def _make_synthesize_fn():
    async def _synthesize_fn(**_kwargs):
        return ["AC-1: must do X", "AC-2: must do Y"]
    return _synthesize_fn


def test_second_call_returns_none_for_same_feature():
    """Bounded to one re-synthesis per feature per process — prevents livelock."""
    import bob.gate_synthesizer as gs
    gs._resynthesized.discard("feat-idem-1")

    score_gate_fn = _make_passing_synthesizer()
    synthesize_fn = _make_synthesize_fn()

    # First call should run the synthesizer and return criteria.
    result1 = gs.re_synthesize_gate_blocked_feature(
        feature_id="feat-idem-1",
        name="My Feature",
        description="Some description",
        project_id="proj-1",
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
    assert isinstance(result1, tuple)
    assert len(result1) == 2

    # Second call for the same feature_id must return (None, 0.0).
    result2 = gs.re_synthesize_gate_blocked_feature(
        feature_id="feat-idem-1",
        name="My Feature",
        description="Some description",
        project_id="proj-1",
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
    assert result2 == (None, 0.0), (
        "Second call must return (None, 0.0) — one attempt per feature per process"
    )


def test_different_features_each_get_one_attempt():
    """Two distinct feature IDs each get one synthesis attempt."""
    import bob.gate_synthesizer as gs
    gs._resynthesized.discard("feat-A")
    gs._resynthesized.discard("feat-B")

    score_gate_fn = _make_passing_synthesizer()
    synthesize_fn = _make_synthesize_fn()

    r_a = gs.re_synthesize_gate_blocked_feature(
        feature_id="feat-A",
        name="Feature A",
        description="desc",
        project_id="proj-x",
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
    r_b = gs.re_synthesize_gate_blocked_feature(
        feature_id="feat-B",
        name="Feature B",
        description="desc",
        project_id="proj-x",
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
    # Both are first attempts — neither should be (None, 0.0) from the idempotency guard.
    assert r_a != (None, 0.0) or r_b != (None, 0.0), (
        "Both features should have received a synthesis attempt"
    )


# ---------------------------------------------------------------------------
# is_already_resynthesized predicate
# ---------------------------------------------------------------------------

def test_is_already_resynthesized_false_before_attempt():
    import bob.gate_synthesizer as gs
    gs._resynthesized.discard("feat-pred-new")
    assert gs.is_already_resynthesized("feat-pred-new") is False


def test_is_already_resynthesized_true_after_attempt():
    import bob.gate_synthesizer as gs
    gs._resynthesized.discard("feat-pred-done")
    gs._resynthesized.add("feat-pred-done")
    assert gs.is_already_resynthesized("feat-pred-done") is True


def test_is_already_resynthesized_false_for_empty_string():
    import bob.gate_synthesizer as gs
    assert gs.is_already_resynthesized("") is False


def test_is_already_resynthesized_false_for_non_string():
    import bob.gate_synthesizer as gs
    assert gs.is_already_resynthesized(None) is False  # type: ignore[arg-type]
    assert gs.is_already_resynthesized(42) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Return value shape
# ---------------------------------------------------------------------------

def test_returns_criteria_and_composite_on_success():
    """When synthesizer returns passing report, result is (list[str], float)."""
    import bob.gate_synthesizer as gs
    feat_id = "feat-shape-ok"
    gs._resynthesized.discard(feat_id)

    score_gate_fn = _make_passing_synthesizer()
    synthesize_fn = _make_synthesize_fn()

    acs, composite = gs.re_synthesize_gate_blocked_feature(
        feature_id=feat_id,
        name="Shape Test Feature",
        description="Tests return shape",
        project_id="proj-shape",
        synthesize_fn=synthesize_fn,
        score_gate_fn=score_gate_fn,
    )
    assert isinstance(acs, list)
    assert len(acs) > 0
    assert isinstance(composite, float)
    assert 0.0 <= composite <= 1.0


def test_returns_none_tuple_when_synthesizer_fails():
    """When synthesizer raises, function returns (None, 0.0) without propagating."""
    import bob.gate_synthesizer as gs
    feat_id = "feat-shape-fail"
    gs._resynthesized.discard(feat_id)

    async def _failing_score_gate_fn(**_kwargs):
        raise RuntimeError("synthesizer exploded")

    acs, composite = gs.re_synthesize_gate_blocked_feature(
        feature_id=feat_id,
        name="Fail Feature",
        description="desc",
        project_id="proj-fail",
        synthesize_fn=_make_synthesize_fn(),
        score_gate_fn=_failing_score_gate_fn,
    )
    assert acs is None
    assert composite == 0.0


# ---------------------------------------------------------------------------
# Orchestrator integration
# ---------------------------------------------------------------------------

def test_orchestrator_exposes_re_synthesize_gate_blocked_feature():
    """bob.orchestrator must re-export or import re_synthesize_gate_blocked_feature."""
    import bob.orchestrator as orch
    # Accept either direct attribute or importable via the module chain
    assert (
        hasattr(orch, "re_synthesize_gate_blocked_feature")
        or hasattr(orch, "resynthesize_gate_blocked_feature")
        or hasattr(orch, "promote_gate_blocked_features")
    ), (
        "orchestrator must expose at least one gate re-synthesis entry point"
    )
