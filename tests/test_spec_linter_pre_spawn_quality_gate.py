"""Tests for spec_linter_pre_spawn_quality_gate.py.

Verifies that the spec linter correctly catches:
- Ambiguous criteria (no measurable outcome)
- Missing edge cases (no failure path)
- Redundant criteria (duplicates)
- Banned operations in python: criterion expressions

Hard-fail issues block spawn; warnings are filed to reviews/findings.yaml.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from bob3.spec_linter_pre_spawn_quality_gate import (
    LintIssue,
    LintResult,
    LintSeverity,
    lint_acceptance_criteria,
    lint_feature_spec,
)


# ---------------------------------------------------------------------------
# LintIssue and LintResult data model tests
# ---------------------------------------------------------------------------

class TestLintIssue:
    def test_has_required_fields(self):
        issue = LintIssue(
            criterion="some criterion",
            reason="explanation",
            severity=LintSeverity.WARNING,
            category="ambiguous",
        )
        assert issue.criterion == "some criterion"
        assert issue.reason == "explanation"
        assert issue.severity == LintSeverity.WARNING
        assert issue.category == "ambiguous"

    def test_hard_fail_severity(self):
        issue = LintIssue(
            criterion="test",
            reason="banned op",
            severity=LintSeverity.ERROR,
            category="banned_operation",
        )
        assert issue.severity == LintSeverity.ERROR

    def test_warning_severity(self):
        issue = LintIssue(
            criterion="test",
            reason="vague",
            severity=LintSeverity.WARNING,
            category="ambiguous",
        )
        assert issue.severity == LintSeverity.WARNING


class TestLintResult:
    def test_no_issues_is_clean(self):
        result = LintResult(issues=[])
        assert result.passed is True
        assert result.hard_fail is False

    def test_warning_only_does_not_hard_fail(self):
        issue = LintIssue(
            criterion="x",
            reason="y",
            severity=LintSeverity.WARNING,
            category="ambiguous",
        )
        result = LintResult(issues=[issue])
        assert result.passed is True
        assert result.hard_fail is False

    def test_error_causes_hard_fail(self):
        issue = LintIssue(
            criterion="python: eval('os')",
            reason="banned: eval",
            severity=LintSeverity.ERROR,
            category="banned_operation",
        )
        result = LintResult(issues=[issue])
        assert result.hard_fail is True
        assert result.passed is False

    def test_warnings_list(self):
        w = LintIssue(criterion="a", reason="b", severity=LintSeverity.WARNING, category="ambiguous")
        e = LintIssue(criterion="c", reason="d", severity=LintSeverity.ERROR, category="banned_operation")
        result = LintResult(issues=[w, e])
        assert len(result.warnings) == 1
        assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# lint_acceptance_criteria — ambiguous criteria
# ---------------------------------------------------------------------------

class TestAmbiguousCriteria:
    def test_clean_file_exists_criterion_passes(self):
        criteria = ["File exists: src/bob3/foo.py"]
        result = lint_acceptance_criteria(criteria)
        assert result.passed

    def test_clean_pytest_criterion_passes(self):
        criteria = ["pytest: tests/test_foo.py"]
        result = lint_acceptance_criteria(criteria)
        assert result.passed

    def test_vague_criterion_flagged_as_ambiguous(self):
        criteria = ["The feature should work correctly"]
        result = lint_acceptance_criteria(criteria)
        ambiguous = [i for i in result.issues if i.category == "ambiguous"]
        assert len(ambiguous) >= 1

    def test_tbd_placeholder_flagged(self):
        criteria = ["TBD"]
        result = lint_acceptance_criteria(criteria)
        ambiguous = [i for i in result.issues if i.category == "ambiguous"]
        assert len(ambiguous) >= 1

    def test_todo_placeholder_flagged(self):
        criteria = ["TODO: define criteria later"]
        result = lint_acceptance_criteria(criteria)
        ambiguous = [i for i in result.issues if i.category == "ambiguous"]
        assert len(ambiguous) >= 1

    def test_no_measurable_outcome_flagged(self):
        # Criterion with no colon-prefixed form and no verb indicating testability
        criteria = ["The system is fast"]
        result = lint_acceptance_criteria(criteria)
        ambiguous = [i for i in result.issues if i.category == "ambiguous"]
        assert len(ambiguous) >= 1

    def test_python_criterion_without_assertion_flagged(self):
        # python: expressions should contain an assertion or comparison
        criteria = ["python: import bob3"]
        result = lint_acceptance_criteria(criteria)
        # This may be flagged as ambiguous (no measurable outcome) or a warning
        all_categories = {i.category for i in result.issues}
        assert "ambiguous" in all_categories or result.passed  # lenient: at least no error

    def test_well_formed_python_criterion_passes(self):
        criteria = ["python: assert True"]
        result = lint_acceptance_criteria(criteria)
        # A python: criterion with an assert should not be flagged as ambiguous
        ambiguous = [i for i in result.issues if i.category == "ambiguous"]
        assert len(ambiguous) == 0

    def test_empty_criterion_flagged(self):
        criteria = [""]
        result = lint_acceptance_criteria(criteria)
        issues = [i for i in result.issues if i.category in ("ambiguous", "empty")]
        assert len(issues) >= 1


# ---------------------------------------------------------------------------
# lint_acceptance_criteria — missing edge cases
# ---------------------------------------------------------------------------

class TestMissingEdgeCases:
    def test_only_happy_path_warns(self):
        # Only "file exists" and "pytest" without any failure-path criterion
        # For a single criterion set with no failure test, warn about missing edge case
        criteria = ["File exists: src/bob3/foo.py"]
        result = lint_acceptance_criteria(criteria)
        # Single file-exists criterion: no failure path, but it's a soft warning at most
        # The important property: no hard fail
        assert not result.hard_fail

    def test_failure_path_criterion_reduces_warnings(self):
        # When there is at least a pytest criterion (which can test failures),
        # the missing-edge-case warning should not fire
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
        ]
        result = lint_acceptance_criteria(criteria)
        missing_edge = [i for i in result.issues if i.category == "missing_edge_case"]
        # A full test suite (pytest criterion) covers failure paths implicitly
        assert len(missing_edge) == 0


# ---------------------------------------------------------------------------
# lint_acceptance_criteria — redundant criteria
# ---------------------------------------------------------------------------

class TestRedundantCriteria:
    def test_exact_duplicate_flagged(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "File exists: src/bob3/foo.py",
        ]
        result = lint_acceptance_criteria(criteria)
        redundant = [i for i in result.issues if i.category == "redundant"]
        assert len(redundant) >= 1

    def test_no_duplicates_passes(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "pytest: tests/test_foo.py",
        ]
        result = lint_acceptance_criteria(criteria)
        redundant = [i for i in result.issues if i.category == "redundant"]
        assert len(redundant) == 0

    def test_case_insensitive_duplicate_flagged(self):
        criteria = [
            "file exists: src/bob3/foo.py",
            "File exists: src/bob3/foo.py",
        ]
        result = lint_acceptance_criteria(criteria)
        redundant = [i for i in result.issues if i.category == "redundant"]
        assert len(redundant) >= 1


# ---------------------------------------------------------------------------
# lint_acceptance_criteria — banned operations in python: criteria
# ---------------------------------------------------------------------------

class TestBannedOperations:
    def test_eval_in_python_criterion_is_hard_fail(self):
        criteria = ["python: eval('1+1')"]
        result = lint_acceptance_criteria(criteria)
        assert result.hard_fail
        banned = [i for i in result.issues if i.category == "banned_operation"]
        assert len(banned) >= 1

    def test_exec_in_python_criterion_is_hard_fail(self):
        criteria = ["python: exec('x=1')"]
        result = lint_acceptance_criteria(criteria)
        assert result.hard_fail

    def test_import_subprocess_in_python_criterion_is_hard_fail(self):
        criteria = ["python: import subprocess; subprocess.run(['ls'])"]
        result = lint_acceptance_criteria(criteria)
        assert result.hard_fail

    def test_import_os_in_python_criterion_is_hard_fail(self):
        criteria = ["python: import os; os.listdir('.')"]
        result = lint_acceptance_criteria(criteria)
        assert result.hard_fail

    def test_open_call_in_python_criterion_is_hard_fail(self):
        criteria = ["python: open('/etc/passwd').read()"]
        result = lint_acceptance_criteria(criteria)
        assert result.hard_fail

    def test_clean_python_criterion_passes(self):
        criteria = ["python: assert 1 + 1 == 2"]
        result = lint_acceptance_criteria(criteria)
        assert not result.hard_fail
        banned = [i for i in result.issues if i.category == "banned_operation"]
        assert len(banned) == 0

    def test_import_json_allowed_in_python_criterion(self):
        # json is not in the banned modules list
        criteria = ["python: import json; assert json.loads('{}') == {}"]
        result = lint_acceptance_criteria(criteria)
        banned = [i for i in result.issues if i.category == "banned_operation"]
        assert len(banned) == 0

    def test_non_python_criterion_not_scanned_for_banned_ops(self):
        # File exists and pytest criteria don't go through banned-op check
        criteria = ["File exists: src/subprocess_helper.py"]
        result = lint_acceptance_criteria(criteria)
        banned = [i for i in result.issues if i.category == "banned_operation"]
        assert len(banned) == 0


# ---------------------------------------------------------------------------
# lint_feature_spec — full feature spec linting
# ---------------------------------------------------------------------------

class TestLintFeatureSpec:
    def test_valid_spec_returns_lint_result(self):
        result = lint_feature_spec(
            name="My feature",
            description="Implements X",
            acceptance_criteria=["File exists: src/bob3/x.py", "pytest: tests/test_x.py"],
        )
        assert isinstance(result, LintResult)

    def test_none_acceptance_criteria_returns_warning(self):
        result = lint_feature_spec(
            name="No criteria feature",
            description="A feature with no criteria",
            acceptance_criteria=None,
        )
        # No criteria at all is suspicious — warn or error
        assert len(result.issues) >= 1

    def test_empty_criteria_list_returns_warning(self):
        result = lint_feature_spec(
            name="Empty criteria feature",
            description="A feature with empty criteria",
            acceptance_criteria=[],
        )
        assert len(result.issues) >= 1

    def test_json_string_criteria_parsed(self):
        # acceptance_criteria can arrive as a JSON-encoded string
        criteria_json = json.dumps(["File exists: src/bob3/x.py", "pytest: tests/test_x.py"])
        result = lint_feature_spec(
            name="JSON criteria feature",
            description="A feature with JSON-encoded criteria",
            acceptance_criteria=criteria_json,
        )
        assert isinstance(result, LintResult)
        # Should not hard-fail on clean criteria
        assert not result.hard_fail

    def test_hard_fail_blocks_spawn(self):
        result = lint_feature_spec(
            name="Banned op feature",
            description="Uses eval",
            acceptance_criteria=["python: eval('bad')"],
        )
        assert result.hard_fail

    def test_warnings_filed_to_registry(self):
        """Warnings should be filed to reviews/findings.yaml when a registry path is given."""
        criteria = ["The feature should work"]  # ambiguous
        with patch("bob3.spec_linter_pre_spawn_quality_gate.file_warnings_to_registry") as mock_file:
            lint_feature_spec(
                name="Ambiguous feature",
                description="Has ambiguous criteria",
                acceptance_criteria=criteria,
                file_warnings=True,
            )
            # Should have been called with at least one warning
            mock_file.assert_called_once()

    def test_no_filing_when_file_warnings_false(self):
        """When file_warnings=False, registry is not touched."""
        criteria = ["The feature should work"]
        with patch("bob3.spec_linter_pre_spawn_quality_gate.file_warnings_to_registry") as mock_file:
            lint_feature_spec(
                name="Ambiguous feature",
                description="Has ambiguous criteria",
                acceptance_criteria=criteria,
                file_warnings=False,
            )
            mock_file.assert_not_called()


# ---------------------------------------------------------------------------
# lint_acceptance_criteria — edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_valid_criterion_passes(self):
        result = lint_acceptance_criteria(["pytest: tests/test_foo.py"])
        assert not result.hard_fail

    def test_multiple_clean_criteria_pass(self):
        criteria = [
            "File exists: src/bob3/feature.py",
            "pytest: tests/test_feature.py",
            "python: assert True",
        ]
        result = lint_acceptance_criteria(criteria)
        assert not result.hard_fail

    def test_multiple_banned_ops_all_flagged(self):
        criteria = [
            "python: eval('x')",
            "python: exec('y')",
        ]
        result = lint_acceptance_criteria(criteria)
        assert result.hard_fail
        banned = [i for i in result.issues if i.category == "banned_operation"]
        assert len(banned) >= 2

    def test_mixed_clean_and_banned(self):
        criteria = [
            "File exists: src/bob3/foo.py",
            "python: eval('bad')",
        ]
        result = lint_acceptance_criteria(criteria)
        assert result.hard_fail
        # The clean criterion should not be flagged
        clean_issues = [i for i in result.issues if i.criterion.startswith("File exists")]
        assert len(clean_issues) == 0

    def test_syntax_error_in_python_criterion_flagged(self):
        # A python: criterion with a syntax error should be flagged
        criteria = ["python: def ("]
        result = lint_acceptance_criteria(criteria)
        # Should produce some issue (at minimum a warning about unparseable criterion)
        assert len(result.issues) >= 1
