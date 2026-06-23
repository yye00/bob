"""Tests for classify_failure returning FailureClass.ambiguous_ac."""

import pytest
from bob3.orchestrator.path_finding_retry import classify_failure, FailureClass


def test_classify_explicit_ambiguous_ac():
    result = classify_failure({"failure_class": "ambiguous_ac"})
    assert result == FailureClass.ambiguous_ac


def test_classify_ambiguous_in_message():
    result = classify_failure({"message": "ambiguous acceptance criteria — cannot determine expected output"})
    assert result == FailureClass.ambiguous_ac


def test_classify_unclear_in_message():
    result = classify_failure({"message": "unclear what the function should return"})
    assert result == FailureClass.ambiguous_ac


def test_classify_ac_failure_in_error_type():
    result = classify_failure({"error_type": "ACFailure", "message": "ac failure: cannot interpret criterion"})
    assert result == FailureClass.ambiguous_ac


def test_classify_ambiguous_ac_is_enum_value():
    result = classify_failure({"failure_class": "ambiguous_ac"})
    assert result is FailureClass.ambiguous_ac


def test_classify_all_failure_classes_parseable():
    """All FailureClass values can be used as explicit failure_class input."""
    for fc in FailureClass:
        result = classify_failure({"failure_class": fc.value})
        assert result == fc


def test_classify_unknown_returns_unknown_not_ambiguous():
    result = classify_failure({"message": "some completely unrelated error"})
    assert result == FailureClass.unknown
    assert result != FailureClass.ambiguous_ac
