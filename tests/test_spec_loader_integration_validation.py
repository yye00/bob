"""Tests for bob74.spec_loader.validate_integration_targets.

Verifies:
- Returns ReachabilityResult with .passed attribute.
- Empty feature list passes.
- Non-integration ACs are ignored.
- A module that exists as a source file in the workspace passes.
- A module declared as integration target in a sibling feature passes.
- An importable (stdlib) module passes.
- An unreachable module produces a failing result.
- Multiple ACs checked across multiple features.
- Invalid input (non-list) raises ValueError.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob74.spec_loader import validate_integration_targets, ReachabilityResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feat(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_reachability_result(self, tmp_path):
        result = validate_integration_targets([], workspace=tmp_path)
        assert isinstance(result, ReachabilityResult)

    def test_result_has_passed_attribute(self, tmp_path):
        result = validate_integration_targets([], workspace=tmp_path)
        assert hasattr(result, "passed")


# ---------------------------------------------------------------------------
# Empty / no-integration cases
# ---------------------------------------------------------------------------

class TestEmptyCases:
    def test_empty_list_passes(self, tmp_path):
        result = validate_integration_targets([], workspace=tmp_path)
        assert result.passed is True

    def test_non_integration_ac_ignored(self, tmp_path):
        features = [_feat("F1", "File exists: src/foo.py", "pytest: tests/test_foo.py")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_feature_with_no_acs_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": []}]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Workspace reachability
# ---------------------------------------------------------------------------

class TestWorkspaceReachability:
    def test_module_as_src_file_passes(self, tmp_path):
        p = tmp_path / "src" / "myapp" / "utils.py"
        p.parent.mkdir(parents=True)
        p.write_text("")
        features = [_feat("F1", "integration: myapp.utils")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_missing_module_fails(self, tmp_path):
        features = [_feat("F1", "integration: totally.absent.module")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) == 1
        assert result.issues[0].missing_module == "totally.absent.module"


# ---------------------------------------------------------------------------
# Sibling-feature spec reachability
# ---------------------------------------------------------------------------

class TestSiblingFeatureReachability:
    def test_sibling_integration_target_passes(self, tmp_path):
        features = [
            _feat("F1", "integration: myapp.new_mod"),
            _feat("F2", "integration: myapp.new_mod"),
        ]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Importable module
# ---------------------------------------------------------------------------

class TestImportableModule:
    def test_stdlib_module_passes(self, tmp_path):
        features = [_feat("F1", "integration: os")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True

    def test_pathlib_passes(self, tmp_path):
        features = [_feat("F1", "integration: pathlib")]
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Multiple features / ACs
# ---------------------------------------------------------------------------

class TestMultipleFeaturesAndACs:
    def test_multiple_features_one_missing(self, tmp_path):
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "pkg" / "good.py").write_text("")
        features = [
            _feat("F1", "integration: pkg.good"),
            _feat("F2", "integration: pkg.absent"),
        ]
        result = validate_integration_targets(features, workspace=tmp_path)
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
        result = validate_integration_targets(features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# format_report smoke test
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_format_report_passed(self, tmp_path):
        result = validate_integration_targets([], workspace=tmp_path)
        assert "PASSED" in result.format_report()

    def test_format_report_failed_contains_module(self, tmp_path):
        features = [_feat("F1", "integration: missing.thing")]
        result = validate_integration_targets(features, workspace=tmp_path)
        report = result.format_report()
        assert "FAILED" in report
        assert "missing.thing" in report


# ---------------------------------------------------------------------------
# ValueError on invalid input
# ---------------------------------------------------------------------------

class TestInvalidInput:
    def test_none_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets("not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets({"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]
