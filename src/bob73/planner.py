"""bob73.planner — plan-ready event emission for the Devin-style plan.yaml gate.

After the spec-critic passes (F-R7-450), write specs/<feature>/plan.yaml and
emit a PLAN_READY event so implementer sub-agents know a plan is available.

Public API::

    from bob73.planner import emit_plan_ready

    result = emit_plan_ready(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py"],
    )
    # result["plan_path"] — path to written plan.yaml
    # result["approved"]  — bool
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.orchestrator.plan_gate import (
    compute_plan_vs_spec_drift,
    is_approved,
    write_plan_artifact,
)


def emit_plan_ready(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    workspace: Path | str | None = None,
    *,
    auto_approve: bool = False,
) -> dict[str, Any]:
    """Write specs/<feature>/plan.yaml, emit PLAN_READY event, and return status.

    Called after the spec-critic passes to create or refresh the editable plan
    artifact. Implementer sub-agents consult ``is_approved`` (or
    ``check_plan_approved``) before starting work.

    Parameters
    ----------
    feature_id:
        UUID of the feature.
    name:
        Human-readable feature name.
    description:
        Feature description text. ``None`` is stored as an empty string.
    acceptance_criteria:
        List of AC strings for this feature.
    workspace:
        Override for the workspace root (defaults to CWD).
    auto_approve:
        When True, writes ``approved: true`` unconditionally (CI / --auto-approve).

    Returns
    -------
    dict with keys:
        plan_path: str — absolute path to the written plan.yaml
        approved: bool — value of approved in the written plan.yaml
        implementer_blocked: bool — True when the implementer must not start
        plan_ready_emitted: bool — always True
        drift_detected: bool — True when AC changed since last plan.yaml write

    Raises
    ------
    ValueError
        When ``feature_id`` is empty/None, ``name`` is empty/None, or
        ``acceptance_criteria`` is not a list.
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
