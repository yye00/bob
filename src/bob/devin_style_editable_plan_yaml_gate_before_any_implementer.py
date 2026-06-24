"""Devin-style editable plan.yaml gate before any implementer fires.

After F-R7-450 spec-critic passes, write specs/<feature>/plan.yaml and emit a
PLAN_READY event. Implementer sub-agents refuse to start unless
plan.yaml.approved is true. Edits to plan.yaml re-trigger F-R7-450 critic
incrementally via F-R7-451 provenance.

Public API::

    from bob.devin_style_editable_plan_yaml_gate_before_any_implementer import (
        devin_style_editable_plan_yaml_gate_before_any_implementer,
    )

    result = devin_style_editable_plan_yaml_gate_before_any_implementer(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py"],
    )
    if result["implementer_blocked"]:
        raise RuntimeError("Set approved: true in plan.yaml before running the implementer")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.orchestrator.plan_gate import (
    compute_plan_vs_spec_drift,
    is_approved,
    write_plan_artifact,
)


def devin_style_editable_plan_yaml_gate_before_any_implementer(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    workspace: Path | None = None,
    *,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Write plan.yaml, emit PLAN_READY, and gate the implementer on approval.

    After the spec-critic passes (F-R7-450), this function:
      1. Detects whether the spec has drifted from any prior plan.yaml.
      2. Writes (or re-writes) specs/<feature_id>/plan.yaml with approval state
         preserved when the spec is unchanged, or reset to False when it drifts.
      3. Emits a PLAN_READY structured event to runs/events.jsonl.
      4. Returns whether the implementer is blocked (approved=False → blocked).

    Edits to plan.yaml that change acceptance_criteria trigger incremental
    re-evaluation of the spec-critic (F-R7-451 provenance).

    Parameters
    ----------
    feature_id:
        UUID of the feature.
    name:
        Human-readable feature name.
    description:
        Feature description text.
    acceptance_criteria:
        List of AC strings for this feature.
    workspace:
        Override for the workspace root (defaults to CWD).
    auto_approve:
        When True, writes approved=true unconditionally. For CI / --auto-approve paths.

    Returns
    -------
    dict with keys:
        plan_path: str — absolute path to the written plan.yaml
        approved: bool — value of approved in the written plan.yaml
        implementer_blocked: bool — True when the implementer must not start
        plan_ready_emitted: bool — always True (PLAN_READY event was emitted)
        drift_detected: bool — True when AC changed since last plan.yaml write
    """
    drift_report = compute_plan_vs_spec_drift(feature_id, acceptance_criteria, workspace)
    drift_detected = drift_report["drift"]

    plan_path = write_plan_artifact(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
        auto_approve=auto_approve,
    )

    approved = is_approved(feature_id, workspace)

    return {
        "plan_path": str(plan_path),
        "approved": approved,
        "implementer_blocked": not approved,
        "plan_ready_emitted": True,
        "drift_detected": drift_detected,
    }
