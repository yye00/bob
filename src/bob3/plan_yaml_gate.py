"""bob3.plan_yaml_gate — public facade for plan.yaml loading and approval checks.

Provides the canonical load_plan_yaml / validate_plan_approved API used by
implementer sub-agents to enforce the Devin-style editable plan.yaml gate
(F-259ea328).  The heavy lifting lives in bob3.orchestrator.plan_gate; this
module re-exports the right primitives under clean names so callers do not
need to know the internal package layout.

Usage::

    from bob3.plan_yaml_gate import load_plan_yaml, validate_plan_approved

    plan = load_plan_yaml("some-feature-id")
    validate_plan_approved("some-feature-id")   # raises if not approved
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.orchestrator.plan_gate import (
    ImplementerBlockedError,
    PlanArtifactMissingError,
    is_approved,
    load_plan,
)


__all__ = [
    "load_plan_yaml",
    "validate_plan_approved",
    "ImplementerBlockedError",
    "PlanArtifactMissingError",
]


def load_plan_yaml(
    feature_id: str,
    workspace: str | Path | None = None,
) -> dict[str, Any] | None:
    """Load specs/<feature_id>/plan.yaml and return its parsed contents.

    Returns None when the file does not exist or is empty/malformed, so callers
    can handle the missing-plan case explicitly rather than catching exceptions.

    Args:
        feature_id: UUID (or short slug) of the feature whose plan.yaml to load.
        workspace: Workspace root override.  Defaults to the current directory.

    Returns:
        Parsed dict from plan.yaml, or None if the file is absent/unreadable.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")
    return load_plan(feature_id, workspace)


def validate_plan_approved(
    feature_id: str,
    workspace: str | Path | None = None,
) -> None:
    """Assert that specs/<feature_id>/plan.yaml has approved=true.

    Implementer sub-agents must call this at startup to enforce the gate.

    Args:
        feature_id: UUID of the feature to check.
        workspace: Workspace root override.  Defaults to the current directory.

    Raises:
        ValueError: When feature_id is empty or None.
        ImplementerBlockedError: When plan.yaml is absent or approved=false.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")
    if not is_approved(feature_id, workspace):
        raise ImplementerBlockedError(
            f"Implementer blocked: plan.yaml not approved for feature {feature_id}. "
            "Set approved: true in specs/<feature>/plan.yaml before running the implementer."
        )
