"""Tests for stuck_readiness_decomposition_trigger_kill_eval_demotion_treadmill."""

import pytest

from bob.models import Feature
from bob.stuck_readiness_decomposition_trigger_kill_eval_demotion_treadmill import (
    stuck_readiness_decomposition_trigger_kill_eval_demotion_treadmill,
)


def make_feature(**kwargs) -> Feature:
    defaults = dict(
        id="feat-001",
        project_id="proj-001",
        name="Test Feature",
        status="ready",
        refinement_attempts=2,
        readiness_score=0.65,
        max_refinement_attempts=5,
        conf_spec_understanding=0.65,
        conf_impl_correctness=0.65,
        conf_test_adequacy=0.65,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


def test_stuck_readiness_decomposition_trigger_kill_eval_demotion_treadmill():
    """Core acceptance-criteria test: validates all decision branches."""
    fn = stuck_readiness_decomposition_trigger_kill_eval_demotion_treadmill

    # All three conditions met → decompose
    f = make_feature(refinement_attempts=2, readiness_score=0.65)
    assert fn(f, previous_readiness_score=0.65) == "decompose"

    # Readiness above threshold → execute
    f = make_feature(refinement_attempts=2, readiness_score=0.85)
    assert fn(f, previous_readiness_score=0.85) == "execute"

    # Readiness exactly at threshold → execute (not strictly below)
    f = make_feature(refinement_attempts=2, readiness_score=0.80)
    assert fn(f, previous_readiness_score=0.80) == "execute"

    # Fewer than 2 attempts → execute
    f = make_feature(refinement_attempts=0, readiness_score=0.65)
    assert fn(f, previous_readiness_score=0.65) == "execute"

    f = make_feature(refinement_attempts=1, readiness_score=0.65)
    assert fn(f, previous_readiness_score=0.65) == "execute"

    # Readiness improved → execute
    f = make_feature(refinement_attempts=2, readiness_score=0.75)
    assert fn(f, previous_readiness_score=0.65) == "execute"

    # No previous score → treat as no improvement → decompose
    f = make_feature(refinement_attempts=2, readiness_score=0.65)
    assert fn(f, previous_readiness_score=None) == "decompose"

    # Score decreased → decompose
    f = make_feature(refinement_attempts=2, readiness_score=0.55)
    assert fn(f, previous_readiness_score=0.65) == "decompose"

    # 3 attempts → decompose
    f = make_feature(refinement_attempts=3, readiness_score=0.50)
    assert fn(f, previous_readiness_score=0.50) == "decompose"

    # Negative attempts → ValueError with "negative" in message
    f = make_feature(refinement_attempts=-1, readiness_score=0.65)
    with pytest.raises(ValueError, match="negative"):
        fn(f, previous_readiness_score=0.65)

    # Default previous_readiness_score=None → decompose when stuck
    f = make_feature(refinement_attempts=2, readiness_score=0.65)
    assert fn(f) == "decompose"

    # High readiness with default → execute
    f = make_feature(refinement_attempts=2, readiness_score=0.90)
    assert fn(f) == "execute"
