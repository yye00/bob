"""Tests for hippy.spec.reachability — integration-target reachability at spec-load time.

Covers:
- check_integration_reachability across a whole spec (list of feature dicts)
- resolve_target_module classifying a single dotted module target
- boundary cases (empty / minimal input return a well-defined result)
- error path (invalid input raises ValueError)
"""

from __future__ import annotations

import pytest

from hippy.spec.reachability import (
    check_integration_reachability,
    resolve_target_module,
)


class TestCheckIntegrationReachability:
    def test_empty_features_passes(self, tmp_path):
        result = check_integration_reachability(features=[], workspace=tmp_path)
        assert result.passed is True
        assert result.issues == []

    def test_no_integration_acs_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["File exists: src/f1.py"]}]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_target_fails(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: totally.missing.zzz.module"]}
        ]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        assert result.passed is False
        assert result.issues
        assert result.issues[0].missing_module == "totally.missing.zzz.module"

    def test_target_reachable_via_workspace_file(self, tmp_path):
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "mod.py").write_text("x = 1\n")
        features = [{"name": "F1", "acceptance_criteria": ["integration: pkg.mod"]}]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_target_reachable_via_sibling_feature(self, tmp_path):
        features = [
            {"name": "consumer", "acceptance_criteria": ["integration: pkg.newmod"]},
            {"name": "producer", "acceptance_criteria": ["integration: pkg.newmod"]},
        ]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_target_reachable_via_importable_module(self, tmp_path):
        # Standard-library module is importable → reachable.
        features = [{"name": "F1", "acceptance_criteria": ["integration: json"]}]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reject_on_failure_raises_for_unreachable(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: totally.missing.zzz.module"]}
        ]
        with pytest.raises(ValueError, match="totally.missing.zzz.module"):
            check_integration_reachability(
                features=features, workspace=tmp_path, reject_on_failure=True
            )

    def test_reject_on_failure_does_not_raise_when_reachable(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: json"]}]
        result = check_integration_reachability(
            features=features, workspace=tmp_path, reject_on_failure=True
        )
        assert result.passed is True

    def test_format_report_names_missing_module(self, tmp_path):
        features = [
            {"name": "F1", "acceptance_criteria": ["integration: totally.missing.zzz.module"]}
        ]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        report = result.format_report()
        assert "totally.missing.zzz.module" in report


class TestResolveTargetModule:
    def test_workspace_file_resolves_in_workspace(self, tmp_path):
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "mod.py").write_text("x = 1\n")
        assert resolve_target_module("pkg.mod", workspace=tmp_path) == "in_workspace"

    def test_importable_module_resolves_in_workspace(self, tmp_path):
        assert resolve_target_module("json", workspace=tmp_path) == "in_workspace"

    def test_sibling_spec_module_resolves_in_spec(self, tmp_path):
        features = [
            {"name": "producer", "acceptance_criteria": ["integration: pkg.newmod"]},
        ]
        assert (
            resolve_target_module("pkg.newmod", features=features, workspace=tmp_path)
            == "in_spec"
        )

    def test_missing_module_resolves_unreachable(self, tmp_path):
        assert (
            resolve_target_module("totally.missing.zzz.module", workspace=tmp_path)
            == "unreachable"
        )

    def test_empty_module_resolves_unreachable(self, tmp_path):
        assert resolve_target_module("", workspace=tmp_path) == "unreachable"


class TestBoundary:
    def test_no_args_returns_result(self):
        result = check_integration_reachability()
        assert result.passed is True

    def test_none_ac_does_not_raise(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": None}]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_missing_ac_key_does_not_raise(self, tmp_path):
        features = [{"name": "F1"}]
        result = check_integration_reachability(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_whitespace_module_resolves_unreachable(self, tmp_path):
        assert resolve_target_module("   ", workspace=tmp_path) == "unreachable"


class TestErrorPath:
    def test_none_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_integration_reachability(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_integration_reachability(features="nope", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_integration_reachability(features={"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]

    def test_int_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            check_integration_reachability(features=7, workspace=tmp_path)  # type: ignore[arg-type]
