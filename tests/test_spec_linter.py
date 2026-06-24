"""Tests for the spec_linter public API.

Covers:
  - lint_acceptance_criteria: returns list[LintIssue]
  - LintIssue fields: ac_index, criterion, reason
  - LintReport: passed, format_report()
  - CLI command: lint-specs (via Click test runner)
"""

from __future__ import annotations

import json
import os
import textwrap
import tempfile
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from spec_linter import (
    LintIssue,
    LintReport,
    lint_acceptance_criteria,
)
from bob.cli import main


# ---------------------------------------------------------------------------
# lint_acceptance_criteria — basic correctness
# ---------------------------------------------------------------------------

class TestLintAcceptanceCriteria:
    def test_valid_criteria_return_empty_list(self):
        issues = lint_acceptance_criteria("MyFeature", [
            "File exists: src/foo.py",
            "pytest: tests/test_foo.py",
        ])
        assert issues == []

    def test_returns_list_of_lint_issues(self):
        issues = lint_acceptance_criteria("MyFeature", ["works correctly"])
        assert isinstance(issues, list)
        assert len(issues) == 1
        assert isinstance(issues[0], LintIssue)

    def test_vague_criterion_flagged(self):
        issues = lint_acceptance_criteria("MyFeature", ["works correctly"])
        assert len(issues) >= 1
        assert any("works" in issue.reason or "does not match" in issue.reason
                   for issue in issues)

    def test_issue_has_correct_ac_index(self):
        issues = lint_acceptance_criteria("MyFeature", [
            "File exists: src/foo.py",  # index 0, ok
            "handles any input",        # index 1, bad
        ])
        assert len(issues) == 1
        assert issues[0].ac_index == 1

    def test_issue_has_criterion_text(self):
        issues = lint_acceptance_criteria("MyFeature", ["supports all formats"])
        assert len(issues) >= 1
        assert "supports all formats" in issues[0].criterion

    def test_issue_has_reason_string(self):
        issues = lint_acceptance_criteria("MyFeature", ["works correctly"])
        assert issues[0].reason
        assert isinstance(issues[0].reason, str)

    def test_empty_ac_list_flags_boundary_failure(self):
        issues = lint_acceptance_criteria("MyFeature", [])
        assert len(issues) >= 1

    def test_multiple_bad_criteria_all_flagged(self):
        issues = lint_acceptance_criteria("MyFeature", [
            "handles any input",
            "works for all cases",
            "performs correctly",
        ])
        assert len(issues) == 3

    def test_mixed_valid_and_invalid(self):
        issues = lint_acceptance_criteria("MyFeature", [
            "File exists: src/foo.py",
            "works correctly",
            "pytest: tests/test_foo.py",
        ])
        assert len(issues) == 1
        assert issues[0].ac_index == 1

    def test_function_defined_form_accepted(self):
        issues = lint_acceptance_criteria("MyFeature", [
            "Function defined: bob.module.func",
        ])
        assert issues == []

    def test_class_defined_form_accepted(self):
        issues = lint_acceptance_criteria("MyFeature", [
            "Class defined: bob.module.MyClass",
        ])
        assert issues == []

    def test_integration_form_accepted(self):
        issues = lint_acceptance_criteria("MyFeature", [
            "integration: bob.cli.plan",
        ])
        assert issues == []

    def test_unbounded_quantifier_detected(self):
        issues = lint_acceptance_criteria("F", ["everything works correctly"])
        assert len(issues) >= 1

    def test_bare_verb_handles_detected(self):
        issues = lint_acceptance_criteria("F", ["the system handles errors"])
        assert len(issues) >= 1


# ---------------------------------------------------------------------------
# LintIssue dataclass
# ---------------------------------------------------------------------------

class TestLintIssue:
    def test_fields_accessible(self):
        issue = LintIssue(ac_index=2, criterion="works", reason="bare verb")
        assert issue.ac_index == 2
        assert issue.criterion == "works"
        assert issue.reason == "bare verb"


# ---------------------------------------------------------------------------
# LintReport
# ---------------------------------------------------------------------------

