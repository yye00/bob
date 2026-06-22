"""Spec ambiguity linter — public entry point.

Pre-plan gate that scans every acceptance_criteria entry and rejects
ambiguous patterns. Each AC must match one of the structured forms:

  File exists: <path>
  Function defined: <dotted.path>
  Class defined: <dotted.path>
  pytest: <test_path>
  integration: <dotted.module>
  behavior: <subject> <verb> <object> when <condition>

The linter fails the plan if any feature has an ambiguous AC and emits
a structured report naming the offending feature and AC index.

Public API::

    from spec_linter import lint_acceptance_criteria, LintReport, LintIssue

    issues = lint_acceptance_criteria("MyFeature", [
        "File exists: src/foo.py",
        "works correctly",            # ambiguous — will be flagged
    ])
    if issues:
        print(issues[0].reason)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bob3.spec_quality.ambiguity_linter import (
    AmbiguityIssue,
    FeatureLintResult,
    SpecLintReport,
    lint_feature,
    lint_spec,
)


# ---------------------------------------------------------------------------
# Re-export core types so callers only need to import from spec_linter
# ---------------------------------------------------------------------------

__all__ = [
    "AmbiguityIssue",
    "FeatureLintResult",
    "LintIssue",
    "LintReport",
    "SpecLintReport",
    "lint_acceptance_criteria",
    "lint_spec",
    "lint_feature",
]


@dataclass
class LintIssue:
    """One ambiguity finding for a single acceptance criterion.

    Mirrors :class:`bob3.spec_quality.ambiguity_linter.AmbiguityIssue`
    but uses the simpler field names expected by the CLI report formatter.
    """

    ac_index: int
    criterion: str
    reason: str


@dataclass
class LintReport:
    """Aggregate lint report returned by :func:`lint_acceptance_criteria`."""

    feature_name: str
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def format_report(self) -> str:
        """Return a human-readable report string."""
        if self.passed:
            return f"Spec ambiguity lint: PASSED — {self.feature_name!r}"
        lines = [f"Spec ambiguity lint: FAILED — {self.feature_name!r}", ""]
        for issue in self.issues:
            lines.append(f"  AC[{issue.ac_index}] {issue.criterion!r}: {issue.reason}")
        return "\n".join(lines)


def lint_acceptance_criteria(
    feature_name: str,
    acceptance_criteria: list[str],
) -> list[LintIssue]:
    """Lint a feature's acceptance criteria and return a list of issues.

    Parameters
    ----------
    feature_name:
        The name or ID of the feature being linted (used in reports).
    acceptance_criteria:
        List of acceptance criterion strings.

    Returns
    -------
    list[LintIssue]
        All ambiguity issues found. Empty list means the criteria passed.
    """
    result: FeatureLintResult = lint_feature(feature_name, acceptance_criteria)
    return [
        LintIssue(
            ac_index=issue.ac_index,
            criterion=issue.criterion,
            reason=issue.reason,
        )
        for issue in result.issues
    ]
