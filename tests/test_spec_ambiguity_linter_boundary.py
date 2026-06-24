"""Boundary tests for spec_linter.linter.lint_acceptance_criteria.

Each test exercises a zero, empty, or minimum input to verify the function
returns a well-defined result rather than raising an unhandled exception.
"""

from __future__ import annotations

import pytest

from spec_linter.linter import lint_acceptance_criteria, LintIssue


class TestBoundaryCases:
    def test_empty_list_returns_list(self):
        result = lint_acceptance_criteria("F", [])
        assert isinstance(result, list)

    def test_empty_list_returns_at_least_one_issue(self):
        result = lint_acceptance_criteria("F", [])
        assert len(result) >= 1

    def test_empty_feature_name_returns_list(self):
        result = lint_acceptance_criteria("", ["File exists: src/foo.py"])
        assert isinstance(result, list)

    def test_single_valid_ac_returns_empty_list(self):
        result = lint_acceptance_criteria("F", ["File exists: src/foo.py"])
        assert result == []

    def test_single_invalid_ac_returns_one_issue(self):
        result = lint_acceptance_criteria("F", ["works correctly"])
        assert len(result) >= 1
        assert isinstance(result[0], LintIssue)

    def test_list_with_one_empty_string_returns_issue(self):
        result = lint_acceptance_criteria("F", [""])
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_minimum_valid_pytest_ac(self):
        result = lint_acceptance_criteria("F", ["pytest: tests/test_f.py"])
        assert result == []

    def test_minimum_valid_function_ac(self):
        result = lint_acceptance_criteria("F", ["Function defined: a.b.c"])
        assert result == []

    def test_whitespace_only_ac_returns_issue(self):
        result = lint_acceptance_criteria("F", ["   "])
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_very_short_feature_name_accepted(self):
        result = lint_acceptance_criteria("X", ["File exists: x.py"])
        assert isinstance(result, list)

    def test_returns_list_not_none(self):
        result = lint_acceptance_criteria("F", [])
        assert result is not None

    def test_issues_have_ac_index_field(self):
        result = lint_acceptance_criteria("F", ["works correctly"])
        assert hasattr(result[0], "ac_index")

    def test_issues_have_criterion_field(self):
        result = lint_acceptance_criteria("F", ["works correctly"])
        assert hasattr(result[0], "criterion")

    def test_issues_have_reason_field(self):
        result = lint_acceptance_criteria("F", ["works correctly"])
        assert hasattr(result[0], "reason")

    def test_reason_is_non_empty_string(self):
        result = lint_acceptance_criteria("F", ["works correctly"])
        assert isinstance(result[0].reason, str)
        assert result[0].reason != ""
