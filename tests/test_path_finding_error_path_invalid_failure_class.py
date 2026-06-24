"""Tests asserting classify_failure raises ValueError with message containing 'failure_class' on malformed input."""

import pytest
from bob.orchestrator.path_finding_retry import classify_failure, FailureClass


def test_raises_valueerror_on_invalid_failure_class_string():
    with pytest.raises(ValueError) as exc_info:
        classify_failure({"failure_class": "not_a_valid_class"})
    assert "failure_class" in str(exc_info.value).lower()


def test_raises_valueerror_on_none_failure_class():
    with pytest.raises(ValueError) as exc_info:
        classify_failure({"failure_class": None})
    assert "failure_class" in str(exc_info.value).lower()


def test_raises_valueerror_on_non_dict_input():
    with pytest.raises(ValueError) as exc_info:
        classify_failure("this is not a dict")  # type: ignore[arg-type]
    assert "failure_class" in str(exc_info.value).lower()


def test_raises_valueerror_on_integer_input():
    with pytest.raises(ValueError) as exc_info:
        classify_failure(42)  # type: ignore[arg-type]
    assert "failure_class" in str(exc_info.value).lower()


def test_raises_valueerror_on_list_input():
    with pytest.raises(ValueError) as exc_info:
        classify_failure(["ambiguous_ac"])  # type: ignore[arg-type]
    assert "failure_class" in str(exc_info.value).lower()


def test_raises_valueerror_on_empty_string_failure_class():
    with pytest.raises(ValueError) as exc_info:
        classify_failure({"failure_class": ""})
    assert "failure_class" in str(exc_info.value).lower()


def test_error_message_contains_failure_class_literally():
    """The ValueError message must literally contain the string 'failure_class'."""
    try:
        classify_failure({"failure_class": "bad_value"})
        pytest.fail("Expected ValueError to be raised")
    except ValueError as exc:
        assert "failure_class" in str(exc), (
            f"ValueError message must contain 'failure_class'; got: {str(exc)!r}"
        )


def test_valid_failure_class_does_not_raise():
    """Valid failure class values must not raise."""
    for fc in FailureClass:
        result = classify_failure({"failure_class": fc.value})
        assert result == fc


def test_raises_valueerror_on_wrong_case_failure_class():
    """FailureClass values are case-sensitive; wrong case must raise."""
    with pytest.raises(ValueError) as exc_info:
        classify_failure({"failure_class": "AMBIGUOUS_AC"})
    assert "failure_class" in str(exc_info.value).lower()
