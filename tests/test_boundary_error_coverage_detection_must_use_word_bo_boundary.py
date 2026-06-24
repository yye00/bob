"""Boundary cases for detect_boundary_error_coverage.

Verifies that empty, zero, or minimum inputs return a well-defined result
rather than raising (boundary case AC).
"""

from __future__ import annotations

import pytest
from bob.coverage_detector import detect_boundary_error_coverage


class TestBoundaryCases:
    """Empty/minimal inputs must return a valid (bool, bool) tuple without raising."""

    def test_empty_list_returns_false_false(self):
        result = detect_boundary_error_coverage([])
        assert result == (False, False)

    def test_single_empty_string_criterion(self):
        result = detect_boundary_error_coverage([""])
        assert result == (False, False)

    def test_single_whitespace_criterion(self):
        result = detect_boundary_error_coverage(["   "])
        assert result == (False, False)

    def test_one_structural_ac_only(self):
        result = detect_boundary_error_coverage(["File exists: src/foo.py"])
        assert result == (False, False)

    def test_one_prose_ac_no_keywords(self):
        result = detect_boundary_error_coverage(["The function computes the result."])
        assert result == (False, False)

    def test_returns_tuple_on_empty(self):
        result = detect_boundary_error_coverage([])
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], bool)

    def test_returns_tuple_on_single_prose(self):
        result = detect_boundary_error_coverage(["The system processes requests."])
        assert isinstance(result, tuple)
        assert isinstance(result[0], bool)
        assert isinstance(result[1], bool)

    def test_all_structural_acs_returns_false_false(self):
        criteria = [
            "File exists: src/bob/handler.py",
            "Function defined: bob.handler.process",
            "pytest: tests/test_handler.py",
            "integration: bob.memory",
        ]
        result = detect_boundary_error_coverage(criteria)
        assert result == (False, False)

    def test_single_boundary_keyword_prose(self):
        result = detect_boundary_error_coverage(["handles empty input"])
        assert result == (True, False)

    def test_single_error_keyword_prose(self):
        result = detect_boundary_error_coverage(["raises on invalid data"])
        assert result == (False, True)

    def test_both_keywords_prose(self):
        result = detect_boundary_error_coverage([
            "handles null input and raises ValueError"
        ])
        assert result == (True, True)

    def test_large_ac_list_does_not_raise(self):
        criteria = ["Criterion number {}".format(i) for i in range(1000)]
        result = detect_boundary_error_coverage(criteria)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_idempotent_on_repeated_calls(self):
        criteria = ["handles zero input gracefully"]
        r1 = detect_boundary_error_coverage(criteria)
        r2 = detect_boundary_error_coverage(criteria)
        assert r1 == r2

    def test_does_not_mutate_input(self):
        original = ["The function processes data.", "File exists: src/foo.py"]
        copy = list(original)
        detect_boundary_error_coverage(original)
        assert original == copy

    def test_unicode_criterion_does_not_raise(self):
        result = detect_boundary_error_coverage(["处理空输入时函数不应抛出异常"])
        assert isinstance(result, tuple)
        assert len(result) == 2
