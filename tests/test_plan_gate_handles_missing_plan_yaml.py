"""Tests: handle_missing_plan_yaml raises PlanArtifactMissingError when absent (F-9792cc6f).

Acceptance criterion:
    pytest: tests/test_plan_gate_handles_missing_plan_yaml.py asserts
    handle_missing_plan_yaml raises PlanArtifactMissingError with message
    containing "plan.yaml" when absent (error path)
"""

from __future__ import annotations

import pytest


class TestHandleMissingPlanYaml:
    """handle_missing_plan_yaml raises PlanArtifactMissingError when plan.yaml absent."""

    def test_raises_when_plan_yaml_absent(self, tmp_path):
        from bob3.orchestrator.plan_gate import handle_missing_plan_yaml, PlanArtifactMissingError

        feature_id = "aaaa2001-missing-plan-test000000001"

        with pytest.raises(PlanArtifactMissingError) as exc_info:
            handle_missing_plan_yaml(feature_id, workspace=tmp_path)

        assert "plan.yaml" in str(exc_info.value), (
            "PlanArtifactMissingError message must contain 'plan.yaml'"
        )

    def test_error_message_contains_plan_yaml_string(self, tmp_path):
        from bob3.orchestrator.plan_gate import handle_missing_plan_yaml, PlanArtifactMissingError

        feature_id = "bbbb2002-missing-plan-test000000002"

        try:
            handle_missing_plan_yaml(feature_id, workspace=tmp_path)
            pytest.fail("Expected PlanArtifactMissingError was not raised")
        except PlanArtifactMissingError as exc:
            assert "plan.yaml" in str(exc), (
                f"Exception message '{exc}' must contain 'plan.yaml'"
            )

    def test_no_raise_when_plan_yaml_exists(self, tmp_path):
        from bob3.orchestrator.plan_gate import (
            handle_missing_plan_yaml,
            write_plan_artifact,
            PlanArtifactMissingError,
        )

        feature_id = "cccc2003-missing-plan-test000000003"
        write_plan_artifact(
            feature_id=feature_id,
            name="Existing Feature",
            description=None,
            acceptance_criteria=["AC one"],
            workspace=tmp_path,
        )

        # Must not raise
        handle_missing_plan_yaml(feature_id, workspace=tmp_path)

    def test_plan_artifact_missing_error_is_file_not_found_error(self, tmp_path):
        from bob3.orchestrator.plan_gate import PlanArtifactMissingError

        assert issubclass(PlanArtifactMissingError, FileNotFoundError), (
            "PlanArtifactMissingError must be a subclass of FileNotFoundError"
        )

    def test_error_is_specific_exception_type(self, tmp_path):
        from bob3.orchestrator.plan_gate import handle_missing_plan_yaml, PlanArtifactMissingError

        feature_id = "dddd2004-missing-plan-test000000004"

        with pytest.raises(PlanArtifactMissingError):
            handle_missing_plan_yaml(feature_id, workspace=tmp_path)

    def test_raises_only_when_actually_missing(self, tmp_path):
        """Does NOT raise for a different feature_id whose plan exists."""
        from bob3.orchestrator.plan_gate import (
            handle_missing_plan_yaml,
            write_plan_artifact,
            PlanArtifactMissingError,
        )

        present_id = "eeee2005-missing-plan-test000000005"
        absent_id = "ffff2006-missing-plan-test000000006"

        write_plan_artifact(
            feature_id=present_id,
            name="Present Feature",
            description=None,
            acceptance_criteria=["AC"],
            workspace=tmp_path,
        )

        # present_id should not raise
        handle_missing_plan_yaml(present_id, workspace=tmp_path)

        # absent_id should raise
        with pytest.raises(PlanArtifactMissingError):
            handle_missing_plan_yaml(absent_id, workspace=tmp_path)
