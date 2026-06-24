"""Persistent spec-critic findings registry with regression detection.

F-R7-450: critic writes findings to reviews/spec_findings.yaml keyed by
(spec_hash, slot_id, defect_type). On re-run with same defect at same slot,
critic flags REGRESSION and escalates severity. Halt-gate fires if
critic_repeat_rate > 0.30 over 3 runs.

Public API::

    from bob.persistent_spec_critic_findings_registry_regression_detection import (
        persistent_spec_critic_findings_registry_regression_detection,
    )

    result = persistent_spec_critic_findings_registry_regression_detection(
        spec_hash="abc123",
        slot_id="AC-0",
        defect_type="ambiguity",
        feature_id="feat-001",
        name="My feature",
        rationale="...",
        suggested_fix="...",
        severity="warning",
        run_id="run-001",
    )
    if result["is_regression"]:
        print(f"REGRESSION: escalated to {result['severity']}")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.spec_findings_registry import record


def persistent_spec_critic_findings_registry_regression_detection(
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
    """Record a spec-critic finding with regression detection and halt-gate.

    Writes to reviews/spec_findings.yaml keyed by (spec_hash, slot_id,
    defect_type). On re-run with the same composite key, the finding is
    flagged as a REGRESSION and severity is escalated one level. The
    halt-gate fires (logged as warning) when critic_repeat_rate > 0.30
    over the last 3 distinct run_ids.

    Parameters
    ----------
    spec_hash:
        Hash of the spec that produced this defect.
    slot_id:
        AC slot identifier, e.g. ``"AC-0"`` or ``"FEATURE"``.
    defect_type:
        One of the canonical defect types defined in spec_critic.DEFECT_TYPES.
    feature_id:
        Unique identifier for the feature.
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
        ``escalated_severity``, and ``occurrence_count`` fields.
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
