"""Tests: is_approved({}) returns False when plan.yaml has zero keys (F-9792cc6f).

Acceptance criterion:
    pytest: tests/test_plan_gate_boundary_empty_plan.py asserts is_approved({})
    returns False when plan.yaml has zero keys (empty/zero boundary)
"""

from __future__ import annotations

import pytest
import yaml


class TestBoundaryEmptyPlan:
    """is_approved returns False when plan.yaml has zero keys."""

    def test_is_approved_returns_false_for_empty_plan_yaml(self, tmp_path):
        """Write an empty plan.yaml (zero keys) — is_approved must return False."""
        from bob3.orchestrator.plan_gate import is_approved

        feature_id = "aaaa3001-boundary-empty-plan00000001"
        plan_dir = tmp_path / "specs" / feature_id
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.yaml").write_text("{}\n")  # zero keys

        result = is_approved(feature_id, workspace=tmp_path)
        assert result is False, (
            "is_approved must return False when plan.yaml has zero keys (empty dict)"
        )

    def test_is_approved_returns_false_for_null_plan_yaml(self, tmp_path):
        """Write a plan.yaml with null content — is_approved must return False."""
        from bob3.orchestrator.plan_gate import is_approved

        feature_id = "bbbb3002-boundary-empty-plan00000002"
        plan_dir = tmp_path / "specs" / feature_id
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.yaml").write_text("null\n")

        result = is_approved(feature_id, workspace=tmp_path)
        assert result is False

    def test_is_approved_returns_false_for_empty_file(self, tmp_path):
        """Write a plan.yaml with empty content — is_approved must return False."""
        from bob3.orchestrator.plan_gate import is_approved

        feature_id = "cccc3003-boundary-empty-plan00000003"
        plan_dir = tmp_path / "specs" / feature_id
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.yaml").write_text("")

        result = is_approved(feature_id, workspace=tmp_path)
        assert result is False

    def test_is_approved_returns_false_when_approved_key_missing(self, tmp_path):
        """plan.yaml with other keys but no 'approved' key — is_approved must return False."""
        from bob3.orchestrator.plan_gate import is_approved

        feature_id = "dddd3004-boundary-empty-plan00000004"
        plan_dir = tmp_path / "specs" / feature_id
        plan_dir.mkdir(parents=True)
        data = {"feature_id": feature_id, "name": "Test"}
        (plan_dir / "plan.yaml").write_text(yaml.dump(data))

        result = is_approved(feature_id, workspace=tmp_path)
        assert result is False, (
            "is_approved must return False when 'approved' key is absent"
        )

    def test_is_approved_returns_false_when_approved_is_none(self, tmp_path):
        """plan.yaml with approved: null — is_approved must return False."""
        from bob3.orchestrator.plan_gate import is_approved

        feature_id = "eeee3005-boundary-empty-plan00000005"
        plan_dir = tmp_path / "specs" / feature_id
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.yaml").write_text("approved: null\n")

        result = is_approved(feature_id, workspace=tmp_path)
        assert result is False

    def test_is_approved_returns_true_only_when_explicitly_true(self, tmp_path):
        """Confirm positive case: approved: true returns True."""
        from bob3.orchestrator.plan_gate import is_approved

        feature_id = "ffff3006-boundary-empty-plan00000006"
        plan_dir = tmp_path / "specs" / feature_id
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.yaml").write_text("approved: true\n")

        result = is_approved(feature_id, workspace=tmp_path)
        assert result is True
