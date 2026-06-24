"""bob75.plan_manager — plan.yaml management for Devin-style editable plan gate.

Wraps the canonical bob.orchestrator.plan_gate to provide a bob75-scoped
public API for emitting PLAN_READY events after spec-critic passes.

Public API::

    from bob75.plan_manager import emit_plan_ready

    emit_plan_ready(
        feature_id="abc123",
        plan_path="specs/abc123/plan.yaml",
        approved=False,
    )
"""

from __future__ import annotations

from pathlib import Path

from bob.orchestrator.plan_gate import emit_plan_ready_event, write_plan_artifact


def emit_plan_ready(
    feature_id: str,
    plan_path: str | Path,
    approved: bool,
    workspace: Path | str | None = None,
) -> None:
    """Emit a PLAN_READY event to runs/events.jsonl.

    Called after F-R7-450 spec-critic passes to signal that a plan.yaml has
    been written and is awaiting human approval before any implementer fires.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan is ready.
    plan_path:
        Path to the plan.yaml artifact (string or Path).
    approved:
        Whether the plan has been pre-approved (e.g. via --auto-approve).
    workspace:
        Override for the workspace root; defaults to CWD.

    Raises
    ------
    ValueError
        When feature_id is empty or None.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")
    emit_plan_ready_event(
        feature_id=feature_id,
        plan_path=str(plan_path),
        approved=approved,
        workspace=workspace,
    )


def write_and_emit_plan(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    workspace: Path | str | None = None,
    *,
    auto_approve: bool = False,
) -> Path:
    """Write specs/<feature_id>/plan.yaml and emit a PLAN_READY event.

    Convenience wrapper that combines write_plan_artifact + emit_plan_ready
    into a single call for use immediately after spec-critic passes.

    Parameters
    ----------
    feature_id:
        UUID of the feature.
    name:
        Human-readable feature name.
    description:
        Feature description text (may be None).
    acceptance_criteria:
        List of AC strings.
    workspace:
        Override for workspace root; defaults to CWD.
    auto_approve:
        When True, writes approved=true (for CI / --auto-approve paths).

    Returns
    -------
    Path
        Absolute path to the written plan.yaml.

    Raises
    ------
    ValueError
        When feature_id is empty/None, name is empty/None, or
        acceptance_criteria is not a list.
    """
    plan_path = write_plan_artifact(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
        auto_approve=auto_approve,
    )
    emit_plan_ready(
        feature_id=feature_id,
        plan_path=plan_path,
        approved=auto_approve,
        workspace=workspace,
    )
    return plan_path


__all__ = ["emit_plan_ready", "write_and_emit_plan"]
