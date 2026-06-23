"""bob3.planner — planning-time AC validation integration.

Wires :func:`bob3.validators.validate_acceptance_criteria` and the full
22-smell linter (:mod:`bob3.linter.smella_22`) into the feature-creation
flow so malformed or smelly acceptance criteria are rejected before
features are persisted to the database.

Usage (called internally by ``bob3 plan --create``)::

    from bob3.planner import validate_feature_acs

    validate_feature_acs(feature_dict)
    # Raises ValueError if any AC is malformed or has E-severity smells.
"""

from __future__ import annotations

from pathlib import Path

from bob3.validators import MalformedACError, validate_acceptance_criteria
from bob3.spec_quality.composite_score import compute_composite_score  # noqa: F401 — integration
from bob3.linter.smella_22 import detect_all_smells, filter_by_severity, blocks_plan_create  # noqa: F401 — integration
from bob3.orchestrator.plan_gate import emit_plan_ready_event as _emit_plan_ready_event  # noqa: F401 — re-export

__all__ = [
    "validate_feature_acs",
    "validate_acceptance_criteria",
    "MalformedACError",
    "compute_composite_score",
    "detect_all_smells",
    "filter_by_severity",
    "blocks_plan_create",
    "emit_plan_ready_event",
]


def emit_plan_ready_event(
    feature_id: str,
    plan_path: str,
    approved: bool,
    workspace: Path | str | None = None,
) -> None:
    """Emit a PLAN_READY event to runs/events.jsonl.

    Delegates to :func:`bob3.orchestrator.plan_gate.emit_plan_ready_event`.
    Exposed here so callers can import from bob3.planner directly.

    Args:
        feature_id: UUID of the feature.
        plan_path: Path to the written plan.yaml (may be empty string).
        approved: Whether the plan has been approved.
        workspace: Override for the workspace root (defaults to CWD).
    """
    _emit_plan_ready_event(feature_id, plan_path, approved, workspace)


def validate_feature_acs(feature: dict) -> list[str]:
    """Validate the acceptance_criteria field of a feature dict at planning time.

    Runs both structural validation and the 22-smell linter. E-severity
    findings block plan creation; W/I findings are returned as warnings.

    Parameters
    ----------
    feature:
        A feature dict as parsed from the YAML spec (may contain
        ``acceptance_criteria`` as a list of strings or be absent).

    Returns
    -------
    list[str]
        Empty list when all criteria are well-formed and smell-free.

    Raises
    ------
    ValueError
        When one or more criteria are malformed or have E-severity smells.
    """
    criteria = feature.get("acceptance_criteria") or []
    if isinstance(criteria, str):
        criteria = [criteria]
    criteria = list(criteria)
    validate_acceptance_criteria(criteria)

    blocking_details: list[str] = []
    for ac in criteria:
        findings = detect_all_smells(ac, peer_criteria=criteria)
        e_findings = filter_by_severity(findings, "E")
        for f in e_findings:
            blocking_details.append(f"[{f.smell_id}] {f.detail}")

    if blocking_details:
        raise ValueError(
            "E-severity smell(s) block bob3 plan --create:\n"
            + "\n".join(f"  • {d}" for d in blocking_details)
        )
    return []
