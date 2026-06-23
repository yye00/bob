"""Boundary tests for bob3.integration_target_verifier.verify_integration_targets.

Every boundary case returns a well-defined result rather than raising:
- Empty list of features
- Feature with empty acceptance_criteria list
- Feature with empty-string AC
- Feature with None acceptance_criteria
- Single integration AC that is an empty string module target
"""

from __future__ import annotations

import pytest

from bob3.integration_target_verifier import verify_integration_targets


class TestBoundaryCases:
    def test_empty_features_list_returns_result(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert result is not None
        assert result.passed is True

    def test_feature_with_empty_ac_list_does_not_raise(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": []}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_feature_with_none_ac_does_not_raise(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": None}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_feature_missing_ac_key_does_not_raise(self, tmp_path):
        features = [{"name": "F1"}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_feature_with_empty_string_ac_does_not_raise(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": [""]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_single_non_integration_ac_does_not_raise(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["pytest: tests/test_foo.py"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_feature_with_empty_name_does_not_raise(self, tmp_path):
        features = [{"name": "", "acceptance_criteria": ["integration: missing.module"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result is not None

    def test_no_workspace_arg_does_not_raise(self):
        result = verify_integration_targets(features=[])
        assert result is not None

    def test_no_args_at_all_does_not_raise(self):
        result = verify_integration_targets()
        assert result is not None
        assert result.passed is True

    def test_single_feature_no_integration_acs_passes(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["File exists: src/f1.py"]}]
        result = verify_integration_targets(features=features, workspace=tmp_path)
        assert result.passed is True

    def test_result_has_passed_attribute(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert hasattr(result, "passed")
        assert isinstance(result.passed, bool)

    def test_result_has_issues_attribute(self, tmp_path):
        result = verify_integration_targets(features=[], workspace=tmp_path)
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)
