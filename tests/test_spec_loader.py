"""Tests for bob3.spec_loader.verify_integration_targets."""

from __future__ import annotations

from pathlib import Path

import pytest

from bob3.spec_loader import validate_integration_targets, verify_integration_targets, check_integration_reachability
from bob3.spec_quality.integration_reachability import ReachabilityResult


def _feat(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


class TestReturnType:
    def test_returns_reachability_result(self, tmp_path):
        result = verify_integration_targets([], workspace=tmp_path)
        assert isinstance(result, ReachabilityResult)

    def test_result_has_passed_attribute(self, tmp_path):
        result = verify_integration_targets([], workspace=tmp_path)
        assert hasattr(result, "passed")
        assert isinstance(result.passed, bool)

    def test_result_has_issues_attribute(self, tmp_path):
        result = verify_integration_targets([], workspace=tmp_path)
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)


class TestEmptyCases:
    def test_empty_list_passes(self, tmp_path):
        result = verify_integration_targets([], workspace=tmp_path)
        assert result.passed is True

    def test_no_args_passes(self):
        result = verify_integration_targets()
        assert result.passed is True

    def test_non_integration_ac_ignored(self, tmp_path):
        features = [_feat("F1", "File exists: src/foo.py", "pytest: tests/test_foo.py")]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_feature_with_no_acs_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": []}]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


class TestWorkspaceReachability:
    def test_module_as_src_file_passes(self, tmp_path):
        p = tmp_path / "src" / "myapp" / "utils.py"
        p.parent.mkdir(parents=True)
        p.write_text("")
        features = [_feat("F1", "integration: myapp.utils")]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_missing_module_fails(self, tmp_path):
        features = [_feat("F1", "integration: totally.absent.module.xyz")]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].missing_module == "totally.absent.module.xyz"


class TestSiblingFeatureReachability:
    def test_sibling_integration_target_passes(self, tmp_path):
        features = [
            _feat("F1", "integration: myapp.new_mod"),
            _feat("F2", "integration: myapp.new_mod"),
        ]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


class TestImportableModule:
    def test_stdlib_module_passes(self, tmp_path):
        features = [_feat("F1", "integration: os")]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_pathlib_passes(self, tmp_path):
        features = [_feat("F1", "integration: pathlib")]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


class TestMultipleFeaturesAndACs:
    def test_multiple_features_one_missing(self, tmp_path):
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "good.py").write_text("")
        features = [
            _feat("F1", "integration: pkg.good"),
            _feat("F2", "integration: pkg.absent.module"),
        ]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is False
        assert any(i.feature_name == "F2" for i in result.issues)
        assert all(i.feature_name != "F1" for i in result.issues)

    def test_all_reachable_passes(self, tmp_path):
        (tmp_path / "src" / "alpha").mkdir(parents=True)
        (tmp_path / "src" / "alpha" / "beta.py").write_text("")
        features = [
            _feat("F1", "integration: alpha.beta"),
            _feat("F2", "integration: os"),
        ]
        result = verify_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


class TestFormatReport:
    def test_format_report_passed(self, tmp_path):
        result = verify_integration_targets([], workspace=tmp_path)
        assert "PASSED" in result.format_report()

    def test_format_report_failed_contains_module(self, tmp_path):
        features = [_feat("F1", "integration: missing.thing.xyz")]
        result = verify_integration_targets(features, workspace=tmp_path)
        report = result.format_report()
        assert "FAILED" in report
        assert "missing.thing.xyz" in report


class TestInvalidInput:
    def test_none_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets("not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets({"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]

    def test_integer_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(42, workspace=tmp_path)  # type: ignore[arg-type]


class TestRejectOnFailure:
    def test_reject_on_failure_raises_for_unreachable(self, tmp_path):
        features = [_feat("F1", "integration: totally.missing.xyz.abc")]
        with pytest.raises(ValueError):
            verify_integration_targets(features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_error_contains_module_name(self, tmp_path):
        features = [_feat("F1", "integration: totally.missing.xyz.abc")]
        with pytest.raises(ValueError, match="totally.missing.xyz.abc"):
            verify_integration_targets(features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_passes_when_reachable(self, tmp_path):
        features = [_feat("F1", "integration: os")]
        result = verify_integration_targets(features, workspace=tmp_path, reject_on_failure=True)
        assert result.passed is True


def test_integration_target_reachability(tmp_path):
    """Integration-target reachability check at spec-load time.

    Verifies the canonical AC: validate_integration_targets in bob3.spec_loader
    correctly gates unreachable modules at plan time.
    """
    # Reachable via workspace file
    src = tmp_path / "src" / "myapp"
    src.mkdir(parents=True)
    (src / "utils.py").write_text("")
    reachable_features = [_feat("F1", "integration: myapp.utils")]
    result = validate_integration_targets(reachable_features, workspace=tmp_path)
    assert result.passed is True
    assert isinstance(result, ReachabilityResult)

    # Unreachable module is detected
    missing_features = [_feat("F2", "integration: totally.absent.module.xyz")]
    result = validate_integration_targets(missing_features, workspace=tmp_path)
    assert result.passed is False
    assert len(result.issues) == 1
    assert result.issues[0].missing_module == "totally.absent.module.xyz"

    # Sibling features in spec count as reachable
    sibling_features = [
        _feat("F3", "integration: myapp.new_mod"),
        _feat("F4", "integration: myapp.new_mod"),
    ]
    result = validate_integration_targets(sibling_features, workspace=tmp_path)
    assert result.passed is True

    # Invalid input raises ValueError
    with pytest.raises(ValueError):
        validate_integration_targets(None, workspace=tmp_path)  # type: ignore[arg-type]

    # reject_on_failure raises for unreachable target
    with pytest.raises(ValueError, match="totally.absent.module.xyz"):
        validate_integration_targets(
            [_feat("F5", "integration: totally.absent.module.xyz")],
            workspace=tmp_path,
            reject_on_failure=True,
        )


def test_integration_target_exists(tmp_path):
    """check_integration_reachability: module file in workspace → target is reachable."""
    src = tmp_path / "src" / "myapp"
    src.mkdir(parents=True)
    (src / "utils.py").write_text("")
    features = [{"name": "F1", "acceptance_criteria": ["integration: myapp.utils"]}]
    result = check_integration_reachability(features, workspace=tmp_path)
    assert isinstance(result, ReachabilityResult)
    assert result.passed is True


def test_integration_target_is_feature(tmp_path):
    """check_integration_reachability: target declared by sibling feature → reachable."""
    features = [
        {"name": "F1", "acceptance_criteria": ["integration: myapp.new_mod"]},
        {"name": "F2", "acceptance_criteria": ["integration: myapp.new_mod"]},
    ]
    result = check_integration_reachability(features, workspace=tmp_path)
    assert isinstance(result, ReachabilityResult)
    assert result.passed is True


def test_reject_unreachable_targets(tmp_path):
    """check_integration_reachability: unreachable module → result.passed is False."""
    features = [{"name": "F1", "acceptance_criteria": ["integration: totally.absent.module.xyz"]}]
    result = check_integration_reachability(features, workspace=tmp_path)
    assert isinstance(result, ReachabilityResult)
    assert result.passed is False
    assert any("totally.absent.module.xyz" in str(i.missing_module) for i in result.issues)
