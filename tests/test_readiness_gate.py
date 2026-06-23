"""Tests for bob3.readiness_gate — stuck-readiness decomposition trigger.

Verifies should_trigger_decomposition and mark_pending_decomposition behave
correctly: fire when all three conditions hold, stay silent when any is missing,
and integrate with the run_loop's pending_decomposition transition path.
"""

from __future__ import annotations

import pytest

from bob3.models import Feature
from bob3.readiness_gate import mark_pending_decomposition, should_trigger_decomposition


def make_feature(**kwargs) -> Feature:
    defaults = dict(
        id="feat-rg-001",
        project_id="proj-001",
        name="ReadinessGate Test Feature",
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


class TestShouldTriggerDecompositionHappy:
    def test_all_conditions_met_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is True

    def test_high_attempts_still_triggers(self):
        f = make_feature(refinement_attempts=10, readiness_score=0.50)
        assert should_trigger_decomposition(f, previous_readiness_score=0.50) is True

    def test_no_previous_score_triggers(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.70)
        assert should_trigger_decomposition(f) is True

    def test_previous_score_none_is_no_improvement(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.60)
        assert should_trigger_decomposition(f, previous_readiness_score=None) is True


class TestShouldTriggerDecompositionNotFiring:
    def test_readiness_above_threshold_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.85)
        assert should_trigger_decomposition(f, previous_readiness_score=0.85) is False

    def test_readiness_exactly_at_threshold_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.80)
        assert should_trigger_decomposition(f, previous_readiness_score=0.80) is False

    def test_fewer_than_two_attempts_returns_false(self):
        f = make_feature(refinement_attempts=1, readiness_score=0.65)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is False

    def test_zero_attempts_returns_false(self):
        f = make_feature(refinement_attempts=0, readiness_score=0.65)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is False

    def test_readiness_improved_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.75)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is False

    def test_small_improvement_suppresses_decomposition(self):
        f = make_feature(refinement_attempts=5, readiness_score=0.66)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is False


class TestShouldTriggerDecompositionErrors:
    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            should_trigger_decomposition(f)

    def test_error_message_includes_feature_id(self):
        f = make_feature(id="corrupt-feat-rg-001", refinement_attempts=-3)
        with pytest.raises(ValueError, match="corrupt-feat-rg-001"):
            should_trigger_decomposition(f)

    def test_does_not_silently_return_on_negative_attempts(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError):
            should_trigger_decomposition(f)


class TestMarkPendingDecomposition:
    def test_sets_status_to_pending_decomposition(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_returns_feature_copy_not_mutated(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = mark_pending_decomposition(f)
        assert f.status == "ready"
        assert result.status == "pending_decomposition"

    def test_calls_db_update_when_provided(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        mark_pending_decomposition(f, db_update=fake_db_update)
        assert calls == [(f.id, {"status": "pending_decomposition"})]

    def test_no_db_update_when_not_provided(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            mark_pending_decomposition(f)

    def test_error_includes_feature_id(self):
        f = make_feature(id="bad-feat-rg-002", refinement_attempts=-5)
        with pytest.raises(ValueError, match="bad-feat-rg-002"):
            mark_pending_decomposition(f)

    def test_negative_attempts_does_not_call_db_update(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError):
            mark_pending_decomposition(f, db_update=fake_db_update)

        assert calls == [], "db_update must not be called when ValueError is raised"


class TestRunLoopIntegration:
    """Verify that bob3.run_loop uses the same decomposition logic."""

    def test_run_loop_has_decompose_threshold(self):
        from bob3.orchestrator.run_loop import _DECOMPOSE_READINESS_THRESHOLD
        assert _DECOMPOSE_READINESS_THRESHOLD == 0.80

    def test_run_loop_has_min_attempts(self):
        from bob3.orchestrator.run_loop import _DECOMPOSE_MIN_ATTEMPTS
        assert _DECOMPOSE_MIN_ATTEMPTS == 2

    def test_run_loop_should_decompose_fires_on_same_conditions(self):
        from bob3.orchestrator.run_loop import _should_decompose_instead_of_execute

        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert _should_decompose_instead_of_execute(
            f, previous_readiness_score=0.65
        ) is True

    def test_run_loop_should_decompose_silent_when_improving(self):
        from bob3.orchestrator.run_loop import _should_decompose_instead_of_execute

        f = make_feature(refinement_attempts=2, readiness_score=0.75)
        assert _should_decompose_instead_of_execute(
            f, previous_readiness_score=0.65
        ) is False

    def test_run_loop_transition_sets_pending_decomposition(self):
        from unittest.mock import patch

        from bob3 import db
        from bob3.orchestrator.run_loop import _transition_to_pending_decomposition

        with patch("bob3.db.update_feature") as mock_update:
            f = make_feature(refinement_attempts=2, readiness_score=0.65)
            mock_update.return_value = f.model_copy(
                update={"status": "pending_decomposition"}
            )
            result = _transition_to_pending_decomposition(f)
            mock_update.assert_called_once_with(f.id, status="pending_decomposition")
