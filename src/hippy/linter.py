"""Hippy spec linter with auto-repair integration.

Thin façade over the shared spec ambiguity linter that wires ambiguous
acceptance criteria into the auto-repair pipeline
(:mod:`hippy.auto_repair`). ERROR-severity rewrites that pass the
semantic-equivalence check are auto-applied unless the feature opts out with
``auto_repair=False``.

Public API::

    from hippy.linter import lint_and_repair

    result = lint_and_repair("feat-001", ["The system should process requests."])
    result["repaired_acs"]     # ACs with ERROR-smell rewrites applied
    result["repairs_applied"]  # list of repair dicts
    result["lint_issues"]      # remaining lint issues (post-repair)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bob.spec_quality.ambiguity_linter import (
    AmbiguityIssue,
    FeatureLintResult,
    lint_feature,
)

from hippy.auto_repair import auto_apply_rewrites, verify_semantic_equivalence

__all__ = [
    "AmbiguityIssue",
    "FeatureLintResult",
    "lint_feature",
    "lint_and_repair",
    "auto_apply_rewrites",
    "verify_semantic_equivalence",
]


def lint_and_repair(
    feature_id: str,
    acceptance_criteria: list[str],
    repairs_log: Path | None = None,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Lint *acceptance_criteria* then auto-repair ERROR-severity smells.

    Ambiguous ACs are surfaced as smell findings and fed through
    :func:`hippy.auto_repair.auto_apply_rewrites`. Only ERROR-severity findings
    that carry a ``suggested_rewrite`` and pass semantic-equivalence checking
    are applied; set ``auto_repair=False`` to disable repairs for this feature.

    Returns
    -------
    dict with keys ``repaired_acs`` (list[str]), ``repairs_applied``
    (list[dict]) and ``lint_issues`` (list[AmbiguityIssue]).

    Raises
    ------
    ValueError
        If *feature_id* is not a string or *acceptance_criteria* is not a list.
    """
    if not isinstance(feature_id, str):
        raise ValueError(
            f"feature_id must be a string, got {type(feature_id).__name__}"
        )
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__}"
        )

    lint_result: FeatureLintResult = lint_feature(feature_id, acceptance_criteria)

    findings: list[dict[str, Any]] = [
        {
            "smell_id": getattr(issue, "smell_id", "AMBIGUOUS"),
            "smell_name": getattr(issue, "smell_name", "AmbiguousAC"),
            "severity": getattr(issue, "severity", "E"),
            "text": issue.criterion,
            "detail": issue.reason,
            "suggested_rewrite": getattr(issue, "suggested_rewrite", None),
        }
        for issue in lint_result.issues
    ]

    repair_result = auto_apply_rewrites(
        feature_id=feature_id,
        findings=findings,
        original_acs=acceptance_criteria,
        repairs_log=repairs_log,
        auto_repair=auto_repair,
    )

    return {
        "repaired_acs": repair_result["repaired_acs"],
        "repairs_applied": repair_result["repairs_applied"],
        "lint_issues": list(lint_result.issues),
    }
