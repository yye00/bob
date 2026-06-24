"""Tests that lint_feature returns a boundary failure for zero ACs edge case."""

from __future__ import annotations

import pytest

from bob.spec_quality.ambiguity_linter import lint_feature, FeatureLintResult


class TestEmptyACListBoundaryFailure:
    def test_empty_ac_list_returns_boundary_failure(self):
        feature = {"name": "EmptyFeature", "acceptance_criteria": []}
        result = lint_feature(feature["name"], feature["acceptance_criteria"])
        assert not result.passed, "lint_feature should return failure for empty AC list"
        assert len(result.issues) == 1
        assert "boundary failure" in result.issues[0].reason

    def test_empty_ac_list_issue_describes_zero_acs(self):
        result = lint_feature("ZeroACFeature", [])
        assert not result.passed
        assert result.issues[0].ac_index == 0
        assert "zero acceptance criteria" in result.issues[0].reason

    def test_empty_ac_list_feature_name_preserved(self):
        result = lint_feature("MyFeature", [])
        assert result.feature_name == "MyFeature"
        assert not result.passed

    def test_none_replaced_with_empty_gives_boundary_failure(self):
        # Simulates what lint_spec does when ac_raw is empty.
        result = lint_feature("Feature", [])
        assert not result.passed

    def test_single_valid_ac_does_not_trigger_boundary_failure(self):
        # Boundary failure is only for zero ACs.
        result = lint_feature("Feature", ["File exists: src/bob/foo.py"])
        assert result.passed

    def test_boundary_failure_is_distinct_from_ambiguity_failure(self):
        result = lint_feature("Feature", [])
        assert not result.passed
        # Boundary failure has no criterion (empty string)
        assert result.issues[0].criterion == ""
