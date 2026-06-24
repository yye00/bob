"""Tests for stuck_readiness_decomposition — kill the eval-demotion treadmill."""

import pytest

from bob.models import Feature
from stuck_readiness_decomposition import decompose_feature, should_trigger_decomposition


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


class TestShouldTriggerDecomposition:
    def test_all_conditions_met_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is True

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

    def test_no_previous_score_treated_as_no_improvement(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert should_trigger_decomposition(f, previous_readiness_score=None) is True

    def test_default_previous_score_is_none(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        assert should_trigger_decomposition(f) is True

    def test_readiness_decreased_returns_true(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.55)
        assert should_trigger_decomposition(f, previous_readiness_score=0.65) is True

    def test_three_attempts_returns_true(self):
        f = make_feature(refinement_attempts=3, readiness_score=0.50)
        assert should_trigger_decomposition(f, previous_readiness_score=0.50) is True

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            should_trigger_decomposition(f)

    def test_error_message_includes_feature_id(self):
        f = make_feature(id="stuck-feat-xyz", refinement_attempts=-1)
        with pytest.raises(ValueError, match="stuck-feat-xyz"):
            should_trigger_decomposition(f)


class TestDecomposeFeature:
    def test_sets_status_to_pending_decomposition(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = decompose_feature(f)
        assert result.status == "pending_decomposition"

    def test_returns_updated_feature(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = decompose_feature(f)
        assert result is not f

    def test_other_fields_unchanged(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = decompose_feature(f)
        assert result.id == f.id
        assert result.readiness_score == f.readiness_score
        assert result.refinement_attempts == f.refinement_attempts

    def test_calls_db_update_when_provided(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(id="feat-db-test", refinement_attempts=2)
        decompose_feature(f, db_update=fake_db_update)

        assert len(calls) == 1
        assert calls[0] == ("feat-db-test", {"status": "pending_decomposition"})

    def test_no_db_update_when_not_provided(self):
        f = make_feature(refinement_attempts=2)
        result = decompose_feature(f)
        assert result.status == "pending_decomposition"

    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            decompose_feature(f)

    def test_negative_attempts_does_not_call_db_update(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError):
            decompose_feature(f, db_update=fake_db_update)

        assert calls == []