class TestLintReport:
    def test_passed_when_no_issues(self):
        report = LintReport(feature_name="F")
        assert report.passed is True

    def test_failed_when_issues_present(self):
        report = LintReport(
            feature_name="F",
            issues=[LintIssue(ac_index=0, criterion="works", reason="bare verb")],
        )
        assert report.passed is False

    def test_format_report_passed(self):
        report = LintReport(feature_name="MyFeature")
        text = report.format_report()
        assert "PASSED" in text
        assert "MyFeature" in text

    def test_format_report_failed_contains_feature_name(self):
        report = LintReport(
            feature_name="BrokenFeature",
            issues=[LintIssue(ac_index=0, criterion="works", reason="bare verb")],
        )
        text = report.format_report()
        assert "FAILED" in text
        assert "BrokenFeature" in text

    def test_format_report_contains_ac_index(self):
        report = LintReport(
            feature_name="F",
            issues=[LintIssue(ac_index=3, criterion="works", reason="bare verb")],
        )
        text = report.format_report()
        assert "AC[3]" in text

    def test_format_report_contains_criterion(self):
        report = LintReport(
            feature_name="F",
            issues=[LintIssue(ac_index=0, criterion="works correctly", reason="bare verb")],
        )
        text = report.format_report()
        assert "works correctly" in text


# ---------------------------------------------------------------------------
# CLI command: lint-specs
# ---------------------------------------------------------------------------

class TestLintSpecsCLI:
    def _make_spec_file(self, features: list[dict], suffix: str = ".yaml") -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False
        )
        yaml.dump(features, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_lint_specs_passes_clean_spec(self):
        runner = CliRunner()
        spec = self._make_spec_file([
            {
                "name": "Clean Feature",
                "acceptance_criteria": [
                    "File exists: src/foo.py",
                    "pytest: tests/test_foo.py",
                ],
            }
        ])
        try:
            result = runner.invoke(main, ["lint-specs", str(spec)])
            assert result.exit_code == 0, result.output
            assert "PASSED" in result.output
        finally:
            spec.unlink(missing_ok=True)

    def test_lint_specs_fails_vague_spec(self):
        runner = CliRunner()
        spec = self._make_spec_file([
            {
                "name": "Vague Feature",
                "acceptance_criteria": [
                    "works correctly",
                ],
            }
        ])
        try:
            result = runner.invoke(main, ["lint-specs", str(spec)])
            assert result.exit_code != 0, result.output
            assert "FAILED" in result.output or "Vague Feature" in result.output
        finally:
            spec.unlink(missing_ok=True)

    def test_lint_specs_reports_offending_feature(self):
        runner = CliRunner()
        spec = self._make_spec_file([
            {
                "name": "BadFeature",
                "acceptance_criteria": ["handles any input"],
            }
        ])
        try:
            result = runner.invoke(main, ["lint-specs", str(spec)])
            assert "BadFeature" in result.output
        finally:
            spec.unlink(missing_ok=True)

    def test_lint_specs_reports_offending_ac_index(self):
        runner = CliRunner()
        spec = self._make_spec_file([
            {
                "name": "F",
                "acceptance_criteria": [
                    "File exists: src/ok.py",
                    "works correctly",
                ],
            }
        ])
        try:
            result = runner.invoke(main, ["lint-specs", str(spec)])
            assert "AC[1]" in result.output
        finally:
            spec.unlink(missing_ok=True)

    def test_lint_specs_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(main, ["lint-specs", "--help"])
        assert result.exit_code == 0

    def test_lint_specs_missing_file_error(self):
        runner = CliRunner()
        result = runner.invoke(main, ["lint-specs", "/no/such/file.yaml"])
        assert result.exit_code != 0

    def test_lint_specs_json_output_flag(self):
        runner = CliRunner()
        spec = self._make_spec_file([
            {
                "name": "F",
                "acceptance_criteria": ["works correctly"],
            }
        ])
        try:
            result = runner.invoke(main, ["lint-specs", "--json", str(spec)])
            data = json.loads(result.output)
            assert isinstance(data, dict)
            assert "passed" in data
            assert data["passed"] is False
        finally:
            spec.unlink(missing_ok=True)

    def test_lint_specs_multiple_features_all_reported(self):
        runner = CliRunner()
        spec = self._make_spec_file([
            {"name": "F1", "acceptance_criteria": ["works correctly"]},
            {"name": "F2", "acceptance_criteria": ["handles any input"]},
        ])
        try:
            result = runner.invoke(main, ["lint-specs", str(spec)])
            assert "F1" in result.output
            assert "F2" in result.output
        finally:
            spec.unlink(missing_ok=True)
