"""Error path tests for bob.integration_target_verifier.verify_integration_targets.

Invalid input raises ValueError and the function does not silently succeed:
- None features → ValueError
- Non-list scalar → ValueError
- Features dict (not list) → ValueError
"""

from __future__ import annotations

import pytest

from bob.integration_target_verifier import verify_integration_targets


class TestErrorPaths:
    def test_none_input_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features=None, workspace=tmp_path)  # type: ignore[arg-type]

    def test_string_input_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features="not_a_list", workspace=tmp_path)  # type: ignore[arg-type]

    def test_integer_input_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features=42, workspace=tmp_path)  # type: ignore[arg-type]

    def test_dict_input_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            verify_integration_targets(features={"name": "F1"}, workspace=tmp_path)  # type: ignore[arg-type]

    def test_raises_value_error_not_silently_succeeds_on_none(self, tmp_path):
        raised = False
        try:
            verify_integration_targets(features=None, workspace=tmp_path)  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, "Expected ValueError but the function did not raise"

    def test_raises_value_error_not_silently_succeeds_on_string(self, tmp_path):
        raised = False
        try:
            verify_integration_targets(features="bad input", workspace=tmp_path)  # type: ignore[arg-type]
        except ValueError:
            raised = True
        assert raised, "Expected ValueError but the function did not raise"

    def test_reject_on_failure_raises_value_error_for_unreachable(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.missing.xyz.module"]}]
        with pytest.raises(ValueError):
            verify_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)

    def test_reject_on_failure_error_message_contains_module_name(self, tmp_path):
        features = [{"name": "F1", "acceptance_criteria": ["integration: totally.missing.xyz.module"]}]
        with pytest.raises(ValueError, match="totally.missing.xyz.module"):
            verify_integration_targets(features=features, workspace=tmp_path, reject_on_failure=True)
