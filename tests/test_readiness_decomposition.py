"""Tests for bob3.readiness_decomposition — stuck-readiness decomposition trigger."""

import pytest

from bob3.models import Feature
from bob3.readiness_decomposition import (
    mark_pending_decomposition,
    should_trigger_decomposition,
)


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


class TestShouldTriggerDecomposition:
    def test_returns_false_when_attempts_below_threshold(self):
        f = make_feature(refinement_attempts=1, readiness_score=0.3)
        assert should_trigger_decomposition(f) is False

    def test_returns_false_when_readiness_meets_threshold(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.80)
        assert should_trigger_decomposition(f) is False

    def test_returns_false_when_readiness_above_threshold(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.90)
        assert should_trigger_decomposition(f) is False

    def test_returns_true_when_all_conditions_met_no_prior_score(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        assert should_trigger_decomposition(f) is True

    def test_returns_true_when_score_equals_previous_score(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        assert should_trigger_decomposition(f, previous_readiness_score=0.5) is True

    def test_returns_true_when_score_decreased(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.4)
        assert should_trigger_decomposition(f, previous_readiness_score=0.6) is True

    def test_returns_false_when_score_improved(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.6)
        assert should_trigger_decomposition(f, previous_readiness_score=0.4) is False

    def test_raises_value_error_on_negative_attempts(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            should_trigger_decomposition(f)

    def test_error_message_includes_feature_id(self):
        f = make_feature(id="bad-feat-42", refinement_attempts=-1)
        with pytest.raises(ValueError, match="bad-feat-42"):
            should_trigger_decomposition(f)

    def test_exactly_two_attempts_just_below_threshold_triggers(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.799)
        assert should_trigger_decomposition(f) is True

    def test_zero_attempts_never_triggers(self):
        f = make_feature(refinement_attempts=0, readiness_score=0.0)
        assert should_trigger_decomposition(f) is False


class TestMarkPendingDecomposition:
    def test_sets_status_to_pending_decomposition(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        result = mark_pending_decomposition(f)
        assert result.status == "pending_decomposition"

    def test_returns_new_feature_object(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        result = mark_pending_decomposition(f)
        assert result is not f

    def test_original_feature_status_unchanged(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5, status="ready")
        mark_pending_decomposition(f)
        assert f.status == "ready"

    def test_calls_db_update_when_provided(self):
        calls = []

        def fake_db(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(id="feat-db-test", refinement_attempts=2)
        mark_pending_decomposition(f, db_update=fake_db)
        assert calls == [("feat-db-test", {"status": "pending_decomposition"})]

    def test_no_db_call_when_db_update_is_none(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.5)
        result = mark_pending_decomposition(f, db_update=None)
        assert result.status == "pending_decomposition"

    def test_raises_value_error_on_negative_attempts(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            mark_pending_decomposition(f)

    def test_db_update_not_called_when_error_raised(self):
        calls = []

        def fake_db(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError):
            mark_pending_decomposition(f, db_update=fake_db)

        assert calls == []
