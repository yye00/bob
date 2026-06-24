"""Tests for bob77.integration_target.validate_integration_targets.

Verifies:
- Non-integration ACs are ignored.
- A module that exists as a source file in the workspace passes.
- A module declared as an integration target in a sibling feature passes.
- An importable module passes.
- An unreachable module produces a failed result.
- reject_on_failure=True raises ValueError for unreachable targets.
- passed=True when all targets are reachable.
- passed=False when any target is unreachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from bob77.integration_target import validate_integration_targets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


# ---------------------------------------------------------------------------
# Basic structure tests
# ---------------------------------------------------------------------------

class TestValidateIntegrationTargets:
    def test_empty_features_returns_passed(self, tmp_path):
        result = validate_integration_targets(features=[], workspace=tmp_path)
        assert result is not None
        assert result.passed is True

    def test_no_integration_acs_passes(self, tmp_path):
        features = [_make_feature("F1", "File exists: src/foo.py", "pytest: tests/test_foo.py")]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_file_exists_in_workspace(self, tmp_path):
        src = tmp_path / "src" / "mymodule.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        features = [_make_feature("F1", "integration: mymodule")]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_importable(self, tmp_path):
        features = [_make_feature("F1", "integration: os")]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_declared_in_sibling_feature(self, tmp_path):
        features = [
            _make_feature("F1", "integration: future.module"),
            _make_feature("F2", "integration: future.module"),
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_returns_failed(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False

    def test_unreachable_populates_issues(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert len(result.issues) > 0

    def test_reject_on_failure_raises_value_error(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        with pytest.raises(ValueError):
            validate_integration_targets(
                features=features,
                workspace=tmp_path,
                reject_on_failure=True,
            )

    def test_reject_on_failure_error_message_contains_module_name(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.nonexistent.xyz.module")]
        with pytest.raises(ValueError, match="totally.nonexistent.xyz.module"):
            validate_integration_targets(
                features=features,
                workspace=tmp_path,
                reject_on_failure=True,
            )

    def test_all_reachable_passed_true(self, tmp_path):
        features = [_make_feature("F1", "integration: os"), _make_feature("F2", "integration: sys")]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_mixed_reachable_unreachable_passed_false(self, tmp_path):
        features = [
            _make_feature("F1", "integration: os"),
            _make_feature("F2", "integration: totally.nonexistent.xyz.module"),
        ]
        result = validate_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False

    def test_result_has_format_report(self, tmp_path):
        result = validate_integration_targets(features=[], workspace=tmp_path)
        assert hasattr(result, "format_report")
        assert callable(result.format_report)

    def test_no_workspace_defaults_to_cwd(self):
        result = validate_integration_targets(features=[])
        assert result is not None

    def test_none_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features="not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            validate_integration_targets(features={"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]
