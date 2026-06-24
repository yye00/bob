"""Tests error path: _should_decompose_instead_of_execute raises ValueError on negative attempts."""

import pytest

from bob.models import Feature
from bob.orchestrator.run_loop import _should_decompose_instead_of_execute


def make_feature(**kwargs):
    defaults = dict(
        id="feat-err",
        project_id="proj-001",
        name="Error Path Feature",
        status="ready",
        refinement_attempts=-1,
        readiness_score=0.65,
        max_refinement_attempts=5,
        conf_spec_understanding=0.65,
        conf_impl_correctness=0.65,
        conf_test_adequacy=0.65,
    )
    defaults.update(kwargs)
    return Feature(**defaults)


class TestInvalidAttemptsValue:
    def test_raises_value_error_with_negative_message_at_minus_one(self):
        f = make_feature(refinement_attempts=-1)
        with pytest.raises(ValueError, match="negative"):
            _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)

    def test_raises_value_error_with_negative_message_at_minus_ten(self):
        f = make_feature(refinement_attempts=-10)
        with pytest.raises(ValueError, match="negative"):
            _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)

    def test_no_error_at_zero(self):
        f = make_feature(refinement_attempts=0)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is False  # attempt=0 => never decompose

    def test_no_error_at_positive(self):
        f = make_feature(refinement_attempts=2, readiness_score=0.65)
        result = _should_decompose_instead_of_execute(f, previous_readiness_score=0.65)
        assert result is True
