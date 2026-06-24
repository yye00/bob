"""Tests for classify_failure returning FailureClass.missing_test_file."""

import pytest
from bob3.orchestrator.path_finding_retry import classify_failure, FailureClass


def test_classify_explicit_missing_test_file():
    result = classify_failure({"failure_class": "missing_test_file"})
    assert result == FailureClass.missing_test_file


def test_classify_filenotfounderror_message():
    result = classify_failure({"error_type": "FileNotFoundError", "message": "test file not found"})
    assert result == FailureClass.missing_test_file


def test_classify_no_such_file_message():
    result = classify_failure({"message": "No such file or directory: tests/test_foo.py"})
    assert result == FailureClass.missing_test_file


def test_classify_missing_test_in_traceback():
    result = classify_failure({
        "traceback": "FileNotFoundError: missing test tests/test_bar.py"
    })
    assert result == FailureClass.missing_test_file


def test_classify_missing_test_file_is_failure_class_enum():
    result = classify_failure({"failure_class": "missing_test_file"})
    assert isinstance(result, FailureClass)


def test_classify_raises_on_invalid_explicit_failure_class():
    with pytest.raises(ValueError, match="failure_class"):
        classify_failure({"failure_class": "not_a_real_class"})


def test_classify_raises_on_non_dict_input():
    with pytest.raises(ValueError, match="failure_class"):
        classify_failure("not a dict")  # type: ignore[arg-type]


def test_classify_raises_on_none_failure_class():
    with pytest.raises(ValueError, match="failure_class"):
        classify_failure({"failure_class": None})
