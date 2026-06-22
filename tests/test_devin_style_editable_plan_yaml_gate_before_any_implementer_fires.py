"""Tests for devin_style_editable_plan_yaml_gate_before_any_implementer_fires.

Acceptance criteria:
  - File exists: src/bob3/devin_style_editable_plan_yaml_gate_before_any_implementer_fires.py
  - pytest: tests/test_devin_style_editable_plan_yaml_gate_before_any_implementer_fires.py::test_devin_style_editable_plan_yaml_gate_before_any_implementer_fires
  - Function defined: bob3.devin_style_editable_plan_yaml_gate_before_any_implementer_fires.devin_style_editable_plan_yaml_gate_before_any_implementer_fires
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bob3.devin_style_editable_plan_yaml_gate_before_any_implementer_fires import (
    devin_style_editable_plan_yaml_gate_before_any_implementer_fires,
)


def test_devin_style_editable_plan_yaml_gate_before_any_implementer_fires(tmp_path):
    """Primary acceptance-criteria test — covers all core behaviours."""
    feature_id = "45b6c7d8-1010-415b-aa39-1285542c80d3"
    name = "Devin-style editable plan.yaml gate before any implementer fires"
    description = (
        "After F-R7-450 spec-critic passes, write specs/<feature>/plan.yaml "
        "and emit a PLAN_READY event. Implementer sub-agents refuse to "
        "start unless plan.yaml.approved is true."
    )
    acceptance_criteria = [
        "File exists: src/bob3/devin_style_editable_plan_yaml_gate_before_any_implementer_fires.py",
        "pytest: tests/test_devin_style_editable_plan_yaml_gate_before_any_implementer_fires.py::test_devin_style_editable_plan_yaml_gate_before_any_implementer_fires",
        "Function defined: bob3.devin_style_editable_plan_yaml_gate_before_any_implementer_fires.devin_style_editable_plan_yaml_gate_before_any_implementer_fires",
    ]

    # --- 1. Unapproved plan: implementer_blocked=True ---
    result = devin_style_editable_plan_yaml_gate_before_any_implementer_fires(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=tmp_path,
    )

    assert isinstance(result, dict), "result must be a dict"
    assert "plan_path" in result, "result must have 'plan_path'"
    assert "approved" in result, "result must have 'approved'"
    assert "implementer_blocked" in result, "result must have 'implementer_blocked'"
    assert "plan_ready_emitted" in result, "result must have 'plan_ready_emitted'"

    plan_path = Path(result["plan_path"])
    assert plan_path.exists(), "plan.yaml must be written to disk"
    assert result["approved"] is False, "default plan must be unapproved"
    assert result["implementer_blocked"] is True, "implementer must be blocked when unapproved"
    assert result["plan_ready_emitted"] is True, "PLAN_READY event must be emitted"

    # --- 2. Verify plan.yaml content ---
    data = yaml.safe_load(plan_path.read_text())
    assert data["feature_id"] == feature_id
    assert data["name"] == name
    assert data["acceptance_criteria"] == acceptance_criteria
    assert data["approved"] is False
    assert "spec_hash" in data
    assert "written_at" in data

    # --- 3. Auto-approve path: implementer_blocked=False ---
    result_approved = devin_style_editable_plan_yaml_gate_before_any_implementer_fires(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=tmp_path,
        auto_approve=True,
    )

    assert result_approved["approved"] is True, "auto_approve must set approved=True"
    assert result_approved["implementer_blocked"] is False, "approved plan must unblock implementer"

    # --- 4. Drift detection: spec change resets approval ---
    changed_ac = acceptance_criteria + ["Extra AC — spec changed"]
    result_drift = devin_style_editable_plan_yaml_gate_before_any_implementer_fires(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=changed_ac,
        workspace=tmp_path,
    )

    assert result_drift["approved"] is False, "spec change must reset approval to False"
    assert result_drift["implementer_blocked"] is True, "implementer must be re-blocked after drift"
    assert result_drift.get("drift_detected") is True, "drift_detected must be True when AC changed"

    # --- 5. Idempotent: same spec preserves approval ---
    # Re-approve first
    devin_style_editable_plan_yaml_gate_before_any_implementer_fires(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=changed_ac,
        workspace=tmp_path,
        auto_approve=True,
    )
    # Same spec re-run must preserve approval
    result_stable = devin_style_editable_plan_yaml_gate_before_any_implementer_fires(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=changed_ac,
        workspace=tmp_path,
    )
    assert result_stable["approved"] is True, "idempotent re-run must preserve approval when spec unchanged"
    assert result_stable["implementer_blocked"] is False, "preserved approval must unblock implementer"
    assert result_stable.get("drift_detected") is False, "no drift when spec unchanged"
