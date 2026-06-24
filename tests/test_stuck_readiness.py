"""Tests for stuck_readiness module — should_decompose and mark_pending_decomposition.

Tests the bob74.stuck_readiness module which provides the stuck-readiness
decomposition trigger to kill the eval-demotion treadmill.
"""

import pytest

from bob3.models import Feature
from bob74.stuck_readiness import mark_pending_decomposition, should_decompose


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


class TestShouldDecompose:
    def test_all_conditions_met_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert should_decompose(f, previous_readiness_score=0.65) is True

    def test_readiness_above_threshold_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.85)
        assert should_decompose(f, previous_readiness_score=0.85) is False

    def test_readiness_exactly_at_threshold_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.80)
        assert should_decompose(f, previous_readiness_score=0.80) is False

    def test_fewer_than_two_attempts_returns_false(self):
        f = make_feature(refinement_attempts=0, readiness_score=0.65)
        assert should_decompose(f, previous_readiness_score=0.65) is False

        f = make_feature(refinement_attempts=1, readiness_score=0.65)
        assert should_decompose(f, previous_readiness_score=0.65) is False

    def test_readiness_improved_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.75)
        assert should_decompose(f, previous_readiness_score=0.65) is False

    def test_no_previous_score_treated_as_no_improvement(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert should_decompose(f, previous_readiness_score=None) is True

    def test_score_decreased_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.55)
        assert should_decompose(f, previous_readiness_score=0.65) is True

    def test_many_attempts_still_triggers(self):
        f = make_feature(refinement_attempts=10, readiness_score=0.50)
        assert should_decompose(f, previous_readiness_score=0.50) is True

    def test_default_previous_score_triggers_when_stuck(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert should_decompose(f) is True

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1, readiness_score=0.65)
        with pytest.raises(ValueError, match="negative"):
            should_decompose(f)


class TestMarkPendingDecomposition:
    def test_sets_status_to_pending_decomposition(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_original_feature_not_mutated(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65, status="ready")
        _ = mark_pending_decomposition(f)
        assert f.status == "ready"

    def test_db_update_called_with_correct_args(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(id="feat-123", refinement_attempts=2, readiness_score=0.65)
        mark_pending_decomposition(f, db_update=fake_db_update)
        assert len(calls) == 1
        assert calls[0] == ("feat-123", {"status": "pending_decomposition"})

    def test_no_db_update_when_not_provided(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1, readiness_score=0.65)
        with pytest.raises(ValueError, match="negative"):
            mark_pending_decomposition(f)

    def test_returns_feature_with_other_fields_unchanged(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.55, name="My Feature")
        result = mark_pending_decomposition(f)
        assert result.name == "My Feature"
        assert result.refinement_attempts == 3
        assert result.readiness_score == 0.55
