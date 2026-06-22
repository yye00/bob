"""Public plan_gate façade for bob3.

Exposes check_plan_approval and enforce_plan_approval as canonical entry points
for implementer sub-agents to check whether a plan.yaml has been approved before
starting work.

Delegates to bob3.orchestrator.plan_gate for all implementation details.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.linter_22smell import (  # noqa: F401 — integration: bob3.plan_gate
    apply_severity_filter,
    blocks_plan_create,
    detect_smells,
)

from bob3.orchestrator.plan_gate import (
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
    "check_plan_approval",
    "check_plan_approved",
    "emit_plan_ready",
    "enforce_plan_approval",
    "lint_acceptance_criteria",
    "validate_plan_approval",
    "ImplementerBlockedError",
    "PlanArtifactMissingError",
    "approve_plan",
    "compute_plan_vs_spec_drift",
    "diff_plan_vs_spec",
    "emit_plan_ready_event",
    "is_approved",
    "load_plan",
    "refuse_implementer_when_unapproved",
    "retrigger_critic_on_edit",
    "write_plan_artifact",
]


def lint_acceptance_criteria(
    criteria: list[str],
    *,
    raise_on_blocking: bool = True,
    peer_criteria: list[str] | None = None,
    known_feature_ids: frozenset[str] | None = None,
) -> list:
    """Lint acceptance criteria with the 22-smell detector catalogue.

    Runs the full 22-smell linter (F-R7-410 extension) over each AC.  When any
    E-severity smell is found and ``raise_on_blocking`` is True, raises
    :class:`ValueError` — blocking ``bob3 plan --create`` per spec.

    Parameters
    ----------
    criteria:
        List of acceptance-criterion strings to lint.
    raise_on_blocking:
        When True (default), raises ValueError if any E-severity smell is found.
    peer_criteria:
        Additional context strings for cross-criterion detectors.
    known_feature_ids:
        Set of valid feature IDs for the dangling-ref detector.

    Returns
    -------
    list
        All :class:`SmellFinding` objects across all criteria, ordered by
        criterion index then smell ID.

    Raises
    ------
    ValueError
        When any E-severity smell is detected and ``raise_on_blocking`` is True.
    """
    all_findings = []
    for ac in criteria:
        findings = detect_smells(
            ac,
            peer_criteria=peer_criteria or criteria,
            known_feature_ids=known_feature_ids,
        )
        all_findings.extend(findings)

    if raise_on_blocking and blocks_plan_create(all_findings):
        blocking = apply_severity_filter(all_findings, "E")
        ids = ", ".join(sorted({f.smell_id for f in blocking}))
        raise ValueError(
            f"E-severity spec smells block plan --create: {ids}. "
            "Fix acceptance criteria before creating a plan."
        )

    return all_findings


def check_plan_approval(
    feature_id: str,
    workspace: str | Path | None = None,
    *,
    raise_on_blocked: bool = True,
) -> bool:
    """Check that plan.yaml.approved=true before an implementer fires.

    Canonical gate function for implementer sub-agents. When the plan is absent
    or unapproved and raise_on_blocked is True, raises ImplementerBlockedError.

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
            raise ImplementerBlockedError(
                f"Implementer blocked: plan.yaml not approved for feature {feature_id}. "
                "Set approved: true in specs/<feature>/plan.yaml before running the implementer."
            )
        return False
    return True


def enforce_plan_approval(
    feature_id: str,
    workspace: str | Path | None = None,
    *,
    raise_on_blocked: bool = True,
) -> bool:
    """Enforce that plan.yaml.approved=true before an implementer fires.

    Alias for check_plan_approval. Retained for backwards compatibility.
    """
    return check_plan_approval(feature_id, workspace, raise_on_blocked=raise_on_blocked)


def validate_plan_approval(
    feature_id: str,
    workspace: str | Path | None = None,
    *,
    raise_on_blocked: bool = True,
) -> bool:
    """Validate that plan.yaml.approved=true before an implementer fires.

    Alias for check_plan_approval. Provides the validate_plan_approval name
    required by the feature AC.

    Parameters
    ----------
    feature_id:
        UUID of the feature whose plan.yaml to validate.
    workspace:
        Override for the workspace root (defaults to CWD).
    raise_on_blocked:
        When True (default), raises ImplementerBlockedError if not approved.
        When False, returns False instead of raising.

    Returns
    -------
    True when approved; False when not approved and raise_on_blocked=False.

    Raises
    ------
    ValueError:
        When feature_id is empty or None.
    ImplementerBlockedError:
        When plan.yaml is absent or approved=false and raise_on_blocked=True.
    """
    return check_plan_approval(feature_id, workspace, raise_on_blocked=raise_on_blocked)


def check_plan_approved(
    feature_id: str,
    workspace: str | Path | None = None,
    *,
    raise_on_blocked: bool = True,
) -> bool:
    """Check that plan.yaml.approved=true before an implementer fires.

    Canonical AC-required name. Delegates to check_plan_approval.

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
    True when approved; False when not approved and raise_on_blocked=False.

    Raises
    ------
    ValueError:
        When feature_id is empty or None.
    ImplementerBlockedError:
        When plan.yaml is absent or approved=false and raise_on_blocked=True.
    """
    return check_plan_approval(feature_id, workspace, raise_on_blocked=raise_on_blocked)


def emit_plan_ready(
    feature_id: str,
    name: str,
    description: str | None,
    acceptance_criteria: list[str],
    workspace: str | Path | None = None,
    *,
    auto_approve: bool = False,
) -> dict:
    """Write specs/<feature_id>/plan.yaml and emit a PLAN_READY event.

    Called after F-R7-450 spec-critic passes. Writes plan.yaml with
    approved=false by default (or true when auto_approve=True) and emits
    a structured PLAN_READY event to runs/events.jsonl.

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
        When True, writes approved=true unconditionally.

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
    ValueError:
        When feature_id is empty/None, name is empty/None,
        or acceptance_criteria is not a list.
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

    emit_plan_ready_event(
        feature_id=feature_id,
        plan_path=str(plan_path),
        approved=is_approved(feature_id, workspace),
        workspace=workspace,
    )

    approved = is_approved(feature_id, workspace)

    return {
        "plan_path": str(plan_path),
        "approved": approved,
        "implementer_blocked": not approved,
        "plan_ready_emitted": True,
        "drift_detected": drift_detected,
    }
