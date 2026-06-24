"""bob3.gates — Gate functions for feature lifecycle enforcement.

Public API:
    :func:`is_completion_persisted`   — check if a feature has a persisted completion stamp
    :func:`prevent_status_downgrade`  — block demotion of previously-completed features
    :func:`plan_yaml_gate`            — Devin-style plan.yaml approval gate for implementers
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.sticky_completed_gate import is_completion_persisted, prevent_status_downgrade


def plan_yaml_gate(
    feature_id: str,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    """Devin-style plan.yaml gate — check and enforce approval before implementers fire.

    Returns the loaded plan dict when approved, raises ImplementerBlockedError when not.

    This is the canonical gate entry-point for the plan.yaml approval workflow:
    1. Load specs/<feature_id>/plan.yaml
    2. If approved=true, return the plan dict (implementer may proceed)
    3. If absent or approved=false, raise ImplementerBlockedError

    Args:
        feature_id: UUID of the feature to check.
        workspace: Workspace root override. Defaults to CWD.

    Returns:
        The plan dict from plan.yaml when the gate passes.

    Raises:
        ValueError: When feature_id is empty or None.
        ImplementerBlockedError: When plan.yaml is absent or approved=false.
    """
    from bob3.orchestrator.plan_gate import (
        ImplementerBlockedError,
        load_plan,
        refuse_implementer_when_unapproved,
    )

    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")

    refuse_implementer_when_unapproved(feature_id, workspace)
    plan = load_plan(feature_id, workspace) or {}
    return plan


__all__ = [
    "is_completion_persisted",
    "prevent_status_downgrade",
    "plan_yaml_gate",
]
