"""Tests for bob3.integration_target_validator.validate_integration_target."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.integration_target_validator import validate_integration_target


def _make_feature(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


class TestValidateIntegrationTarget:
    def test_empty_features_returns_passed(self, tmp_path):
        result = validate_integration_target(features=[], workspace=tmp_path)
        assert result is not None
        assert result.passed is True

    def test_default_call_returns_passed(self, tmp_path):
        result = validate_integration_target(workspace=tmp_path)
        assert result is not None
        assert result.passed is True

    def test_no_integration_acs_passes(self, tmp_path):
        features = [_make_feature("F1", "File exists: src/foo.py", "pytest: tests/test_foo.py")]
        result = validate_integration_target(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_file_exists_in_workspace(self, tmp_path):
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        features = [_make_feature("F1", "integration: mymodule")]
        result = validate_integration_target(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_module_importable(self, tmp_path):
        features = [_make_feature("F1", "integration: os")]
        result = validate_integration_target(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_sibling_feature_declares_target(self, tmp_path):
        features = [
            _make_feature("F1", "integration: future.module"),
            _make_feature("F2", "integration: future.module"),
        ]
        result = validate_integration_target(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_module_returns_failed(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        result = validate_integration_target(features=features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) >= 1

    def test_result_has_issues_attribute(self, tmp_path):
        result = validate_integration_target(features=[], workspace=tmp_path)
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_result_has_passed_attribute(self, tmp_path):
        result = validate_integration_target(features=[], workspace=tmp_path)
        assert hasattr(result, "passed")
        assert isinstance(result.passed, bool)

    def test_format_report_on_passed(self, tmp_path):
        result = validate_integration_target(features=[], workspace=tmp_path)
        report = result.format_report()
        assert isinstance(report, str)
        assert "PASSED" in report

    def test_format_report_on_failed_contains_module_name(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        result = validate_integration_target(features=features, workspace=tmp_path)
        report = result.format_report()
        assert "totally.nonexistent.xyz.module" in report

    def test_issue_tracks_feature_name(self, tmp_path):
        features = [_make_feature("MyFeature", "integration: totally.nonexistent.xyz.module")]
        result = validate_integration_target(features=features, workspace=tmp_path)
        assert result.issues[0].feature_name == "MyFeature"

    def test_multiple_features_only_unreachable_in_issues(self, tmp_path):
        features = [
            _make_feature("F1", "integration: os"),
            _make_feature("F2", "integration: totally.nonexistent.xyz.module"),
        ]
        result = validate_integration_target(features=features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].feature_name == "F2"

    def test_none_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_target(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_target(features="bad", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_target(features={"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]

    def test_reject_on_failure_raises_for_unreachable(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        with pytest.raises(ValueError):
            validate_integration_target(features=features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_false_returns_result(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        result = validate_integration_target(features=features, workspace=tmp_path, reject_on_failure=False)
        assert result.passed is False

    def test_reject_on_failure_true_passes_for_reachable(self, tmp_path):
        features = [_make_feature("F1", "integration: os")]
        result = validate_integration_target(features=features, workspace=tmp_path, reject_on_failure=True)
        assert result.passed is True
