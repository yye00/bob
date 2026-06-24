"""Tests for bob3.spec_loader.validate_integration_targets.

Verifies that validate_integration_targets correctly checks reachability of
every ``integration: <dotted.module>`` AC at spec-load time.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.spec_loader import validate_integration_targets


class TestValidateIntegrationTargets:
    def test_empty_features_list_passes(self, tmp_path):
        result = validate_integration_targets(features=[], workspace=tmp_path)
        assert result.passed is True

    def test_no_args_returns_result(self):
        result = validate_integration_targets()
        assert result is not None
        assert result.passed is True

    def test_features_with_no_integration_acs_pass(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["pytest: tests/test_f1.py"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_module_in_workspace_passes(self, tmp_path):
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        features = [{"name": "F1", "acceptance_criteria": ["integration: mymodule"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_importable_module_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: os"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_module_fails(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.missing.xyz.module"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False

    def test_unreachable_module_creates_issue(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.missing.xyz.module"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert len(result.issues) == 1
        assert result.issues[0].missing_module == "totally.missing.xyz.module"

    def test_unreachable_module_issue_carries_feature_name(self, tmp_path):
        features = [{"name": "MyFeature", "acceptance_criteria": ["integration: totally.missing.xyz.module"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.issues[0].feature_name == "MyFeature"

    def test_none_input_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_input_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features="bad", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_input_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features={"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]

    def test_reject_on_failure_raises_for_unreachable(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.missing.xyz.module"]}]
        with pytest.raises(ValueError):
            validate_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_does_not_raise_when_all_reachable(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: os"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)
        assert result.passed is True

    def test_module_reachable_via_sibling_spec_feature_passes(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: future.module"]},
            {"name": "F2", "acceptance_criteria": ["integration: future.module"]},
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_result_has_format_report(self, tmp_path):
        result = validate_integration_targets(features=[], workspace=tmp_path)
        assert isinstance(result.format_report(), str)

    def test_format_report_on_failure_contains_module_name(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.missing.xyz.module"]}]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        report = result.format_report()
        assert "totally.missing.xyz.module" in report

    def test_multiple_features_some_failing(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: totally.missing.xyz.module"]},
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].feature_name == "F2"

    def test_all_reachable_no_issues(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: pathlib"]},
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True
        assert result.issues == []
