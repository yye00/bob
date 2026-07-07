"""Tests for spec_ambiguity_linter — pre-plan gate rejecting vague ACs.

Verifies that the spec_ambiguity_linter module exposes lint_acceptance_criteria
and correctly classifies structured vs. ambiguous acceptance criteria.
"""

from __future__ import annotations

import pytest

from spec_ambiguity_linter import lint_acceptance_criteria, LintIssue, LintReport
from bob.spec_ambiguity_linter import is_ambiguous_criterion


class TestLintAcceptanceCriteriaStructuredForms:
    def test_file_exists_ac_passes(self):
        issues = lint_acceptance_criteria("F", ["File exists: src/bob/foo.py"])
        assert issues == []

    def test_function_defined_ac_passes(self):
        issues = lint_acceptance_criteria("F", ["Function defined: bob.foo.bar"])
        assert issues == []

    def test_class_defined_ac_passes(self):
        issues = lint_acceptance_criteria("F", ["Class defined: bob.module.MyClass"])
        assert issues == []

    def test_pytest_ac_passes(self):
        issues = lint_acceptance_criteria("F", ["pytest: tests/test_foo.py"])
        assert issues == []

    def test_integration_ac_passes(self):
        issues = lint_acceptance_criteria("F", ["integration: bob.cli.plan"])
        assert issues == []

    def test_behavior_ears_ac_passes(self):
        issues = lint_acceptance_criteria("F", ["behavior: system logs error when token budget exceeded"])
        assert issues == []

    def test_multiple_structured_acs_all_pass(self):
        acs = [
            "File exists: src/bob/foo.py",
            "pytest: tests/test_foo.py",
            "Function defined: bob.foo.bar",
            "Class defined: bob.module.MyClass",
            "integration: bob.cli.plan",
        ]
        issues = lint_acceptance_criteria("F", acs)
        assert issues == []


class TestLintAcceptanceCriteriaAmbiguousPatterns:
    def test_bare_verb_works_flagged(self):
        issues = lint_acceptance_criteria("F", ["The module works correctly"])
        assert len(issues) >= 1
        assert issues[0].ac_index == 0

    def test_bare_verb_handles_flagged(self):
        issues = lint_acceptance_criteria("F", ["handles all edge cases"])
        assert len(issues) >= 1

    def test_bare_verb_supports_flagged(self):
        issues = lint_acceptance_criteria("F", ["supports all formats"])
        assert len(issues) >= 1

    def test_unbounded_quantifier_all_cases_flagged(self):
        issues = lint_acceptance_criteria("F", ["handles all cases"])
        assert len(issues) >= 1

    def test_unbounded_quantifier_any_input_flagged(self):
        issues = lint_acceptance_criteria("F", ["works for any input"])
        assert len(issues) >= 1

    def test_vague_ac_returns_lint_issue_with_ac_index(self):
        issues = lint_acceptance_criteria("F", [
            "File exists: src/foo.py",
            "works correctly",
        ])
        assert len(issues) == 1
        assert issues[0].ac_index == 1

    def test_vague_ac_returns_lint_issue_with_criterion(self):
        issues = lint_acceptance_criteria("F", ["works correctly"])
        assert issues[0].criterion == "works correctly"

    def test_vague_ac_returns_lint_issue_with_reason(self):
        issues = lint_acceptance_criteria("F", ["works correctly"])
        assert isinstance(issues[0].reason, str)
        assert len(issues[0].reason) > 0

    def test_multiple_vague_acs_all_flagged(self):
        acs = [
            "works for any input",
            "supports everything",
            "pytest: tests/test_ok.py",
            "handles all cases",
        ]
        issues = lint_acceptance_criteria("F", acs)
        ac_indices = [i.ac_index for i in issues]
        assert 0 in ac_indices
        assert 1 in ac_indices
        assert 3 in ac_indices
        assert 2 not in ac_indices


class TestLintIssueType:
    def test_returns_list(self):
        result = lint_acceptance_criteria("F", ["File exists: src/foo.py"])
        assert isinstance(result, list)

    def test_issues_are_lint_issue_instances(self):
        issues = lint_acceptance_criteria("F", ["works correctly"])
        assert isinstance(issues[0], LintIssue)

    def test_lint_issue_has_ac_index(self):
        issues = lint_acceptance_criteria("F", ["works correctly"])
        assert hasattr(issues[0], "ac_index")

    def test_lint_issue_has_criterion(self):
        issues = lint_acceptance_criteria("F", ["works correctly"])
        assert hasattr(issues[0], "criterion")

    def test_lint_issue_has_reason(self):
        issues = lint_acceptance_criteria("F", ["works correctly"])
        assert hasattr(issues[0], "reason")


class TestIsAmbiguousCriterion:
    def test_structured_file_exists_is_not_ambiguous(self):
        assert is_ambiguous_criterion("File exists: src/foo.py") is False

    def test_structured_pytest_is_not_ambiguous(self):
        assert is_ambiguous_criterion("pytest: tests/test_foo.py") is False

    def test_structured_function_defined_is_not_ambiguous(self):
        assert is_ambiguous_criterion("Function defined: bob.foo.bar") is False

    def test_bare_verb_works_is_ambiguous(self):
        assert is_ambiguous_criterion("works correctly") is True

    def test_bare_verb_handles_is_ambiguous(self):
        assert is_ambiguous_criterion("handles all edge cases") is True

    def test_unbounded_quantifier_is_ambiguous(self):
        assert is_ambiguous_criterion("works for any input") is True

    def test_free_text_without_structure_is_ambiguous(self):
        assert is_ambiguous_criterion("the feature should be nice") is True

    def test_empty_string_is_ambiguous(self):
        assert is_ambiguous_criterion("") is True

    def test_whitespace_only_is_ambiguous(self):
        assert is_ambiguous_criterion("   ") is True

    def test_returns_bool(self):
        assert isinstance(is_ambiguous_criterion("File exists: x.py"), bool)

    def test_non_string_raises_value_error(self):
        with pytest.raises(ValueError):
            is_ambiguous_criterion(None)

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError):
            is_ambiguous_criterion(42)


class TestLintReportClass:
    def test_lint_report_passed_when_no_issues(self):
        report = LintReport(feature_name="F", issues=[])
        assert report.passed is True

    def test_lint_report_failed_when_has_issues(self):
        issue = LintIssue(ac_index=0, criterion="works correctly", reason="bare verb")
        report = LintReport(feature_name="F", issues=[issue])
        assert report.passed is False

    def test_lint_report_format_report_passed(self):
        report = LintReport(feature_name="MyFeature", issues=[])
        text = report.format_report()
        assert "PASSED" in text
        assert "MyFeature" in text

    def test_lint_report_format_report_failed(self):
        issue = LintIssue(ac_index=0, criterion="works correctly", reason="bare verb")
        report = LintReport(feature_name="MyFeature", issues=[issue])
        text = report.format_report()
        assert "FAILED" in text
        assert "AC[0]" in text
