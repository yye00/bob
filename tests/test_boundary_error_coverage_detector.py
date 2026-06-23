"""Tests for bob3.boundary_error_coverage_detector.

Verifies that detect_coverage_with_word_boundaries and filter_prose_acs:
- Use word-boundary regexes (not naive substring matching)
- Probe only prose ACs, not structural lines
- Handle the two regressing cases from the root-cause fix:
  "failing" slug must NOT satisfy error coverage
  "length-capped" slug must NOT satisfy boundary coverage
"""

from __future__ import annotations

import pytest
from bob3.boundary_error_coverage_detector import (
    detect_coverage_with_word_boundaries,
    filter_prose_acs,
)


class TestFilterProseAcs:
    """filter_prose_acs removes structural lines, keeps prose ACs."""

    def test_empty_sequence_returns_empty(self):
        assert filter_prose_acs([]) == []

    def test_all_prose_acs_returned_unchanged(self):
        acs = ["The function handles null input.", "Raises ValueError on invalid data."]
        assert filter_prose_acs(acs) == acs

    def test_file_exists_filtered(self):
        acs = ["File exists: src/bob3/foo.py", "The module exposes a public API."]
        result = filter_prose_acs(acs)
        assert result == ["The module exposes a public API."]

    def test_function_defined_filtered(self):
        acs = ["Function defined: bob3.foo.bar", "Handles edge cases gracefully."]
        result = filter_prose_acs(acs)
        assert result == ["Handles edge cases gracefully."]

    def test_pytest_prefix_filtered(self):
        acs = ["pytest: tests/test_foo.py", "The system processes data correctly."]
        result = filter_prose_acs(acs)
        assert result == ["The system processes data correctly."]

    def test_integration_prefix_filtered(self):
        acs = ["integration: bob3.orchestrator", "Logs are written on completion."]
        result = filter_prose_acs(acs)
        assert result == ["Logs are written on completion."]

    def test_all_structural_returns_empty(self):
        acs = [
            "File exists: src/bob3/handler.py",
            "Function defined: bob3.handler.process",
            "pytest: tests/test_handler.py",
            "integration: bob3.memory",
        ]
        assert filter_prose_acs(acs) == []

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="criteria"):
            filter_prose_acs(None)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            filter_prose_acs(["valid", 42])

    def test_case_insensitive_structural_match(self):
        acs = ["FILE EXISTS: src/foo.py", "PYTEST: tests/test_foo.py"]
        assert filter_prose_acs(acs) == []

    def test_preserves_order(self):
        acs = ["Prose B.", "File exists: src/b.py", "Prose A."]
        result = filter_prose_acs(acs)
        assert result == ["Prose B.", "Prose A."]


