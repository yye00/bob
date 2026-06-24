"""Tests that the ambiguity linter rejects specific vague AC patterns.

Focused tests for each rejection category:
- Bare verbs ("works", "handles", "supports")
- Missing concrete identifiers (no file path, function name, test path)
- Unbounded quantifiers ("all cases", "any input")
- Verbs without an observable subject
"""

from __future__ import annotations

import pytest

from bob.spec_quality.ambiguity_linter import lint_feature, lint_spec


# ---------------------------------------------------------------------------
# Bare verb rejections
# ---------------------------------------------------------------------------

class TestBareVerbRejection:
    def test_rejects_works(self):
        result = lint_feature("F", ["The module works correctly"])
        assert not result.passed
        assert any("bare verb" in issue.reason for issue in result.issues)

    def test_rejects_handles(self):
        result = lint_feature("F", ["The system handles errors"])
        assert not result.passed
        assert any("bare verb" in issue.reason for issue in result.issues)

    def test_rejects_supports(self):
        result = lint_feature("F", ["The feature supports all formats"])
        assert not result.passed
        assert any("bare verb" in issue.reason for issue in result.issues)

    def test_rejects_it_works(self):
        result = lint_feature("F", ["it works as expected"])
        assert not result.passed

    def test_rejects_system_works(self):
        result = lint_feature("F", ["system works under load"])
        assert not result.passed


# ---------------------------------------------------------------------------
# Unbounded quantifier rejections
# ---------------------------------------------------------------------------

class TestUnboundedQuantifierRejection:
    def test_rejects_all_cases(self):
        result = lint_feature("F", ["handles all cases correctly"])
        assert not result.passed
        assert any("unbounded quantifier" in issue.reason for issue in result.issues)

    def test_rejects_any_input(self):
        result = lint_feature("F", ["processes any input without error"])
        assert not result.passed
        assert any("unbounded quantifier" in issue.reason for issue in result.issues)

    def test_rejects_everything(self):
        result = lint_feature("F", ["works for everything"])
        assert not result.passed
        assert any("unbounded quantifier" in issue.reason for issue in result.issues)

    def test_rejects_always_works(self):
        result = lint_feature("F", ["feature always works"])
        assert not result.passed
        assert any("unbounded quantifier" in issue.reason for issue in result.issues)


# ---------------------------------------------------------------------------
# Missing concrete identifier rejections
# ---------------------------------------------------------------------------

class TestMissingConcreteIdentifierRejection:
    def test_rejects_plain_english_no_prefix(self):
        result = lint_feature("F", ["The output should be correct"])
        assert not result.passed

    def test_rejects_english_with_numeric(self):
        result = lint_feature("F", ["returns 42"])
        assert not result.passed

    def test_rejects_no_file_no_function_no_test(self):
        result = lint_feature("F", ["performs the computation"])
        assert not result.passed

    def test_rejects_vague_verify(self):
        # A bare "verify something" without the structured "verify: <subject>" form
        result = lint_feature("F", ["verifies the result"])
        assert not result.passed

    def test_accepts_file_exists_with_path(self):
        result = lint_feature("F", ["File exists: src/bob/foo.py"])
        assert result.passed

    def test_accepts_function_defined_dotted_path(self):
        result = lint_feature("F", ["Function defined: bob.module.func"])
        assert result.passed

    def test_accepts_pytest_with_test_path(self):
        result = lint_feature("F", ["pytest: tests/test_specific.py::TestClass::test_method"])
        assert result.passed

    def test_accepts_integration_with_module(self):
        result = lint_feature("F", ["integration: bob.cli.plan"])
        assert result.passed


# ---------------------------------------------------------------------------
# Mixed valid/invalid AC lists
# ---------------------------------------------------------------------------

class TestMixedCriteria:
    def test_single_bad_ac_in_long_list_is_caught(self):
        criteria = [
            "File exists: src/bob/spec_quality/ambiguity_linter.py",
            "Function defined: bob.spec_quality.ambiguity_linter.lint_feature",
            "pytest: tests/test_ambiguity_linter.py",
            "works correctly",  # bad
        ]
        result = lint_feature("Feature", criteria)
        assert not result.passed
        assert len(result.issues) == 1
        assert result.issues[0].criterion == "works correctly"

    def test_multiple_bad_acs_all_caught(self):
        criteria = [
            "handles any input",
            "works for all cases",
            "performs correctly",
        ]
        result = lint_feature("BadFeature", criteria)
        assert not result.passed
        assert len(result.issues) == 3

    def test_all_valid_criteria_pass(self):
        criteria = [
            "File exists: src/bob/spec_quality/ambiguity_linter.py",
            "Function defined: bob.spec_quality.ambiguity_linter.lint_feature",
            "Function defined: bob.spec_quality.ambiguity_linter.lint_spec",
            "pytest: tests/test_ambiguity_linter.py",
            "pytest: tests/test_ambiguity_linter_rejects_vague_ac.py",
            "integration: bob.cli.plan",
        ]
        result = lint_feature("SpecAmbiguityLinter", criteria)
        assert result.passed
        assert result.issues == []


# ---------------------------------------------------------------------------
# lint_spec structured report
# ---------------------------------------------------------------------------

class TestLintSpecReport:
    def test_report_names_offending_feature(self):
        features = [
            {
                "name": "Vague Feature One",
                "acceptance_criteria": ["handles all cases"],
            },
            {
                "name": "Vague Feature Two",
                "acceptance_criteria": ["works for any input"],
            },
        ]
        report = lint_spec(features)
        assert not report.passed
        text = report.format_report()
        assert "Vague Feature One" in text
        assert "Vague Feature Two" in text

    def test_report_includes_ac_index_for_each_offending_criterion(self):
        features = [
            {
                "name": "Feature",
                "acceptance_criteria": [
                    "File exists: src/ok.py",  # index 0, ok
                    "works correctly",          # index 1, bad
                    "pytest: tests/ok.py",      # index 2, ok
                    "handles any input",        # index 3, bad
                ],
            }
        ]
        report = lint_spec(features)
        assert not report.passed
        text = report.format_report()
        assert "AC[1]" in text
        assert "AC[3]" in text
        assert "AC[0]" not in text
        assert "AC[2]" not in text

    def test_clean_spec_produces_pass_report(self):
        features = [
            {
                "name": "Clean Feature",
                "acceptance_criteria": [
                    "File exists: src/clean.py",
                    "pytest: tests/test_clean.py",
                ],
            }
        ]
        report = lint_spec(features)
        assert report.passed
        text = report.format_report()
        assert "PASSED" in text
