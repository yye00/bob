"""Tests asserting should_trigger returns False when refinement_attempts == 1 (first/minimum-attempt boundary)."""

import pytest
from bob3.orchestrator.path_finding_retry import (
    should_trigger,
    does_not_trigger_on_first_attempt,
    FailureClass,
)


# Failure info that would trigger if refinement_attempts were high enough
CLASSIFIABLE_FAILURE = {"failure_class": "ambiguous_ac"}
IMPORT_FAILURE = {"failure_class": "import_error"}
MISSING_TEST_FAILURE = {"failure_class": "missing_test_file"}


def test_should_trigger_false_when_attempts_is_one():
    result = should_trigger(1, CLASSIFIABLE_FAILURE)
    assert result is False


def test_should_trigger_false_when_attempts_is_zero():
    result = should_trigger(0, CLASSIFIABLE_FAILURE)
    assert result is False


def test_does_not_trigger_on_first_attempt_returns_false():
    result = does_not_trigger_on_first_attempt(1, CLASSIFIABLE_FAILURE)
    assert result is False


def test_does_not_trigger_when_zero_attempts():
    result = does_not_trigger_on_first_attempt(0, CLASSIFIABLE_FAILURE)
    assert result is False


def test_should_trigger_true_when_attempts_at_boundary_two():
    result = should_trigger(2, CLASSIFIABLE_FAILURE)
    assert result is True


def test_should_trigger_true_when_attempts_above_two():
    result = should_trigger(5, CLASSIFIABLE_FAILURE)
    assert result is True


def test_should_trigger_false_for_all_classifiable_failures_at_attempt_one():
    for failure_class in [CLASSIFIABLE_FAILURE, IMPORT_FAILURE, MISSING_TEST_FAILURE]:
        assert should_trigger(1, failure_class) is False, (
            f"should_trigger must be False at attempt=1 even for classifiable failure {failure_class}"
        )


def test_should_trigger_false_even_when_failure_is_classifiable_at_zero():
    result = should_trigger(0, IMPORT_FAILURE)
    assert result is False


def test_should_trigger_false_for_unknown_failure_at_attempts_two():
    """Unknown failure class disables trigger even at refinement_attempts >= 2."""
    result = should_trigger(2, {"failure_class": "unknown"})
    assert result is False


def test_should_trigger_false_for_unknown_failure_at_high_attempts():
    result = should_trigger(10, {"failure_class": "unknown"})
    assert result is False