class TestDetectCoverageWithWordBoundaries:
    """detect_coverage_with_word_boundaries uses \b word-boundary regex on prose only."""

    def test_empty_list_returns_false_false(self):
        assert detect_coverage_with_word_boundaries([]) == (False, False)

    def test_no_keywords_returns_false_false(self):
        acs = ["The function computes the result.", "Processes requests in order."]
        assert detect_coverage_with_word_boundaries(acs) == (False, False)

    def test_boundary_keyword_in_prose_detected(self):
        has_b, has_e = detect_coverage_with_word_boundaries(["handles empty input"])
        assert has_b is True

    def test_error_keyword_in_prose_detected(self):
        has_b, has_e = detect_coverage_with_word_boundaries(["raises ValueError on bad data"])
        assert has_e is True

    def test_both_keywords_detected(self):
        acs = ["handles null input and raises ValueError"]
        has_b, has_e = detect_coverage_with_word_boundaries(acs)
        assert has_b is True
        assert has_e is True

    def test_all_structural_acs_returns_false_false(self):
        acs = [
            "File exists: src/bob3/handler.py",
            "Function defined: bob3.handler.process",
            "pytest: tests/test_handler.py",
            "integration: bob3.memory",
        ]
        assert detect_coverage_with_word_boundaries(acs) == (False, False)

    # --- Regression tests: the two failing cases from root-cause analysis ---

    def test_slug_with_failing_in_pytest_ac_does_not_satisfy_error(self):
        """'failing' in pytest: slug must NOT satisfy error coverage (word boundary fix)."""
        acs = [
            "pytest: tests/test_failing_tests_boundary.py — some description",
            "File exists: src/bob3/failing_tests.py",
        ]
        has_b, has_e = detect_coverage_with_word_boundaries(acs)
        # "failing" appears only in structural slug — should NOT count
        assert has_e is False

    def test_slug_with_length_capped_in_pytest_ac_does_not_satisfy_boundary(self):
        """'length-capped' in pytest: slug must NOT satisfy boundary coverage."""
        acs = [
            "pytest: tests/test_length_capped_boundary.py — some description",
            "File exists: src/bob3/length_capped.py",
        ]
        has_b, has_e = detect_coverage_with_word_boundaries(acs)
        # "limit" does not appear and "length-capped" only in structural slug
        assert has_b is False

    def test_word_boundary_prevents_partial_match_on_fail(self):
        """'fail' as \b token must not match inside 'failing' in prose."""
        # "failing" does contain the chars "fail" but with word boundary,
        # "fail" as a standalone word is what we look for. "failing" does
        # match \bfail\b? No — \bfail\b requires word boundary after 'l'.
        # "failing" → 'fail' is followed by 'i', which is a word char,
        # so \bfail\b does NOT match inside "failing".
        has_b, has_e = detect_coverage_with_word_boundaries(["The system is failing tests."])
        # "failing" — does \bfail\b match? No, because 'l' is followed by 'i'.
        # But \bfail\b also matches "fail" standalone. Let's check the regex pattern:
        # the pattern uses \b(error|exception|fail|...) — "failing" starts with "fail"
        # and \bfail matches at start, but \bfail\b requires word boundary after 'l'
        # which 'i' breaks. So "failing" should NOT match \bfail\b.
        # However note that the actual regex uses \b at start only for the group.
        # Let's be precise: the pattern is r"\b(error|exception|fail|...)\b"
        # For "failing": \b at 'f', then 'fail' matches, then we need \b after 'l'.
        # 'i' is a word character → no \b → "failing" does NOT match \bfail\b.
        assert has_e is False

    def test_boundary_keyword_minimum_detected_in_prose(self):
        has_b, _ = detect_coverage_with_word_boundaries(["accepts minimum valid input"])
        assert has_b is True

    def test_error_keyword_raises_detected_in_prose(self):
        _, has_e = detect_coverage_with_word_boundaries(["must raise on empty path"])
        assert has_e is True

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_word_boundaries(None)

    def test_non_string_element_raises_value_error(self):
        with pytest.raises(ValueError):
            detect_coverage_with_word_boundaries([42])

    def test_returns_tuple_of_bools(self):
        result = detect_coverage_with_word_boundaries([])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], bool)

    def test_does_not_mutate_input(self):
        acs = ["handles empty input", "File exists: src/foo.py"]
        original = list(acs)
        detect_coverage_with_word_boundaries(acs)
        assert acs == original

    def test_structural_with_error_description_not_detected(self):
        """A pytest: AC with 'error' in description suffix is structural — not counted."""
        acs = ["pytest: tests/test_foo_error.py — invalid input raises ValueError"]
        # Structural lines are excluded; the description after ' — ' is part of
        # the structural line and therefore not probed.
        has_b, has_e = detect_coverage_with_word_boundaries(acs)
        assert has_e is False

    def test_structural_with_boundary_description_not_detected(self):
        """A pytest: AC with 'boundary' in description suffix is structural — not counted."""
        acs = ["pytest: tests/test_foo_boundary.py — empty input returns well-defined result"]
        has_b, has_e = detect_coverage_with_word_boundaries(acs)
        assert has_b is False

    def test_mixed_structural_and_prose_only_prose_probed(self):
        acs = [
            "File exists: src/bob3/limit_checker.py",
            "The function validates normal inputs correctly.",
        ]
        has_b, has_e = detect_coverage_with_word_boundaries(acs)
        # "limit" appears only in structural slug — not probed
        assert has_b is False

    def test_multiple_boundary_keywords_detected(self):
        acs = ["must handle null, zero, and negative values gracefully"]
        has_b, _ = detect_coverage_with_word_boundaries(acs)
        assert has_b is True

    def test_error_keywords_case_insensitive(self):
        has_b, has_e = detect_coverage_with_word_boundaries(["must raise VALUEERROR on bad input"])
        assert has_e is True
