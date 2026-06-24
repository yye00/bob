"""Tests that the ambiguity linter accepts all structured AC forms."""

from __future__ import annotations

import pytest

from bob3.spec_quality.ambiguity_linter import lint_feature, is_ambiguous_ac, has_concrete_identifier


class TestAcceptsStructuredForms:
    def test_file_exists(self):
        result = lint_feature("F", ["File exists: src/bob3/spec_quality/ambiguity_linter.py"])
        assert result.passed

    def test_file_exists_case_insensitive(self):
        result = lint_feature("F", ["file exists: src/bob3/foo.py"])
        assert result.passed

    def test_function_defined(self):
        result = lint_feature("F", ["Function defined: bob3.spec_quality.ambiguity_linter.lint_feature"])
        assert result.passed

    def test_class_defined(self):
        result = lint_feature("F", ["Class defined: bob3.module.MyClass"])
        assert result.passed

    def test_pytest_path(self):
        result = lint_feature("F", ["pytest: tests/test_ambiguity_linter.py"])
        assert result.passed

    def test_pytest_with_node_id(self):
        result = lint_feature("F", ["pytest: tests/test_foo.py::TestBar::test_baz"])
        assert result.passed

    def test_integration_module(self):
        result = lint_feature("F", ["integration: bob3.cli.plan"])
        assert result.passed

    def test_behavior_ears_style(self):
        result = lint_feature("F", ["behavior: planner rejects spec when AC is ambiguous"])
        assert result.passed

    def test_all_forms_together(self):
        criteria = [
            "File exists: src/bob3/spec_quality/ambiguity_linter.py",
            "Function defined: bob3.spec_quality.ambiguity_linter.lint_feature",
            "Function defined: bob3.spec_quality.ambiguity_linter.lint_spec",
            "Class defined: bob3.spec_quality.ambiguity_linter.FeatureLintResult",
            "pytest: tests/test_ambiguity_linter.py",
            "integration: bob3.cli.plan",
            "behavior: linter fails plan when any AC is ambiguous",
        ]
        result = lint_feature("AllForms", criteria)
        assert result.passed
        assert result.issues == []

    def test_is_ambiguous_ac_returns_false_for_structured_form(self):
        assert is_ambiguous_ac("File exists: src/foo.py") is False
        assert is_ambiguous_ac("Function defined: bob3.foo.bar") is False
        assert is_ambiguous_ac("pytest: tests/test_foo.py") is False

    def test_is_ambiguous_ac_returns_true_for_bare_verb(self):
        assert is_ambiguous_ac("the module works correctly") is True
        assert is_ambiguous_ac("it handles errors") is True
        assert is_ambiguous_ac("feature supports all formats") is True

    def test_has_concrete_identifier_true_for_structured_forms(self):
        assert has_concrete_identifier("File exists: src/foo.py") is True
        assert has_concrete_identifier("Function defined: bob3.foo.bar") is True
        assert has_concrete_identifier("pytest: tests/test_foo.py") is True

    def test_has_concrete_identifier_false_for_vague_text(self):
        assert has_concrete_identifier("works correctly") is False
        assert has_concrete_identifier("handles all cases") is False

    def test_has_concrete_identifier_false_for_empty(self):
        assert has_concrete_identifier("") is False
