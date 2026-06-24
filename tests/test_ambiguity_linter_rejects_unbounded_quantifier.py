"""Tests that the ambiguity linter rejects ACs with unbounded quantifiers."""

from __future__ import annotations

import pytest

from bob.spec_quality.ambiguity_linter import lint_feature


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

    def test_structured_ac_with_quantifier_in_text_accepts(self):
        # A structured form is accepted even if the text contains quantifier-like words.
        result = lint_feature("F", ["Function defined: bob.module.handle_all_cases"])
        assert result.passed

    def test_rejects_all_cases_at_end(self):
        result = lint_feature("F", ["validates for all cases"])
        assert not result.passed
        assert any("unbounded quantifier" in issue.reason for issue in result.issues)

    def test_rejects_any_input_mid_sentence(self):
        result = lint_feature("F", ["module accepts any input and returns result"])
        assert not result.passed
        assert any("unbounded quantifier" in issue.reason for issue in result.issues)
