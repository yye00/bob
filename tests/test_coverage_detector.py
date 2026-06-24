"""Tests for bob.coverage_detector.detect_boundary_error_coverage."""

from __future__ import annotations

import pytest
from bob.coverage_detector import detect_boundary_error_coverage


class TestDetectBoundaryErrorCoverageBasic:
    """Basic detection: prose ACs with boundary/error keywords are recognised."""

    def test_no_criteria_returns_false_false(self):
        has_boundary, has_error = detect_boundary_error_coverage([])
        assert has_boundary is False
        assert has_error is False

    def test_boundary_keyword_empty_detected(self):
        criteria = ["When input is empty the function raises ValueError"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_boundary_keyword_null_detected(self):
        criteria = ["Returns default when input is null"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_boundary_keyword_zero_detected(self):
        criteria = ["Handles zero input gracefully"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_boundary_keyword_minimum_detected(self):
        criteria = ["minimum value is accepted without error"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_boundary_keyword_maximum_detected(self):
        criteria = ["maximum value is accepted without error"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_boundary_keyword_limit_detected(self):
        criteria = ["Behaviour at the limit of the input range"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_error_keyword_error_detected(self):
        criteria = ["When invalid input: raises an error"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is True

    def test_error_keyword_exception_detected(self):
        criteria = ["Function raises an exception for invalid input"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is True

    def test_error_keyword_invalid_detected(self):
        criteria = ["When input is invalid the function should reject it"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is True

    def test_error_keyword_raise_detected(self):
        criteria = ["Function must raise ValueError on negative input"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is True

    def test_error_keyword_fail_detected(self):
        criteria = ["Operation must fail with a clear message for bad config"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is True

    def test_both_keywords_present(self):
        criteria = [
            "Handles empty input by returning None",
            "Raises ValueError for invalid data",
        ]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True
        assert has_error is True

    def test_neither_keyword_present(self):
        criteria = ["Function computes the sum of two numbers"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is False
        assert has_error is False


class TestWordBoundaryMatching:
    """Verify word-boundary regex — substrings in slugs must NOT match."""

    def test_slug_with_failing_does_not_satisfy_error_coverage(self):
        """'failing' in a slug-like AC must not count as error coverage."""
        criteria = ["Feature: handle failing tests gracefully"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        # 'failing' as a word triggers error (fail + ing). Let's check the
        # actual expected behavior: the scorer uses \bfail\b so 'failing' does
        # NOT match \bfail\b.  We test the scorer's semantics here.
        # 'failing' does NOT match \bfail\b (word boundary test)
        assert has_error is False

    def test_slug_with_length_capped_does_not_satisfy_boundary_coverage(self):
        """'length-capped' in a slug-like AC must not count as boundary coverage."""
        # 'capped' is not in the boundary keywords. 'limit' substring in
        # 'length-capped' or similar slugs should only match as a whole word.
        criteria = ["Feature: slug contains length-capped input"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        # 'length-capped' contains no boundary keyword as a whole word
        assert has_boundary is False

    def test_word_limit_in_prose_is_detected(self):
        """'limit' as a standalone word IS a boundary keyword."""
        criteria = ["Behaviour: at the limit of input size, returns truncated value"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_word_fail_in_prose_is_detected(self):
        """'fail' as a standalone word IS an error keyword."""
        criteria = ["Behaviour: when credentials are wrong, login must fail"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is True

    def test_error_as_embedded_syllable_does_not_match(self):
        """'tolerant' contains no error keyword — check no false positive."""
        criteria = ["System is resilient and tolerant of transient faults"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is False


class TestProseOnlyFiltering:
    """Structural ACs (file exists, function defined, pytest, integration) are excluded."""

    def test_structural_ac_file_exists_boundary_slug_is_ignored(self):
        """File exists: line with 'limit' in path must NOT satisfy boundary."""
        criteria = ["File exists: src/bob/limit_checker.py"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is False

    def test_structural_ac_function_defined_error_slug_is_ignored(self):
        """Function defined: line with 'error' in name must NOT satisfy error coverage."""
        criteria = ["Function defined: bob.error_handler.handle"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is False

    def test_structural_ac_pytest_path_boundary_slug_is_ignored(self):
        """pytest: line with 'boundary' in filename must NOT satisfy boundary coverage."""
        criteria = ["pytest: tests/test_boundary_check.py"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is False

    def test_structural_ac_integration_error_is_ignored(self):
        """integration: line with 'error' must NOT satisfy error coverage."""
        criteria = ["integration: bob.error_propagation"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is False

    def test_prose_ac_with_boundary_keyword_detected(self):
        """Non-structural AC with boundary keyword IS detected."""
        criteria = [
            "File exists: src/bob/handler.py",
            "Behaviour: handles empty list without raising",
        ]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_mixed_structural_and_prose(self):
        """Only prose ACs contribute; structural ACs are filtered."""
        criteria = [
            "File exists: src/bob/error_handler.py",
            "Function defined: bob.minimum_value",
            "pytest: tests/test_boundary_case.py",
            "Behaviour: normal successful path returns result",
        ]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        # All structural lines are filtered; the prose AC has no boundary/error keywords
        assert has_boundary is False
        assert has_error is False

    def test_python_label_excluded(self):
        """python: lines are structural, not prose."""
        criteria = ["python: from bob.error_handling import handle"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is False


class TestCaseInsensitivity:
    """Keyword matching is case-insensitive."""

    def test_EMPTY_uppercase_boundary(self):
        criteria = ["EMPTY string must be handled"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True

    def test_ValueError_uppercase_error(self):
        criteria = ["Must raise ValueError for missing fields"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_error is True

    def test_Maximum_mixed_case(self):
        criteria = ["Maximum allowed input is 100 records"]
        has_boundary, has_error = detect_boundary_error_coverage(criteria)
        assert has_boundary is True


class TestReturnType:
    """Return type is always a 2-tuple of bools."""

    def test_returns_tuple(self):
        result = detect_boundary_error_coverage([])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_bools(self):
        has_boundary, has_error = detect_boundary_error_coverage(["some criterion"])
        assert isinstance(has_boundary, bool)
        assert isinstance(has_error, bool)
