"""Error-path tests — invalid input raises ValueError and never silently succeeds."""

import pytest

from bob3.models import Feature
from bob3.stuck_readiness_decomposer import check_stuck_readiness, mark_pending_decomposition


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


class TestCheckStuckReadinessErrors:
    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            check_stuck_readiness(f)

    def test_negative_attempts_minus_ten_raises_value_error(self):
        f = make_feature(refinement_attempts=-10)
        with pytest.raises(ValueError, match="negative"):
            check_stuck_readiness(f)

    def test_error_message_includes_feature_id(self):
        f = make_feature(id="corrupt-feat-xyz", refinement_attempts=-1)
        with pytest.raises(ValueError, match="corrupt-feat-xyz"):
            check_stuck_readiness(f)

    def test_negative_attempts_does_not_silently_return(self):
        f = make_feature(refinement_attempts=-1)
        raised = False
        try:
            result = check_stuck_readiness(f)
            assert False, f"Expected ValueError but got {result!r}"
        except ValueError:
            raised = True
        assert raised


class TestMarkPendingDecompositionErrors:
    def test_negative_attempts_raises_value_error(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            mark_pending_decomposition(f)

    def test_negative_attempts_does_not_call_db_update(self):
        calls = []

        def fake_db_update(feature_id, **kwargs):
            calls.append((feature_id, kwargs))

        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError):
            mark_pending_decomposition(f, db_update=fake_db_update)

        assert calls == [], "db_update must not be called when ValueError is raised"

    def test_error_message_includes_feature_id(self):
        f = make_feature(id="bad-feature-999", refinement_attempts=-5)
        with pytest.raises(ValueError, match="bad-feature-999"):
            mark_pending_decomposition(f)

    def test_negative_attempts_does_not_silently_succeed(self):
        f = make_feature(refinement_attempts=-1)
        raised = False
        try:
            result = mark_pending_decomposition(f)
            assert False, f"Expected ValueError but got {result!r}"
        except ValueError:
            raised = True
        assert raised
