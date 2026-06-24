"""Tests for bob72.integration_validator.validate_integration_targets.

Verifies:
- validate_integration_targets returns a passed result for empty feature list.
- validate_integration_targets returns passed when integration targets are reachable.
- validate_integration_targets returns failed result with issues when targets are unreachable.
- validate_integration_targets raises ValueError on non-list input.
- Result object has .passed, .issues, and .format_report().
- Each issue names the missing module and the feature name.
- Integration target that exists in the workspace passes.
- Integration target named in another feature (sibling) passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob72.integration_validator import validate_integration_targets


def _make_feature(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


class TestValidateIntegrationTargetsBasic:
    def test_empty_list_returns_passed(self, tmp_path):
        result = validate_integration_targets([], workspace=tmp_path)
        assert result.passed is True

    def test_features_without_integration_acs_pass(self, tmp_path):
        features = [
            _make_feature("F1", "File exists: src/foo.py", "pytest: tests/test_foo.py"),
        ]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_module_returns_failed_result(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.missing.module.xyz")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].missing_module == "totally.missing.module.xyz"

    def test_issue_names_feature(self, tmp_path):
        features = [_make_feature("MyFeature", "integration: no.such.module")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.issues[0].feature_name == "MyFeature"

    def test_result_has_format_report(self, tmp_path):
        features = [_make_feature("F1", "integration: missing.mod")]
        result = validate_integration_targets(features, workspace=tmp_path)
        report = result.format_report()
        assert "missing.mod" in report
        assert "FAILED" in report

    def test_module_in_workspace_passes(self, tmp_path):
        mod_path = tmp_path / "src" / "mypackage"
        mod_path.mkdir(parents=True)
        (mod_path / "utils.py").touch()
        features = [_make_feature("F1", "integration: mypackage.utils")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_module_in_sibling_feature_passes(self, tmp_path):
        features = [
            _make_feature("F1", "integration: newmod.core"),
            _make_feature("F2", "integration: newmod.core"),
        ]
        result = validate_integration_targets(features, workspace=tmp_path)
        # F1's target is reachable via F2 and vice versa.
        assert result.passed is True

    def test_multiple_unreachable_modules_all_reported(self, tmp_path):
        features = [
            _make_feature("F1", "integration: alpha.missing"),
            _make_feature("F2", "integration: beta.missing"),
        ]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is False
        missing = {i.missing_module for i in result.issues}
        assert "alpha.missing" in missing
        assert "beta.missing" in missing

    def test_passed_result_format_report_says_passed(self, tmp_path):
        result = validate_integration_targets([], workspace=tmp_path)
        report = result.format_report()
        assert "PASSED" in report


class TestValidateIntegrationTargetsInvalidInput:
    def test_non_list_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets("not a list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_integer_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(42, workspace=tmp_path)  # type: ignore[arg-type]
