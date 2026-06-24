"""Tests for bob.spec_quality.ambiguity_linter.

Covers the public API: lint_feature, lint_spec, and the data structures
AmbiguityIssue, FeatureLintResult, and SpecLintReport.
"""

from __future__ import annotations

import pytest

from bob.spec_quality.ambiguity_linter import (
    AmbiguityIssue,
    FeatureLintResult,
    SpecLintReport,
    lint_feature,
    lint_spec,
)


# ---------------------------------------------------------------------------
# AmbiguityIssue
# ---------------------------------------------------------------------------

class TestAmbiguityIssue:
    def test_has_required_fields(self):
        issue = AmbiguityIssue(
            ac_index=0,
            criterion="works correctly",
            reason="bare verb",
        )
        assert issue.ac_index == 0
        assert issue.criterion == "works correctly"
        assert issue.reason == "bare verb"


# ---------------------------------------------------------------------------
# FeatureLintResult
# ---------------------------------------------------------------------------

class TestFeatureLintResult:
    def test_passed_when_no_issues(self):
        result = FeatureLintResult(feature_name="MyFeature")
        assert result.passed is True

    def test_failed_when_issues_present(self):
        result = FeatureLintResult(
            feature_name="MyFeature",
            issues=[AmbiguityIssue(ac_index=0, criterion="works", reason="bare verb")],
        )
        assert result.passed is False

    def test_feature_name_stored(self):
        result = FeatureLintResult(feature_name="SpecificFeature")
        assert result.feature_name == "SpecificFeature"


# ---------------------------------------------------------------------------
# SpecLintReport
# ---------------------------------------------------------------------------

class TestSpecLintReport:
    def test_passed_when_all_features_pass(self):
        report = SpecLintReport(
            feature_results=[
                FeatureLintResult(feature_name="F1"),
                FeatureLintResult(feature_name="F2"),
            ]
        )
        assert report.passed is True

    def test_failed_when_any_feature_fails(self):
        report = SpecLintReport(
            feature_results=[
                FeatureLintResult(feature_name="F1"),
                FeatureLintResult(
                    feature_name="F2",
                    issues=[AmbiguityIssue(ac_index=0, criterion="works", reason="bare verb")],
                ),
            ]
        )
        assert report.passed is False

    def test_failed_features_lists_only_failures(self):
        ok = FeatureLintResult(feature_name="OK")
        fail = FeatureLintResult(
            feature_name="Fail",
            issues=[AmbiguityIssue(ac_index=0, criterion="x", reason="y")],
        )
        report = SpecLintReport(feature_results=[ok, fail])
        assert report.failed_features == [fail]

    def test_format_report_pass(self):
        report = SpecLintReport(feature_results=[FeatureLintResult(feature_name="F1")])
        text = report.format_report()
        assert "PASSED" in text

    def test_format_report_fail_includes_feature_name(self):
        report = SpecLintReport(
            feature_results=[
                FeatureLintResult(
                    feature_name="MyFeature",
                    issues=[AmbiguityIssue(ac_index=2, criterion="works correctly", reason="bare verb")],
                )
            ]
        )
        text = report.format_report()
        assert "FAILED" in text
        assert "MyFeature" in text
        assert "AC[2]" in text

    def test_format_report_empty(self):
        report = SpecLintReport()
        text = report.format_report()
        assert "PASSED" in text


# ---------------------------------------------------------------------------
# lint_feature — accepted (structured) forms
# ---------------------------------------------------------------------------

class TestLintFeatureAcceptedForms:
    def test_file_exists_passes(self):
        result = lint_feature("F", ["File exists: src/bob/foo.py"])
        assert result.passed

    def test_file_exists_case_insensitive(self):
        result = lint_feature("F", ["file exists: src/bob/foo.py"])
        assert result.passed

    def test_function_defined_passes(self):
        result = lint_feature("F", ["Function defined: bob.module.my_func"])
        assert result.passed

    def test_class_defined_passes(self):
        result = lint_feature("F", ["Class defined: bob.module.MyClass"])
        assert result.passed

    def test_pytest_passes(self):
        result = lint_feature("F", ["pytest: tests/test_foo.py"])
        assert result.passed

    def test_pytest_with_node_id_passes(self):
        result = lint_feature("F", ["pytest: tests/test_foo.py::TestBar::test_baz"])
        assert result.passed

    def test_integration_passes(self):
        result = lint_feature("F", ["integration: bob.cli.plan"])
        assert result.passed

    def test_behavior_ears_style_passes(self):
        result = lint_feature("F", ["behavior: planner rejects spec when condition is ambiguous"])
        assert result.passed

    def test_multiple_valid_criteria_all_pass(self):
        criteria = [
            "File exists: src/bob/spec_quality/ambiguity_linter.py",
            "Function defined: bob.spec_quality.ambiguity_linter.lint_feature",
            "Function defined: bob.spec_quality.ambiguity_linter.lint_spec",
            "pytest: tests/test_ambiguity_linter.py",
            "integration: bob.cli.plan",
        ]
        result = lint_feature("FeatureUnderTest", criteria)
        assert result.passed
        assert result.issues == []


