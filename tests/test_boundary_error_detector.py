"""Tests for bob3.boundary_error_detector.detect_coverage_with_boundaries.

Verifies that the word-boundary, prose-only detection correctly discriminates
between structural slug tokens and real boundary/error keywords in prose ACs.
"""

from __future__ import annotations

import pytest
from bob3.boundary_error_detector import detect_coverage_with_boundaries


class TestDetectCoverageWithBoundaries:
    """Core behaviour: word boundaries on prose ACs only."""

    def test_empty_list_returns_false_false(self):
        assert detect_coverage_with_boundaries([]) == (False, False)

    def test_purely_structural_acs_return_false_false(self):
        criteria = [
            "File exists: src/bob3/handler.py",
            "Function defined: bob3.handler.process",
            "pytest: tests/test_handler.py",
            "integration: bob3.memory",
        ]
        assert detect_coverage_with_boundaries(criteria) == (False, False)

    def test_slug_containing_fail_does_not_trigger_error_coverage(self):
        # AC: "pytest: tests/test_failing_tests.py" — slug "failing" must NOT satisfy error
        criteria = [
            "pytest: tests/test_failing_tests_boundary.py",
            "File exists: src/bob3/failing_handler.py",
        ]
        has_boundary, has_error = detect_coverage_with_boundaries(criteria)
        assert not has_error, (
            "slug token 'failing' inside a pytest: path must not satisfy error coverage"
        )

    def test_slug_containing_limit_does_not_trigger_boundary_coverage(self):
        # Feature slug "length-capped" → file path has "limit" substring
        criteria = [
            "pytest: tests/test_length_capped_limit_check.py",
            "File exists: src/bob3/limit_checker.py",
            "Function defined: bob3.limit_checker.check_limit",
        ]
        has_boundary, has_error = detect_coverage_with_boundaries(criteria)
        assert not has_boundary, (
            "slug token 'limit' inside a structural AC path must not satisfy boundary coverage"
        )

    def test_prose_ac_with_boundary_keyword_triggers_boundary(self):
        criteria = ["The function handles empty input without raising."]
        has_boundary, has_error = detect_coverage_with_boundaries(criteria)
        assert has_boundary

    def test_prose_ac_with_error_keyword_triggers_error(self):
        criteria = ["Raises ValueError when the argument is invalid."]
        has_boundary, has_error = detect_coverage_with_boundaries(criteria)
        assert has_error

    def test_both_keywords_in_prose_return_true_true(self):
        criteria = ["Handles null input and raises ValueError."]
        assert detect_coverage_with_boundaries(criteria) == (True, True)

    def test_mixed_structural_and_prose_prose_triggers(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
            "The function handles zero-length input gracefully.",
        ]
        has_boundary, has_error = detect_coverage_with_boundaries(criteria)
        assert has_boundary

    def test_boundary_word_at_word_boundary(self):
        # "min" must match as a word, not "minimum" prefix
        assert detect_coverage_with_boundaries(["handles min items"])[0] is True

    def test_word_boundary_prevents_partial_token_match(self):
        # "minimal" contains "min" but is a different word — \b does NOT match "min" inside "minimal"
        criteria = ["handles minimal configuration"]
        # "minimal" contains "min" but \b regex matches "min" as a word only at word boundary.
        # "minimal" — after "min" comes "imal", so \b is NOT between "min" and "i" since both are word chars.
        # So this should NOT match "min" separately — but "minimum" WOULD match.
        # The regex is \bmin\b — "minimal" would NOT match that.
        has_boundary, _ = detect_coverage_with_boundaries(criteria)
        # "minimal" does not match \bmin\b or any other boundary keyword — boundary should be False
        assert not has_boundary

    def test_returns_tuple_of_two_bools(self):
        result = detect_coverage_with_boundaries(["some prose AC"])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, bool) for v in result)

    def test_idempotent(self):
        criteria = ["handles empty input"]
        assert detect_coverage_with_boundaries(criteria) == detect_coverage_with_boundaries(criteria)

    def test_does_not_mutate_input(self):
        original = ["The function processes data.", "File exists: src/foo.py"]
        copy = list(original)
        detect_coverage_with_boundaries(original)
        assert original == copy

    def test_unicode_does_not_raise(self):
        result = detect_coverage_with_boundaries(["处理空输入时函数不应抛出异常"])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_failing_slug_false_positive_regression(self):
        """Regression: feature slug 'failing' must NOT satisfy error coverage."""
        # This was the exact false-positive case: composite 0.0 for 32/118 features
        criteria = [
            "File exists: src/bob3/failing_tests_processor.py",
            "Function defined: bob3.failing_tests_processor.process_failing_tests",
            "pytest: tests/test_failing_tests_processor.py",
            "integration: bob3.failing_tests_processor",
        ]
        has_boundary, has_error = detect_coverage_with_boundaries(criteria)
        assert not has_error, "slug 'failing' in structural ACs must not satisfy error coverage"
        assert not has_boundary

    def test_length_capped_slug_false_positive_regression(self):
        """Regression: feature slug 'length-capped' must NOT satisfy boundary coverage."""
        criteria = [
            "File exists: src/bob3/length_capped_validator.py",
            "Function defined: bob3.length_capped_validator.validate_length_capped",
            "pytest: tests/test_length_capped_validator.py",
        ]
        has_boundary, has_error = detect_coverage_with_boundaries(criteria)
        assert not has_boundary, "slug 'length-capped'/'limit' in structural ACs must not satisfy boundary"


class TestErrorPaths:
    """Invalid input must raise ValueError."""

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="criteria"):
            detect_coverage_with_boundaries(None)

    def test_integer_element_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_boundaries([42])

    def test_none_element_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_boundaries([None])

    def test_dict_element_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_boundaries([{"key": "val"}])

    def test_mixed_valid_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_boundaries(["valid", 99])
