"""Boundary tests — empty, zero, or minimum input returns a well-defined result."""

from bob.models import Feature
from bob.stuck_readiness_decomposer import check_stuck_readiness, mark_pending_decomposition


def make_feature(**kwargs) -> Feature:
    defaults = dict(
        id="feat-001",
        project_id="proj-001",
        name="Test Feature",
        status="ready",
        refinement_attempts=0,
        readiness_score=0.0,
        max_refinement_attempts=5,
        conf_spec_understanding=0.0,
        conf_impl_correctness=0.0,
        conf_test_adequacy=0.0,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestCheckStuckReadinessBoundary:
    def test_zero_attempts_returns_false(self):
        f = make_feature(refinement_attempts=0, readiness_score=0.0)
        assert check_stuck_readiness(f) is False

    def test_exactly_min_attempts_with_zero_readiness(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.0)
        assert check_stuck_readiness(f) is True

    def test_readiness_score_zero_with_one_attempt(self):
        f = make_feature(refinement_attempts=1, readiness_score=0.0)
        assert check_stuck_readiness(f) is False

    def test_readiness_score_exactly_zero_point_eight_boundary(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.8)
        assert check_stuck_readiness(f) is False

    def test_readiness_just_below_threshold(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.799)
        assert check_stuck_readiness(f) is True

    def test_previous_score_zero_and_current_score_zero(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.0)
        assert check_stuck_readiness(f, previous_readiness_score=0.0) is True

    def test_previous_score_equals_current_score(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        assert check_stuck_readiness(f, previous_readiness_score=0.5) is True


class TestMarkPendingDecompositionBoundary:
    def test_feature_with_zero_attempts_still_decomposes(self):
        f = make_feature(refinement_attempts=0, readiness_score=0.0)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_feature_with_minimum_readiness_score(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.0)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_feature_already_in_pending_decomposition(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5, status="pending_decomposition")
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"
