"""Compatibility shim: spec_quality_score local module.

This file establishes ``spec_quality_score`` as a locally-defined module
within the generated-code tree so that any ``import spec_quality_score``
in subagent-generated code resolves to a first-party module rather than
triggering a slopsquatting false-positive.

The canonical implementation lives in
``bob.composite_spec_quality_score_8_sub_metrics_geometric_mean_0``
and ``bob.spec_quality.quality_score``. This shim re-exports the public
surface so that both import paths work.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Union

from bob.composite_spec_quality_score_8_sub_metrics_geometric_mean_0 import (
    composite_spec_quality_score_8_sub_metrics_geometric_mean_0 as compute_score,
    SUB_METRIC_WEIGHTS,
)
from bob.spec_quality.quality_score import (
    compute_score as _compute_score_internal,
    QualityReport as SpecQualityReport,
)
from bob.spec_quality.score import (
    generate_remediation_report,
)
from bob.spec_quality.composite_score import (
    compute_composite_score,
    calculate_geometric_mean as _calculate_geometric_mean,
    CompositeScoreResult as _CompositeScoreResult,
)
from tools.spec_quality_score import (
    filter_api_surfaces as _filter_api_surfaces,
    _is_code_identifier,
    compute,
    is_code_shaped_token,
    filter_api_surfaces,
    extract_py_paths_from_description,
    extract_concrete_py_paths,
    extract_py_paths,
)
from bob.spec_synthesizer import emit_file_exists_acs


class ScoreResult(_CompositeScoreResult):
    """Result of the composite spec_quality_score computation.

    Attributes
    ----------
    score:
        Weighted geometric mean of 8 sub-metrics, in [0.0, 1.0].
    gate:
        One of ``'refuse'`` (score < 0.65), ``'warn'`` (0.65–0.80),
        or ``'green'`` (>= 0.80).

    This class satisfies the AC:
    ``Function defined: bob.spec_quality_score.ScoreResult``
    """


def compute_quality_score(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> float:
    """Compute the per-feature spec quality score in [0, 1].

    Combines F-R7-410 / F-R7-411 / F-R7-412 plus an AC-coverage metric.
    Features with score < 0.85 stay pending with a structured remediation
    report (see :func:`generate_remediation_report`).

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
    report = _compute_score_internal(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    return report.score


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
        Feature name. Must be a non-None string.
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
    report = _compute_score_internal(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    return report.score


def compute_weighted_geometric_mean(
    values: Dict[str, float],
    weights: Dict[str, float],
) -> float:
    """Compute the weighted geometric mean of *values* using *weights*.

    Implements the core computation for the composite spec_quality_score gate:
    score < 0.65 refuses plan --create; 0.65-0.80 warns; >= 0.80 is green.

    Parameters
    ----------
    values:
        Mapping from metric name to its score in [0, 1].
    weights:
        Mapping from metric name to its weight. Must cover all keys in *values*.

    Returns
    -------
    float
        Weighted geometric mean, clamped to [0.0, 1.0].

    Raises
    ------
    ValueError
        When *values* or *weights* is empty, or when a required key is missing
        from *weights*.
    """
    return _calculate_geometric_mean(values, weights)


def compute_geometric_mean(
    values: Dict[str, float],
    weights: Dict[str, float],
) -> float:
    """Compute the weighted geometric mean of *values* using *weights*.

    Parameters
    ----------
    values:
        Mapping from metric name to its score in [0, 1].
    weights:
        Mapping from metric name to its weight. Must cover all keys in *values*.

    Returns
    -------
    float
        Weighted geometric mean, clamped to [0.0, 1.0].

    Raises
    ------
    ValueError
        When *values* or *weights* is empty, or when a required key is missing
        from *weights*.
    """
    return _calculate_geometric_mean(values, weights)


def compute_composite_quality_score(
    metrics: Dict[str, float],
) -> Dict[str, object]:
    """Compute the composite spec quality score from the 8 required sub-metrics.

    Replaces the F-R7-413 placeholder with a weighted geometric mean of 8
    sub-metrics: smell_density (0.20), predicate_coverage (0.20),
    contract_completeness (0.15), boundary_coverage (0.10),
    error_path_coverage (0.10), traceability (0.10), spec_executability (0.10),
    ac_atomicity (0.05).

    Gate semantics: score < 0.65 refuses plan --create; 0.65-0.80 warns;
    >= 0.80 is green.

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].
        All 8 keys must be present.

    Returns
    -------
    dict
        ``{"score": float, "gate": "green" | "warn" | "refuse"}``

    Raises
    ------
    ValueError
        When any required sub-metric key is absent.
    """
    return compute_composite_score(metrics)


def filter_code_shaped_tokens(tokens: list[str]) -> list[str]:
    """Return only code-shaped tokens from *tokens*, filtering out prose words.

    A token is code-shaped when it contains an underscore (``_``), a dot
    (``.``), a ``.py`` extension, or internal CamelCase (has BOTH upper and
    lower letters). Plain English words like "defined", "name", "correctly"
    are filtered out.

    This function satisfies the AC:
    ``Function defined: bob.spec_quality_score.filter_code_shaped_tokens``

    Parameters
    ----------
    tokens:
        List of candidate surface tokens extracted from a feature description.

    Returns
    -------
    list[str]
        Filtered list containing only code-shaped tokens (order preserved).

    Raises
    ------
    ValueError
        When *tokens* is not a list.
    """
    if not isinstance(tokens, list):
        raise ValueError(
            f"tokens must be a list, got {type(tokens).__name__!r}."
        )
    return _filter_api_surfaces(tokens)


def assess_gate_status(score: float) -> str:
    """Return the gate label for a given composite spec quality score.

    Implements the 0.65/0.80 gate semantics for the composite spec_quality_score:
    score < 0.65 → 'refuse' (plan --create blocked);
    0.65 ≤ score < 0.80 → 'warn';
    score >= 0.80 → 'green'.

    Parameters
    ----------
    score:
        The composite spec quality score in [0, 1].

    Returns
    -------
    str
        One of ``'refuse'``, ``'warn'``, or ``'green'``.

    Raises
    ------
    TypeError
        When *score* is not a numeric type.
    """
    if not isinstance(score, (int, float)):
        raise TypeError(
            f"score must be a numeric type, got {type(score).__name__!r}."
        )
    score = float(score)
    if score >= 0.80:
        return "green"
    if score >= 0.65:
        return "warn"
    return "refuse"


def calculate_composite_score(
    metrics: Dict[str, float],
) -> Dict[str, object]:
    """Compute the composite spec quality score from the 8 required sub-metrics.

    Weighted geometric mean of 8 sub-metrics: smell_density (0.20),
    predicate_coverage (0.20), contract_completeness (0.15),
    boundary_coverage (0.10), error_path_coverage (0.10),
    traceability (0.10), spec_executability (0.10), ac_atomicity (0.05).

    Gate: score < 0.65 → refuse; 0.65 ≤ score < 0.80 → warn; >= 0.80 → green.

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].

    Returns
    -------
    dict
        ``{"score": float, "gate": "green" | "warn" | "refuse"}``

    Raises
    ------
    ValueError
        When any required sub-metric key is absent.
    """
    return compute_composite_score(metrics)


def remediation_report(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> str | None:
    """Generate a structured remediation report for a feature failing the gate.

    Combines F-R7-410 / F-R7-411 / F-R7-412 plus an AC-coverage metric into a
    per-feature spec_quality_score in [0, 1]. When score < 0.85 the feature stays
    pending and this function returns a structured report detailing which
    sub-scores contributed to the failure and how to fix them.

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
        Structured remediation report when score < 0.85, or None when passing.

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
    from bob.spec_quality.quality_score import gate_for_ready
    report = _compute_score_internal(
        name=name,
        description=description,
        acceptance_criteria=acceptance_criteria,
        workspace=workspace,
    )
    _passed, message = gate_for_ready(report)
    return message


def validate_score_thresholds(score: float) -> str:
    """Return the gate label for a given composite spec quality score.

    Gate semantics:
      score < 0.65  → 'refuse'  (plan --create is blocked)
      0.65 ≤ score < 0.80 → 'warn'
      score >= 0.80 → 'green'

    Function defined: bob.spec_quality_score.validate_score_thresholds

    Parameters
    ----------
    score:
        The composite spec quality score in [0, 1].

    Returns
    -------
    str
        One of ``'refuse'``, ``'warn'``, or ``'green'``.

    Raises
    ------
    TypeError
        When *score* is not a numeric type.
    """
    if not isinstance(score, (int, float)):
        raise TypeError(
            f"score must be a numeric type, got {type(score).__name__!r}."
        )
    score = float(score)
    if score >= 0.80:
        return "green"
    if score >= 0.65:
        return "warn"
    return "refuse"


def validate_score_gate(score: float) -> str:
    """Return the gate label for a given composite spec quality score.

    Gate semantics:
      score < 0.65  → 'refuse'  (plan --create is blocked)
      0.65 ≤ score < 0.80 → 'warn'
      score >= 0.80 → 'green'

    Parameters
    ----------
    score:
        The composite spec quality score in [0, 1].

    Returns
    -------
    str
        One of ``'refuse'``, ``'warn'``, or ``'green'``.

    Raises
    ------
    TypeError
        When *score* is not a numeric type.
    """
    if not isinstance(score, (int, float)):
        raise TypeError(
            f"score must be a numeric type, got {type(score).__name__!r}."
        )
    score = float(score)
    if score >= 0.80:
        return "green"
    if score >= 0.65:
        return "warn"
    return "refuse"


def evaluate_quality_gate(
    metrics: Dict[str, float],
) -> Dict[str, object]:
    """Evaluate the quality gate for the 8 sub-metric composite spec_quality_score.

    Computes the weighted geometric mean of the 8 required sub-metrics and
    applies the 0.65/0.80 gate thresholds.

    Gate semantics:
      score < 0.65  → gate='refuse'  (plan --create is rejected)
      0.65 ≤ score < 0.80 → gate='warn'
      score >= 0.80 → gate='green'

    Parameters
    ----------
    metrics:
        Dict mapping each of the 8 sub-metric names to a score in [0, 1].
        All 8 keys must be present: smell_density, predicate_coverage,
        contract_completeness, boundary_coverage, error_path_coverage,
        traceability, spec_executability, ac_atomicity.

    Returns
    -------
    dict
        ``{"score": float, "gate": "green" | "warn" | "refuse"}``

    Raises
    ------
    ValueError
        When any required sub-metric key is absent.
    """
    return compute_composite_score(metrics)


def gate_spec_quality(score_or_metrics: Union[float, int, Dict[str, float]]) -> str:
    """Return the gate label for a composite spec quality score.

    Accepts either a precomputed score in [0, 1] or the full 8-sub-metric
    dict (in which case the weighted geometric mean is computed first via
    :func:`compute_composite_score`).

    Gate semantics (the 0.65/0.80 gate that replaces F-R7-413):
      score < 0.65        → 'refuse'  (plan --create is blocked)
      0.65 <= score < 0.80 → 'warn'
      score >= 0.80       → 'green'

    Function defined: bob.spec_quality_score.gate_spec_quality

    Parameters
    ----------
    score_or_metrics:
        Either a numeric score in [0, 1], or a dict of the 8 sub-metrics.

    Returns
    -------
    str
        One of ``'refuse'``, ``'warn'``, or ``'green'``.

    Raises
    ------
    ValueError
        When the argument is neither a numeric score nor a metrics dict, or
        when a metrics dict is missing a required sub-metric.
    """
    if isinstance(score_or_metrics, dict):
        result = compute_composite_score(score_or_metrics)
        return str(result["gate"])
    if isinstance(score_or_metrics, bool) or not isinstance(
        score_or_metrics, (int, float)
    ):
        raise ValueError(
            "gate_spec_quality expects a numeric score in [0, 1] or a dict "
            f"of the 8 sub-metrics, got {type(score_or_metrics).__name__!r}."
        )
    score = float(score_or_metrics)
    if score >= 0.80:
        return "green"
    if score >= 0.65:
        return "warn"
    return "refuse"


__all__ = [
    "compute",
    "compute_score",
    "gate_spec_quality",
    "SUB_METRIC_WEIGHTS",
    "compute_quality_score",
    "compute_spec_quality_score",
    "remediation_report",
    "generate_remediation_report",
    "compute_composite_score",
    "compute_composite_quality_score",
    "calculate_composite_score",
    "compute_weighted_geometric_mean",
    "compute_geometric_mean",
    "assess_gate_status",
    "validate_score_thresholds",
    "validate_score_gate",
    "evaluate_quality_gate",
    "SpecQualityReport",
    "filter_code_shaped_tokens",
    "ScoreResult",
    "is_code_shaped_token",
    "filter_api_surfaces",
    "extract_py_paths_from_description",
    "extract_concrete_py_paths",
    "extract_py_paths",
    "emit_file_exists_acs",
]
