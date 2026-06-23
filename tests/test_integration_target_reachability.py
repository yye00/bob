"""Tests for bob3.integration_target_reachability.verify_integration_target_reachable."""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.integration_target_reachability import verify_integration_target_reachable


class TestVerifyIntegrationTargetReachable:
    def test_reachable_when_file_exists_in_workspace(self, tmp_path):
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        result = verify_integration_target_reachable("mymodule", workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_module_exists_nested(self, tmp_path):
        src = tmp_path / "src" / "pkg" / "sub.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        result = verify_integration_target_reachable("pkg.sub", workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_returns_failed_result(self, tmp_path):
        result = verify_integration_target_reachable("totally.nonexistent.module.xyz", workspace=tmp_path)
        assert result.passed is False

    def test_reachable_when_importable_in_env(self, tmp_path):
        result = verify_integration_target_reachable("os", workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_module_in_spec(self, tmp_path):
        features = [{"name": "other", "acceptance_criteria": ["integration: future.module"]}]
        result = verify_integration_target_reachable("future.module", features=features, workspace=tmp_path)
        assert result.passed is True

    def test_empty_features_list_still_checks_workspace(self, tmp_path):
        result = verify_integration_target_reachable("nonexistent.xyz", features=[], workspace=tmp_path)
        assert result.passed is False

    def test_check_all_features_reachability(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: totally.missing.module.xyz"]},
        ]
        result = verify_integration_target_reachable(features=features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].feature_name == "F2"

    def test_all_reachable_returns_passed(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: os"]},
            {"name": "F2", "acceptance_criteria": ["integration: pathlib"]},
        ]
        result = verify_integration_target_reachable(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_no_integration_acs_returns_passed(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["pytest: tests/test_foo.py"]}]
        result = verify_integration_target_reachable(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_result_has_format_report(self, tmp_path):
        result = verify_integration_target_reachable(features=[], workspace=tmp_path)
        report = result.format_report()
        assert isinstance(report, str)

    def test_closest_match_in_report_on_failure(self, tmp_path):
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        features = [{"name": "F1", "acceptance_criteria": ["integration: mymodulee"]}]
        result = verify_integration_target_reachable(features=features, workspace=tmp_path)
        assert result is not None

    def test_reject_on_failure_raises_for_unreachable(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_target_reachable(
                "totally.missing.module.xyz",
                workspace=tmp_path,
                reject_on_failure=True,
            )

    def test_reject_on_failure_does_not_raise_when_reachable(self, tmp_path):
        result = verify_integration_target_reachable("os", workspace=tmp_path, reject_on_failure=True)
        assert result.passed is True
