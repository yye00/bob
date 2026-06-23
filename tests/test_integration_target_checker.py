"""Tests for bob3.integration_target_checker.verify_integration_targets."""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.integration_target_checker import verify_integration_targets


class TestVerifyIntegrationTargets:
    def test_empty_features_list_returns_passed(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert result is not None
        assert result.passed is True

    def test_no_args_returns_passed(self):
        result = verify_integration_targets()
        assert result is not None
        assert result.passed is True

    def test_reachable_module_in_workspace_passes(self, tmp_path):
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        features = [{"name": "F1", "acceptance_criteria": ["integration: mymodule"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_importable_module_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: os"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_module_fails(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.nonexistent.module.xyz"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False

    def test_unreachable_module_recorded_as_issue(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.nonexistent.module.xyz"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert len(result.issues) == 1
        assert result.issues[0].feature_name == "F1"

    def test_module_in_sibling_spec_feature_passes(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: future.module"]},
            {"name": "F2", "acceptance_criteria": ["integration: future.module"]},
        ]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_all_importable_modules_pass(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: pathlib"]},
        ]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_non_integration_acs_ignored(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["pytest: tests/test_foo.py"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_none_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features="not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features={"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]

    def test_reject_on_failure_raises_for_unreachable(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.nonexistent.module.xyz"]}]
        with pytest.raises(ValueError):
            verify_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_does_not_raise_when_all_reachable(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: os"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)
        assert result.passed is True

    def test_result_has_format_report(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        report = result.format_report()
        assert isinstance(report, str)

    def test_result_has_issues_list(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_feature_with_empty_ac_list_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": []}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_mixed_reachable_and_unreachable_fails(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: totally.missing.module.xyz"]},
        ]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].feature_name == "F2"
