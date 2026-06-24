"""bob.plan_editor — Handle edits to plan.yaml and re-trigger spec critic.

When a user edits specs/<feature>/plan.yaml after the spec-critic has passed,
this module detects the change and incrementally re-triggers F-R7-450 critic
via F-R7-451 provenance tracking.

Public API::

    from bob.plan_editor import handle_plan_edits

    result = handle_plan_edits(
        feature_id="abc123",
        name="My feature",
        description="...",
        new_acceptance_criteria=["File exists: src/foo.py"],
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.orchestrator.plan_gate import (
    compute_plan_vs_spec_drift,
    retrigger_critic_on_edit,
    write_plan_artifact,
    is_approved,
)


def handle_plan_edits(
    feature_id: str,
    name: str,
    description: str | None,
    new_acceptance_criteria: list[str],
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Handle edits to plan.yaml by detecting drift and re-triggering the spec critic.

    When acceptance_criteria in plan.yaml change, the spec-critic (F-R7-450) is
    re-triggered incrementally via F-R7-451 provenance to re-gate the feature.
    The plan's ``approved`` flag is reset to False when drift is detected, forcing
    human re-approval before the implementer can fire.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml has been edited.
    name:
        Human-readable feature name.
    description:
        Feature description text.
    new_acceptance_criteria:
        The updated list of AC strings from the edited plan.yaml.
    workspace:
        Override for the workspace root (defaults to CWD).

    Returns
    -------
    dict with keys:
        drift_detected: bool — True when ACs changed from prior plan.yaml
        critic_defects: list — defects found by re-triggered spec critic
        plan_path: str — path to the re-written plan.yaml
        approved: bool — approval state after handling edits (False when drift)
        implementer_blocked: bool — True when implementer cannot start
        added: list[str] — ACs added since prior plan.yaml
        removed: list[str] — ACs removed since prior plan.yaml

    Raises
    ------
    ValueError
        When ``feature_id`` is empty or None, ``name`` is empty or None, or
        ``new_acceptance_criteria`` is not a list.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")
    if not name or not isinstance(name, str):
        raise ValueError("name must be a non-empty string")
    if not isinstance(new_acceptance_criteria, list):
        raise ValueError(
            f"new_acceptance_criteria must be a list, got {type(new_acceptance_criteria).__name__}"
        )

    drift_report = compute_plan_vs_spec_drift(feature_id, new_acceptance_criteria, workspace)
    drift_detected = drift_report["drift"]

    critic_defects: list[Any] = []

    if drift_detected:
        # Re-trigger spec critic incrementally (F-R7-451 provenance)
        try:
            critic_defects = retrigger_critic_on_edit(
                feature_id=feature_id,
                name=name,
                description=description,
                acceptance_criteria=new_acceptance_criteria,
                workspace=workspace,
            )
        except Exception:
            # Critic re-trigger failure is non-fatal; gate on drift alone.
            critic_defects = []

    # Rewrite plan.yaml with auto_approve=False to force re-approval on drift.
    # When no drift, approval state is preserved by write_plan_artifact.
    plan_path = write_plan_artifact(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=new_acceptance_criteria,
        workspace=workspace,
        auto_approve=False,
    )

    approved = is_approved(feature_id, workspace)

    return {
        "drift_detected": drift_detected,
        "critic_defects": critic_defects,
        "plan_path": str(plan_path),
        "approved": approved,
        "implementer_blocked": not approved,
        "added": drift_report.get("added", []),
        "removed": drift_report.get("removed", []),
    }
