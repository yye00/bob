"""Tests for bob76.integration_check.validate_integration_targets."""

from __future__ import annotations

import pytest
from pathlib import Path

from bob76.integration_check import validate_integration_targets


class TestValidateIntegrationTargets:
    def test_reachable_when_file_exists_in_workspace(self, tmp_path):
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        features = [{"name": "F1", "acceptance_criteria": ["integration: mymodule"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_module_exists_nested(self, tmp_path):
        src = tmp_path / "src" / "pkg" / "sub.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        features = [{"name": "F1", "acceptance_criteria": ["integration: pkg.sub"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_returns_failed_result(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.nonexistent.module.xyz"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False

    def test_reachable_when_importable_in_env(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: os"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_module_in_spec_sibling(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: future.module"]},
            {"name": "F2", "acceptance_criteria": ["integration: future.module"]},
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_empty_features_list_returns_passed(self, tmp_path):
        result = validate_integration_targets(features=[], workspace=tmp_path)
        assert result.passed is True

    def test_check_all_features_reachability(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: totally.missing.module.xyz"]},
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].feature_name == "F2"

    def test_all_reachable_returns_passed(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: pathlib"]},
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_no_integration_acs_returns_passed(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["pytest: tests/test_foo.py"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_result_has_format_report(self, tmp_path):
        result = validate_integration_targets(features=[], workspace=tmp_path)
        report = result.format_report()
        assert isinstance(report, str)
        assert "PASSED" in report

    def test_reject_on_failure_raises_value_error(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.missing.module.xyz"]}]
        with pytest.raises(ValueError, match="Integration-target reachability"):
            validate_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_does_not_raise_when_passed(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: os"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)
        assert result.passed is True

    def test_none_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_non_list_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features="not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_format_report_on_failure_names_module(self, tmp_path):
        features = [{"name": "MyFeature", "acceptance_criteria": ["integration: missing.xyz.module"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        report = result.format_report()
        assert "missing.xyz.module" in report
        assert "FAILED" in report
