"""Tests for bob.stuck_readiness_decomposer — check_stuck_readiness and mark_pending_decomposition."""

import pytest

from bob.models import Feature
from bob.stuck_readiness_decomposer import check_stuck_readiness, mark_pending_decomposition


def make_feature(**kwargs) -> Feature:
    defaults = dict(
        id="feat-001",
        project_id="proj-001",
        name="Test Feature",
        status="ready",
        refinement_attempts=2,
        readiness_score=0.5,
        max_refinement_attempts=5,
        conf_spec_understanding=0.5,
        conf_impl_correctness=0.5,
        conf_test_adequacy=0.5,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestCheckStuckReadiness:
    def test_all_conditions_met_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        assert check_stuck_readiness(f) is True

    def test_not_enough_attempts_returns_false(self):
        f = make_feature(refinement_attempts=1, readiness_score=0.5)
        assert check_stuck_readiness(f) is False

    def test_high_readiness_score_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.80)
        assert check_stuck_readiness(f) is False

    def test_readiness_just_below_threshold_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.799)
        assert check_stuck_readiness(f) is True

    def test_no_previous_score_treated_as_no_improvement(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        assert check_stuck_readiness(f, previous_readiness_score=None) is True

    def test_improved_readiness_returns_false(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.6)
        assert check_stuck_readiness(f, previous_readiness_score=0.5) is False

    def test_same_readiness_treated_as_no_improvement(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        assert check_stuck_readiness(f, previous_readiness_score=0.5) is True

    def test_worsened_readiness_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.4)
        assert check_stuck_readiness(f, previous_readiness_score=0.5) is True

    def test_many_attempts_still_detects_stuck(self):
        f = make_feature(refinement_attempts=10, readiness_score=0.3)
        assert check_stuck_readiness(f) is True

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            check_stuck_readiness(f)

    def test_error_message_includes_feature_id(self):
        f = make_feature(id="bad-feat", refinement_attempts=-1)
        with pytest.raises(ValueError, match="bad-feat"):
            check_stuck_readiness(f)


class TestMarkPendingDecomposition:
    def test_sets_status_to_pending_decomposition(self):
        f = make_feature(status="ready")
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_returns_new_feature_object(self):
        f = make_feature(status="ready")
        result = mark_pending_decomposition(f)
        assert result is not f

    def test_original_feature_not_mutated(self):
        f = make_feature(status="ready")
        mark_pending_decomposition(f)
        assert f.status == "ready"

    def test_db_update_called_with_correct_args(self):
        calls = []
        f = make_feature()
        mark_pending_decomposition(f, db_update=lambda fid, **kw: calls.append((fid, kw)))
        assert calls == [("feat-001", {"status": "pending_decomposition"})]

    def test_db_update_not_called_when_none(self):
        f = make_feature()
        result = mark_pending_decomposition(f, db_update=None)
        assert result.status == "pending_decomposition"

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            mark_pending_decomposition(f)

    def test_error_message_includes_feature_id(self):
        f = make_feature(id="corrupt-feat", refinement_attempts=-1)
        with pytest.raises(ValueError, match="corrupt-feat"):
            mark_pending_decomposition(f)

    def test_zero_readiness_feature_gets_marked(self):
        f = make_feature(readiness_score=0.0)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"
