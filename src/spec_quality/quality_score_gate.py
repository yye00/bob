"""Spec quality score gate — features below threshold cannot reach ready.

Combines the F-R7-410 (ambiguity), F-R7-411 (integration reachability) and
F-R7-412 (EARS behaviour) sub-scorers plus an AC-coverage metric into a
per-feature ``spec_quality_score`` in [0, 1]. Features whose score falls below
the resolved threshold (default 0.85) stay at ``status='pending'`` and receive a
structured remediation report describing which sub-scores dragged the composite
down and how to fix them.

Computation is delegated to :mod:`bob.spec_quality.quality_score`, which owns the
four sub-scorers and the weighted-average composite. This module is the
``spec_quality``-package facade required by the feature's acceptance criteria and
integrates with :mod:`spec_quality.composite_score`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from bob.spec_quality.quality_score import compute_score, gate_for_ready
from bob.spec_quality.threshold_resolver import resolve_spec_quality_threshold


def _validate_inputs(
    name: object,
    acceptance_criteria: object,
) -> None:
    """Validate the shared inputs for both public functions.

    Raises
    ------
    ValueError
        When *name* is None or not a string, or when *acceptance_criteria* is
        neither a list nor a string.
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


def compute_spec_quality_score(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> float:
    """Compute the composite spec quality score for a single feature.

    Combines four sub-scorers (F-R7-410 ambiguity, F-R7-411 integration
    reachability, F-R7-412 EARS behaviour, and AC-coverage) into a single score
    in [0, 1]. An empty acceptance-criteria list yields ``0.0`` (a feature with
    no verifiable ACs cannot be trusted), never an exception.

    Parameters
    ----------
    name:
        Feature name. Must be a non-None string.
    description:
        Feature description text (used for AC-coverage analysis). May be None.
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root directory for reachability checks. Defaults to ``Path.cwd()``.

    Returns
    -------
    float
        Composite spec quality score in [0.0, 1.0].

    Raises
    ------
    ValueError
        When *name* is None or not a string, or when *acceptance_criteria* is
        neither a list nor a string.
    """
    _validate_inputs(name, acceptance_criteria)

    report = compute_score(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    return report.score


def gate_feature_readiness(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> dict[str, object]:
    """Decide whether a feature may be promoted to ``status='ready'``.

    A feature passes the gate when its composite ``spec_quality_score`` is at or
    above the resolved threshold (``BOB_SPEC_QUALITY_THRESHOLD``, default 0.85).
    Otherwise it stays ``pending`` and the returned ``remediation`` field carries
    a structured report listing the offending sub-scores and how to fix them.

    Parameters
    ----------
    name:
        Feature name. Must be a non-None string.
    description:
        Feature description text. May be None.
    acceptance_criteria:
        List of AC strings, a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root directory for reachability checks. Defaults to ``Path.cwd()``.

    Returns
    -------
    dict
        ``{"ready": bool, "score": float, "threshold": float,
        "remediation": str | None}``. ``remediation`` is ``None`` when the
        feature passes and a structured report string when it is blocked.

    Raises
    ------
    ValueError
        When *name* is None or not a string, or when *acceptance_criteria* is
        neither a list nor a string.
    """
    _validate_inputs(name, acceptance_criteria)

    report = compute_score(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    passed, message = gate_for_ready(report)
    threshold = resolve_spec_quality_threshold()

    return {
        "ready": bool(passed),
        "score": float(report.score),
        "threshold": float(threshold),
        "remediation": message,
    }
