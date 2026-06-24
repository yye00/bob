"""Tests that lint_feature handles minimum one-AC input without error."""

from __future__ import annotations

import pytest

from bob.spec_quality.ambiguity_linter import lint_feature


class TestSingleACBoundary:
    def test_single_valid_ac_passes(self):
        result = lint_feature("F", ["File exists: src/bob/foo.py"])
        assert result.passed
        assert result.issues == []

    def test_single_invalid_ac_fails(self):
        result = lint_feature("F", ["works correctly"])
        assert not result.passed
        assert len(result.issues) == 1

    def test_single_ac_function_defined(self):
        result = lint_feature("F", ["Function defined: bob.module.func"])
        assert result.passed

    def test_single_ac_pytest(self):
        result = lint_feature("F", ["pytest: tests/test_something.py"])
        assert result.passed

    def test_single_ac_integration(self):
        result = lint_feature("F", ["integration: bob.cli.plan"])
        assert result.passed

    def test_single_ac_behavior_ears(self):
        result = lint_feature("F", ["behavior: system rejects request when input is malformed"])
        assert result.passed

    def test_single_ac_bare_verb_reported_at_index_zero(self):
        result = lint_feature("F", ["handles errors"])
        assert not result.passed
        assert result.issues[0].ac_index == 0

    def test_single_ac_does_not_raise(self):
        # Boundary check: must not raise, only return FeatureLintResult.
        try:
            result = lint_feature("BoundaryFeature", ["File exists: src/ok.py"])
            assert result is not None
        except Exception as exc:
            pytest.fail(f"lint_feature raised unexpectedly: {exc}")
