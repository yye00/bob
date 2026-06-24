"""Spec quality score gate — features below threshold cannot reach ready.

Public entry point that combines F-R7-410 / F-R7-411 / F-R7-412 plus an
AC-coverage metric into a per-feature spec_quality_score in [0, 1].

Features with score < 0.85 stay pending with a structured remediation report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from bob.spec_quality.quality_score import (
    QualityReport,
    compute_score,
    gate_for_ready,
)


def spec_quality_score_gate_features_below_threshold_cannot_reach_ready(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Union[Path, str, None] = None,
) -> tuple[float, bool, str | None]:
    """Compute spec quality score and apply the ready-promotion gate.

    Combines four sub-scorers (ambiguity, reachability, EARS, AC coverage)
    into a composite score in [0, 1]. Features with score < 0.85 are blocked
    from reaching 'ready' status and receive a structured remediation report.

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
