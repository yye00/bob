"""Tests for bob.integration_target_verifier.

Verifies:
- verify_integration_targets: handles empty features, non-integration ACs,
  reachable and unreachable modules, reject_on_failure, invalid input.
- is_target_reachable: returns bool for existing/missing modules, empty strings,
  sibling spec features.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.integration_target_verifier import is_target_reachable, verify_integration_targets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feature(name: str, *acs: str) -> dict:
    return {"name": name, "acceptance_criteria": list(acs)}


# ---------------------------------------------------------------------------
# verify_integration_targets
# ---------------------------------------------------------------------------

class TestVerifyIntegrationTargets:
    def test_empty_features_passes(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert result.passed is True

    def test_no_args_passes(self):
        result = verify_integration_targets()
        assert result is not None
        assert result.passed is True

    def test_non_integration_acs_are_ignored(self, tmp_path):
        features = [_make_feature("F1", "File exists: src/foo.py", "pytest: tests/test_foo.py")]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_source_file_exists(self, tmp_path):
        (tmp_path / "src" / "mymod").mkdir(parents=True)
        (tmp_path / "src" / "mymod" / "__init__.py").write_text("")
        features = [_make_feature("F1", "integration: mymod")]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_reachable_when_sibling_feature_declares_module(self, tmp_path):
        features = [
            _make_feature("F1", "integration: future.module"),
            _make_feature("F2", "integration: future.module", "File exists: src/future/module.py"),
        ]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_unreachable_module_fails(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.missing.xyz.abc")]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is False
        assert len(result.issues) >= 1

    def test_unreachable_module_issue_has_correct_feature_name(self, tmp_path):
        features = [_make_feature("MyFeature", "integration: totally.missing.xyz.abc")]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert any(issue.feature_name == "MyFeature" for issue in result.issues)

    def test_reject_on_failure_raises_for_unreachable(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.missing.xyz.abc")]
        with pytest.raises(ValueError):
            verify_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_error_message_contains_module_name(self, tmp_path):
        features = [_make_feature("F1", "integration: totally.missing.xyz.abc")]
        with pytest.raises(ValueError, match="totally.missing.xyz.abc"):
            verify_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_does_not_raise_when_all_pass(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path, reject_on_failure=True)
        assert result.passed is True

    def test_none_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features="not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_features_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features={"key": "val"}, workspace=tmp_path)  # type: ignore[arg-type]

    def test_result_has_passed_attribute(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert hasattr(result, "passed")
        assert isinstance(result.passed, bool)

    def test_result_has_issues_attribute(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_format_report_returns_string(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        report = result.format_report()
        assert isinstance(report, str)

    def test_importable_module_passes(self, tmp_path):
        # os is always importable
        features = [_make_feature("F1", "integration: os")]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True


# ---------------------------------------------------------------------------
# is_target_reachable
# ---------------------------------------------------------------------------

class TestIsTargetReachable:
    def test_empty_string_returns_false(self, tmp_path):
        assert is_target_reachable("", workspace=tmp_path) is False

    def test_whitespace_string_returns_false(self, tmp_path):
        assert is_target_reachable("   ", workspace=tmp_path) is False

    def test_missing_module_returns_false(self, tmp_path):
        assert is_target_reachable("totally.missing.xyz.abc", workspace=tmp_path) is False

    def test_importable_module_returns_true(self, tmp_path):
        assert is_target_reachable("os", workspace=tmp_path) is True

    def test_importable_stdlib_module_returns_true(self, tmp_path):
        assert is_target_reachable("pathlib", workspace=tmp_path) is True

    def test_existing_source_file_returns_true(self, tmp_path):
        src = tmp_path / "src" / "mymod.py"
        src.parent.mkdir(parents=True)
        src.write_text("")
        assert is_target_reachable("mymod", workspace=tmp_path) is True

    def test_sibling_feature_makes_module_reachable(self, tmp_path):
        features = [
            _make_feature("Sibling", "integration: future.newmod"),
        ]
        assert is_target_reachable("future.newmod", features=features, workspace=tmp_path) is True

    def test_no_features_arg_works(self, tmp_path):
        result = is_target_reachable("os")
        assert result is True

    def test_returns_bool_type(self, tmp_path):
        result = is_target_reachable("os", workspace=tmp_path)
        assert isinstance(result, bool)

    def test_returns_false_bool_not_none(self, tmp_path):
        result = is_target_reachable("totally.missing.xyz.abc", workspace=tmp_path)
        assert result is False