# ---------------------------------------------------------------------------
# lint_feature — rejected (ambiguous) forms
# ---------------------------------------------------------------------------

class TestLintFeatureRejectedForms:
    def test_empty_criterion_rejected(self):
        result = lint_feature("F", [""])
        assert not result.passed
        assert result.issues[0].ac_index == 0

    def test_plain_english_rejected(self):
        result = lint_feature("F", ["The module works correctly"])
        assert not result.passed

    def test_multiple_criteria_bad_one_caught(self):
        result = lint_feature("F", [
            "File exists: src/foo.py",
            "The system handles all cases",
        ])
        assert not result.passed
        assert len(result.issues) == 1
        assert result.issues[0].ac_index == 1

    def test_ac_index_preserved(self):
        result = lint_feature("F", [
            "pytest: tests/test_ok.py",
            "File exists: src/ok.py",
            "works correctly",
        ])
        assert not result.passed
        assert result.issues[0].ac_index == 2

    def test_no_criteria_returns_boundary_failure(self):
        # Zero-AC is a boundary failure: unverifiable feature.
        result = lint_feature("F", [])
        assert not result.passed
        assert len(result.issues) == 1
        assert "boundary failure" in result.issues[0].reason


# ---------------------------------------------------------------------------
# lint_spec
# ---------------------------------------------------------------------------

class TestLintSpec:
    def test_all_valid_features_pass(self):
        features = [
            {
                "name": "Feature A",
                "acceptance_criteria": [
                    "File exists: src/foo.py",
                    "pytest: tests/test_foo.py",
                ],
            },
            {
                "name": "Feature B",
                "acceptance_criteria": [
                    "Function defined: bob.foo.bar",
                ],
            },
        ]
        report = lint_spec(features)
        assert report.passed

    def test_vague_feature_causes_failure(self):
        features = [
            {
                "name": "Vague Feature",
                "acceptance_criteria": ["The system works correctly"],
            },
        ]
        report = lint_spec(features)
        assert not report.passed
        assert report.failed_features[0].feature_name == "Vague Feature"

    def test_mixed_features_one_bad(self):
        features = [
            {
                "name": "Good Feature",
                "acceptance_criteria": ["pytest: tests/test_good.py"],
            },
            {
                "name": "Bad Feature",
                "acceptance_criteria": ["it handles all cases"],
            },
        ]
        report = lint_spec(features)
        assert not report.passed
        failed = report.failed_features
        assert len(failed) == 1
        assert failed[0].feature_name == "Bad Feature"

    def test_empty_spec_passes(self):
        report = lint_spec([])
        assert report.passed

    def test_string_criteria_normalised(self):
        features = [
            {
                "name": "Single AC",
                "acceptance_criteria": "pytest: tests/test_single.py",
            },
        ]
        report = lint_spec(features)
        assert report.passed

    def test_feature_uses_title_fallback(self):
        features = [
            {
                "title": "Title Feature",
                "acceptance_criteria": ["The app supports anything"],
            },
        ]
        report = lint_spec(features)
        assert not report.passed
        assert report.failed_features[0].feature_name == "Title Feature"

    def test_unnamed_feature_handled(self):
        features = [
            {
                "acceptance_criteria": ["works"],
            },
        ]
        report = lint_spec(features)
        assert not report.passed
        assert "unnamed" in report.failed_features[0].feature_name.lower()

    def test_format_report_names_offending_feature_and_ac_index(self):
        features = [
            {
                "name": "OffendingFeature",
                "acceptance_criteria": [
                    "pytest: tests/test_ok.py",
                    "handles all input",
                ],
            },
        ]
        report = lint_spec(features)
        text = report.format_report()
        assert "OffendingFeature" in text
        assert "AC[1]" in text
