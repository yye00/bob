"""Devin-style editable plan.yaml gate before any implementer fires.

After F-R7-450 spec-critic passes, write specs/<feature>/plan.yaml and emit a
PLAN_READY event. Implementer sub-agents refuse to start unless
plan.yaml.approved is true. Edits to plan.yaml re-trigger F-R7-450 critic
incrementally via F-R7-451 provenance.

Public API::

    from bob.editable_plan_gate import enforce_plan_approval_gate, write_plan_yaml

    path = write_plan_yaml(
        feature_id="abc123",
        name="My feature",
        description="...",
        acceptance_criteria=["File exists: src/foo.py"],
    )

    enforce_plan_approval_gate(feature_id="abc123")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.orchestrator.plan_gate import (
    ImplementerBlockedError,
    PlanArtifactMissingError,
    approve_plan,
    compute_plan_vs_spec_drift,
    diff_plan_vs_spec,
    emit_plan_ready_event,
    is_approved,
    load_plan,
    refuse_implementer_when_unapproved,
    retrigger_critic_on_edit,
    write_plan_artifact,
)

__all__ = [
    "enforce_plan_approval_gate",
    "write_plan_yaml",
    "validate_plan_yaml",
    "check_plan_approved",
    "ImplementerBlockedError",
    "PlanArtifactMissingError",
]


def write_plan_yaml(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    workspace: Path | str | None = None,
    *,
    auto_approve: bool = False,
) -> Path:
    """Write specs/<feature_id>/plan.yaml, emit PLAN_READY, and return the path.

    This is the canonical entry point called after F-R7-450 spec-critic passes.
    It writes plan.yaml with ``approved: false`` by default so implementers are
    blocked until a human (or CI with --auto-approve) sets it to true.

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
        Override for the workspace root (defaults to CWD).
    auto_approve:
        When True, writes ``approved: true`` unconditionally (CI use).

    Returns
    -------
    Path
        Absolute path to the written plan.yaml.

    Raises
    ------
    ValueError:
        When feature_id is empty/None, name is empty/None,
        or acceptance_criteria is not a list.
    """
    return write_plan_artifact(
        feature_id=feature_id,
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
        auto_approve=auto_approve,
    )


def validate_plan_yaml(
    feature_id: str,
    workspace: Path | str | None = None,
) -> dict[str, Any]:
    """Validate the structure and content of specs/<feature_id>/plan.yaml.

    Checks that the file exists, is valid YAML, and contains the required keys
    (feature_id, name, acceptance_criteria, approved, spec_hash).

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml to validate.
    workspace:
        Override for the workspace root (defaults to CWD).

    Returns
    -------
    dict with keys:
        valid: bool — True iff the plan.yaml passes all structural checks.
        errors: list[str] — list of validation error messages (empty when valid).
        data: dict | None — parsed YAML content, or None if unparseable.

    Raises
    ------
    ValueError:
        When feature_id is empty or None.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")

    plan = load_plan(feature_id, workspace)
    errors: list[str] = []

    if plan is None:
        errors.append("plan.yaml is absent or unparseable")
        return {"valid": False, "errors": errors, "data": None}

    required_keys = ["feature_id", "name", "acceptance_criteria", "approved", "spec_hash"]
    for key in required_keys:
        if key not in plan:
            errors.append(f"missing required key: {key!r}")

    if "acceptance_criteria" in plan and not isinstance(plan["acceptance_criteria"], list):
        errors.append(
            f"acceptance_criteria must be a list, got {type(plan['acceptance_criteria']).__name__}"
        )

    if "approved" in plan and not isinstance(plan["approved"], bool):
        errors.append(f"approved must be a bool, got {type(plan['approved']).__name__}")

    return {"valid": len(errors) == 0, "errors": errors, "data": plan}


def check_plan_approved(
    feature_id: str,
    workspace: Path | str | None = None,
) -> bool:
    """Return True when plan.yaml is approved, False otherwise — never raises.

    A non-raising convenience wrapper for use in polling loops or conditional
    logic where raising an exception is not appropriate.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml to inspect.
    workspace:
        Override for the workspace root (defaults to CWD).

    Returns
    -------
    bool
        True iff plan.yaml exists and approved=true.
        False when plan.yaml is absent or approved=false.

    Raises
    ------
    ValueError:
        When feature_id is empty or None.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")
    return is_approved(feature_id, workspace)


def enforce_plan_approval_gate(
    feature_id: str,
    workspace: Path | str | None = None,
    *,
    raise_on_blocked: bool = True,
) -> bool:
    """Enforce that plan.yaml.approved=true before an implementer fires.

    Implementer sub-agents MUST call this at startup. When the plan is absent
    or unapproved and raise_on_blocked=True, raises ImplementerBlockedError so
    the orchestrator can surface the block to the operator.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml to check.
    workspace:
        Override for the workspace root (defaults to CWD).
    raise_on_blocked:
        When True (default), raises ImplementerBlockedError if not approved.
        When False, returns False instead of raising.

    Returns
    -------
    bool
        True when approved; False when not approved and raise_on_blocked=False.

    Raises
    ------
    ValueError:
        When feature_id is empty or None.
    ImplementerBlockedError:
        When plan.yaml is absent or approved=false and raise_on_blocked=True.
    """
    if not feature_id or not isinstance(feature_id, str):
        raise ValueError("feature_id must be a non-empty string")

    approved = is_approved(feature_id, workspace)

    if not approved:
        if raise_on_blocked:
            refuse_implementer_when_unapproved(feature_id, workspace)
        return False

    return True
