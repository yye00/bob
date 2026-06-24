"""Tests for bob73.integration_checker.check_reachability.

Covers:
- Module is importable from the feature list
- Unreachable module is reported as an issue
- Module that exists in workspace passes
- Module declared by sibling feature passes
- Invalid input raises ValueError
"""

from __future__ import annotations

import pytest

from bob73.integration_checker import check_reachability
from bob.spec_quality.integration_reachability import ReachabilityResult


class TestCheckReachabilityBasicBehavior:
    def test_empty_features_passes(self, tmp_path):
        result = check_reachability([], workspace=tmp_path)
        assert isinstance(result, ReachabilityResult)
        assert result.passed is True

    def test_no_integration_ac_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["pytest: tests/test_foo.py"]}]
        result = check_reachability(features, workspace=tmp_path)
        assert result.passed is True

    def test_importable_module_passes(self, tmp_path):
        # pathlib is always importable
        features = [{"name": "F1", "acceptance_criteria": ["integration: pathlib"]}]
        result = check_reachability(features, workspace=tmp_path)
        assert result.passed is True

    def test_workspace_file_module_passes(self, tmp_path):
        # Create a source file in workspace
        src = tmp_path / "src" / "mypackage"
        src.mkdir(parents=True)
        (src / "mymod.py").write_text("# mymod\n")
        features = [{"name": "F1", "acceptance_criteria": ["integration: mypackage.mymod"]}]
        result = check_reachability(features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_module_fails(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.nonexistent.module.xyz"]}]
        result = check_reachability(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].missing_module == "totally.nonexistent.module.xyz"
        assert result.issues[0].feature_name == "F1"

    def test_sibling_feature_integration_target_passes(self, tmp_path):
        # F2's integration target is declared by F1, so it's reachable via spec
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: mypackage.new_module"]},
            {"name": "F2", "acceptance_criteria": ["integration: mypackage.new_module"]},
        ]
        result = check_reachability(features, workspace=tmp_path)
        # Each feature's module is reachable because the sibling declares it
        assert result.passed is True

    def test_multiple_issues_reported(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: bad.module.one"]},
            {"name": "F2", "acceptance_criteria": ["integration: bad.module.two"]},
        ]
        result = check_reachability(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 2

    def test_format_report_on_failure(self, tmp_path):
        features = [{"name": "FeatureX", "acceptance_criteria": ["integration: no.such.module.abc"]}]
        result = check_reachability(features, workspace=tmp_path)
        report = result.format_report()
        assert "FAILED" in report
        assert "no.such.module.abc" in report

    def test_format_report_on_pass(self, tmp_path):
        result = check_reachability([], workspace=tmp_path)
        report = result.format_report()
        assert "PASSED" in report

    def test_none_ac_field_does_not_raise(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": None}]
        result = check_reachability(features, workspace=tmp_path)
        assert result.passed is True

    def test_default_workspace_does_not_raise(self):
        result = check_reachability([])
        assert result is not None

    def test_workspace_as_string(self, tmp_path):
        result = check_reachability([], workspace=str(tmp_path))
        assert result.passed is True


class TestCheckReachabilityInvalidInput:
    def test_none_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_reachability(None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_reachability("not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_integer_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_reachability(42, workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_reachability({"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]
