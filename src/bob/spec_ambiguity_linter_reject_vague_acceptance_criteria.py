"""Spec ambiguity linter — pre-plan gate that rejects vague acceptance criteria.

Each AC must match one of the structured forms:
  File exists: <path>
  Function defined: <dotted.path>
  Class defined: <dotted.path>
  pytest: <test_path>
  integration: <dotted.module>
  behavior: <subject> <verb> <object> when <condition>  (EARS-style)

The linter fails the plan if any feature has an ambiguous AC and emits a
structured report naming the offending feature and AC index.
"""

from __future__ import annotations

from typing import Any

from bob.spec_quality.ambiguity_linter import lint_spec


def spec_ambiguity_linter_reject_vague_acceptance_criteria(
    features: list[dict[str, Any]],
) -> dict[str, Any]:
    """Scan every acceptance_criteria entry and reject ambiguous patterns.

    Parameters
    ----------
    features:
        List of feature dicts, each with 'name' (or 'title') and
        'acceptance_criteria' keys.

    Returns
    -------
    dict with keys:
        passed: bool — True if no ambiguous ACs found
        failed_features: list of dicts, each with:
            feature_name: str
            issues: list of dicts with ac_index, criterion, reason
        report: str — human-readable structured report
    """
    report = lint_spec(features)

    failed_features = [
        {
            "feature_name": fr.feature_name,
            "issues": [
                {
                    "ac_index": issue.ac_index,
                    "criterion": issue.criterion,
                    "reason": issue.reason,
                }
                for issue in fr.issues
            ],
        }
        for fr in report.failed_features
    ]

    return {
        "passed": report.passed,
        "failed_features": failed_features,
        "report": report.format_report(),
    }
