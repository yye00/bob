"""Spec quality gate threshold must honor BOB_SPEC_QUALITY_THRESHOLD env var.

The gate threshold is resolved lazily on every call via
:func:`bob.spec_quality.threshold_resolver.resolve_spec_quality_threshold`,
so operator changes (e.g. lowering the bar to unstick ALL_BLOCKED runs) take
effect on the next gate evaluation without a process restart.

Escape hatch: set BOB_SPEC_QUALITY_THRESHOLD_FROZEN=<value> to pin the
threshold for the lifetime of the process (useful in tests that need a
deterministic value).
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from bob.spec_quality.quality_score import (
    QualityReport,
    compute_score,
    gate_for_ready,
)


def spec_quality_score_gate_threshold_must_honor_bob_spec(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Union[Path, str, None] = None,
) -> tuple[float, bool, str | None]:
    """Compute spec quality score and apply the env-var-driven ready-promotion gate.

    The threshold is read lazily from ``BOB_SPEC_QUALITY_THRESHOLD`` on every
    call (default 0.85, clamped to [0.0, 1.0]). This ensures that an operator
    can lower the threshold mid-run to unstick pending features without restarting
    the process — previously the hardcoded ``_THRESHOLD = 0.85`` constant made
    the env var a silent no-op.

    Parameters
    ----------
    name:
        Feature name.
    description:
        Feature description text (used for AC coverage analysis).
    acceptance_criteria:
        List of AC strings, or a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root directory for reachability checks. Defaults to ``Path.cwd()``.

    Returns
    -------
    tuple[float, bool, str | None]
        - ``score``: composite spec_quality_score in [0, 1]
        - ``passed``: True when score >= threshold (feature may reach 'ready')
        - ``remediation``: None when passed; structured report string when blocked
    """
    report: QualityReport = compute_score(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    passed, remediation = gate_for_ready(report)
    return report.score, passed, remediation
