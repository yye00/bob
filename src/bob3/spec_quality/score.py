"""Spec quality score gate — features below threshold cannot reach ready.

Combines F-R7-410 / F-R7-411 / F-R7-412 plus an AC-coverage metric into
a per-feature spec_quality_score in [0, 1]. Features with score < 0.85
stay pending with a structured remediation report.

Public API
----------
compute_spec_quality_score : compute the composite score for a feature.
generate_remediation_report : produce a structured remediation report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from bob3.spec_quality.quality_score import compute_score, gate_for_ready


def compute_spec_quality_score(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> float:
    """Compute the composite spec quality score for a single feature.

    Combines four sub-scorers (F-R7-410, F-R7-411, F-R7-412, AC-coverage)
    into a score in [0, 1]. Features with score < 0.85 stay pending.

    Parameters
    ----------
    name:
        Feature name. Must be a non-None, non-integer string.
    description:
        Feature description text. May be None.
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root directory for reachability checks. Defaults to Path.cwd().

    Returns
    -------
    float
        Composite spec quality score in [0.0, 1.0].

    Raises
    ------
    ValueError
        When *name* is None or not a string.
    ValueError
        When *acceptance_criteria* is not a list or string.
    """
    if name is None:
        raise ValueError("feature name must not be None; provide a non-empty string.")
    if not isinstance(name, str):
        raise ValueError(
            f"feature name must be a string, got {type(name).__name__!r}."
        )
    if not isinstance(acceptance_criteria, (list, str)):
        raise ValueError(
            f"acceptance_criteria must be a list or string, got "
            f"{type(acceptance_criteria).__name__!r}."
        )

    report = compute_score(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    return report.score


def generate_remediation_report(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> str | None:
    """Generate a structured remediation report for a feature failing the gate.

    Returns a structured report when score < 0.85 detailing which sub-scores
    contributed to the failure and how to fix them. Returns None when passing.

    Parameters
    ----------
    name:
        Feature name. Must be a non-None string.
    description:
        Feature description text. May be None.
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root directory for reachability checks. Defaults to Path.cwd().

    Returns
    -------
    str | None
        Structured remediation report when score < threshold, or None when passing.

    Raises
    ------
    ValueError
        When *name* is None or not a string.
    ValueError
        When *acceptance_criteria* is not a list or string.
    """
    if name is None:
        raise ValueError("feature name must not be None; provide a non-empty string.")
    if not isinstance(name, str):
        raise ValueError(
            f"feature name must be a string, got {type(name).__name__!r}."
        )
    if not isinstance(acceptance_criteria, (list, str)):
        raise ValueError(
            f"acceptance_criteria must be a list or string, got "
            f"{type(acceptance_criteria).__name__!r}."
        )

    report = compute_score(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    _passed, message = gate_for_ready(report)
    return message


def calculate_spec_quality_score(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> float:
    """Compute the spec quality score for a single feature.

    Alias for :func:`compute_spec_quality_score` — the canonical name required
    by the feature AC ``Function defined: bob3.spec_quality.calculate_spec_quality_score``.

    Combines four sub-scorers (F-R7-410, F-R7-411, F-R7-412, AC-coverage)
    into a composite score in [0, 1]. Features with score < 0.85 stay pending.

    Parameters
    ----------
    name:
        Feature name. Must not be None.
    description:
        Feature description text. May be None.
    acceptance_criteria:
        List of AC strings, or a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root directory for reachability checks. Defaults to Path.cwd().

    Returns
    -------
    float
        Composite spec quality score in [0.0, 1.0].

    Raises
    ------
    ValueError
        When *name* is None or not a string.
    ValueError
        When *acceptance_criteria* is not a list or string.
    """
    return compute_spec_quality_score(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
