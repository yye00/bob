"""Persistent spec-critic findings registry with regression detection.

F-R7-450: critic writes findings to reviews/spec_findings.yaml keyed by
(spec_hash, slot_id, defect_type). On re-run with same defect at same slot,
critic flags REGRESSION and escalates severity. Halt-gate fires if
critic_repeat_rate > 0.30 over 3 runs.

Public API::

    from bob3.spec_critic_registry import write_findings, detect_regression

    entry = write_findings(
        spec_hash="abc123",
        slot_id="AC-0",
        defect_type="ambiguity",
        feature_id="feat-001",
        name="My feature",
        rationale="AC is vague",
        suggested_fix="Use concrete predicate",
    )
    if entry["is_regression"]:
        print(f"REGRESSION detected, escalated to {entry['severity']}")

    is_regression = detect_regression(
        spec_hash="abc123",
        slot_id="AC-0",
        defect_type="ambiguity",
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob3.spec_quality.spec_findings_registry import (
    record,
    detect_regression as _detect_regression,
    compute_critic_repeat_rate,
    is_halt_gate_fired,
)


def write_findings(
    spec_hash: str,
    slot_id: str,
    defect_type: str,
    *,
    feature_id: str = "",
    name: str = "",
    rationale: str = "",
    suggested_fix: str = "",
    severity: str = "warning",
    run_id: str | None = None,
    findings_path: Path | None = None,
    metrics_path: Path | None = None,
) -> dict[str, Any]:
    """Write a spec-critic finding to the persistent registry.

    Keyed by (spec_hash, slot_id, defect_type). On re-run with the same
    composite key, the finding is flagged as REGRESSION and severity is
    escalated one level. The halt-gate fires when critic_repeat_rate > 0.30
    over the last 3 distinct run_ids.

    Parameters
    ----------
    spec_hash:
        Hash of the spec that produced this defect.
    slot_id:
        AC slot identifier, e.g. ``"AC-0"`` or ``"FEATURE"``.
    defect_type:
        Canonical defect type (ambiguity, missing_edge_case, untestable, …).
    feature_id:
        Unique feature identifier.
    name:
        Human-readable feature name.
    rationale:
        Why this defect was flagged.
    suggested_fix:
        Suggested remedy for the defect.
    severity:
        Initial severity (info | warning | error | critical). Escalated on
        regression.
    run_id:
        Opaque identifier for the current run (defaults to ISO timestamp).
    findings_path:
        Override path to spec_findings.yaml; mainly for testing.
    metrics_path:
        Override path to metrics.yaml; mainly for testing.

    Returns
    -------
    dict
        The stored finding entry including ``is_regression``,
        ``severity``, and ``occurrence_count`` fields.

    Raises
    ------
    ValueError
        When severity is not one of (info, warning, error, critical) or when
        required string arguments are None.
    TypeError
        When required string arguments are None.
    """
    return record(
        spec_hash=spec_hash,
        slot_id=slot_id,
        defect_type=defect_type,
        feature_id=feature_id,
        name=name,
        rationale=rationale,
        suggested_fix=suggested_fix,
        severity=severity,
        run_id=run_id,
        findings_path=findings_path,
        metrics_path=metrics_path,
    )


def detect_regression(
    spec_hash: str,
    slot_id: str,
    defect_type: str,
    *,
    findings_path: Path | None = None,
) -> bool:
    """Return True if (spec_hash, slot_id, defect_type) has been seen before.

    Parameters
    ----------
    spec_hash, slot_id, defect_type:
        Composite key identifying the finding.
    findings_path:
        Override path; mainly for testing.

    Returns
    -------
    bool
        True if the same finding key has occurrence_count > 1, else False.

    Raises
    ------
    TypeError
        When spec_hash, slot_id, or defect_type is None.
    ValueError
        When spec_hash, slot_id, or defect_type is not a string.
    """
    return _detect_regression(
        spec_hash=spec_hash,
        slot_id=slot_id,
        defect_type=defect_type,
        findings_path=findings_path,
    )


def check_repeat_rate_halt_gate(
    *,
    findings_path: Path | None = None,
    metrics_path: Path | None = None,
) -> bool:
    """Return True if critic_repeat_rate > 0.30 over the last 3 runs.

    Parameters
    ----------
    findings_path:
        Override path to spec_findings.yaml; mainly for testing.
    metrics_path:
        Override path to metrics.yaml; mainly for testing.

    Returns
    -------
    bool
        True when critic_repeat_rate > 0.30 over the last 3 distinct run_ids.
    """
    return is_halt_gate_fired(findings_path=findings_path, metrics_path=metrics_path)


check_repeat_rate_gate = check_repeat_rate_halt_gate

__all__ = [
    "write_findings",
    "detect_regression",
    "check_repeat_rate_gate",
    "check_repeat_rate_halt_gate",
    "compute_critic_repeat_rate",
    "is_halt_gate_fired",
]
