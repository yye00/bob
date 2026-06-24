"""Tests for bob.boundary_error_detection module.

Verifies detect_coverage_with_word_boundaries and filter_prose_acs use
word-boundary regexes on prose ACs only, matching the composite scorer's logic.
"""

from __future__ import annotations

import pytest
from bob.boundary_error_detection import (
    detect_coverage_with_word_boundaries,
    filter_prose_acs,
)


class TestFilterProseAcs:
    def test_empty_list_returns_empty(self):
        assert filter_prose_acs([]) == []

    def test_structural_file_exists_excluded(self):
        result = filter_prose_acs(["File exists: src/foo.py"])
        assert result == []

    def test_structural_function_defined_excluded(self):
        result = filter_prose_acs(["Function defined: bob.foo.bar"])
        assert result == []

    def test_structural_pytest_excluded(self):
        result = filter_prose_acs(["pytest: tests/test_foo.py"])
        assert result == []

    def test_structural_integration_excluded(self):
        result = filter_prose_acs(["integration: bob.memory"])
        assert result == []

    def test_prose_ac_retained(self):
        ac = "The function returns a valid result."
        result = filter_prose_acs([ac])
        assert result == [ac]

    def test_mixed_acs_only_prose_retained(self):
        acs = [
            "File exists: src/bob/foo.py",
            "The function handles null input.",
            "pytest: tests/test_foo.py",
            "Raises ValueError on invalid data.",
        ]
        result = filter_prose_acs(acs)
        assert result == [
            "The function handles null input.",
            "Raises ValueError on invalid data.",
        ]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="criteria"):
            filter_prose_acs(None)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_prose_acs([42])

    def test_order_preserved(self):
        acs = ["WHEN x THEN y", "WHEN a THEN b"]
        result = filter_prose_acs(acs)
        assert result == acs


class TestDetectCoverageWithWordBoundaries:
    """Core correctness: word-boundary detection on prose-only ACs."""

    def test_empty_list_returns_false_false(self):
        assert detect_coverage_with_word_boundaries([]) == (False, False)

    def test_slug_failing_does_not_satisfy_error_coverage(self):
        # Regressing case: "failing" in slug must NOT match "fail" via word boundary.
        # "failing" contains "fail" as a substring BUT IS a word-boundary match too.
        # Key: structural lines are excluded before matching.
        acs = [
            "pytest: tests/test_failing_tests.py — handles failing tests",
        ]
        # This is a structural pytest: line, so it's excluded → no error coverage.
        result = detect_coverage_with_word_boundaries(acs)
        assert result == (False, False)

    def test_slug_length_capped_does_not_satisfy_boundary_coverage(self):
        # Regressing case: "length-capped" in a structural slug must NOT match "limit".
        acs = [
            "File exists: src/bob/derived_module_slug_must_be_length_capped.py",
        ]
        result = detect_coverage_with_word_boundaries(acs)
        assert result == (False, False)

    def test_prose_ac_with_boundary_keyword_detected(self):
        acs = ["handles empty input gracefully"]
        result = detect_coverage_with_word_boundaries(acs)
        assert result == (True, False)

    def test_prose_ac_with_error_keyword_detected(self):
        acs = ["raises ValueError on invalid input"]
        result = detect_coverage_with_word_boundaries(acs)
        assert result == (False, True)

    def test_prose_ac_with_both_keywords_detected(self):
        acs = ["handles null input and raises ValueError"]
        result = detect_coverage_with_word_boundaries(acs)
        assert result == (True, True)

    def test_all_structural_returns_false_false(self):
        acs = [
            "File exists: src/foo.py",
            "Function defined: bob.foo.process",
            "pytest: tests/test_foo.py",
            "integration: bob.memory",
        ]
        assert detect_coverage_with_word_boundaries(acs) == (False, False)

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_word_boundaries(None)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_word_boundaries([42])

    def test_returns_two_bools(self):
        result = detect_coverage_with_word_boundaries(["hello"])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, bool) for v in result)

    def test_word_boundary_limit_in_prose_detected(self):
        acs = ["must not exceed the limit"]
        result = detect_coverage_with_word_boundaries(acs)
        assert result[0] is True

    def test_word_fail_in_prose_detected(self):
        acs = ["function must fail on bad input"]
        result = detect_coverage_with_word_boundaries(acs)
        assert result[1] is True

    def test_does_not_mutate_input(self):
        original = ["The function processes data.", "File exists: src/foo.py"]
        copy = list(original)
        detect_coverage_with_word_boundaries(original)
        assert original == copy

    def test_idempotent(self):
        acs = ["handles zero input"]
        r1 = detect_coverage_with_word_boundaries(acs)
        r2 = detect_coverage_with_word_boundaries(acs)
        assert r1 == r2
