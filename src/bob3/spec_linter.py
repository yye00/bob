"""Spec ambiguity linter — bob3 package entry point.

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

    from bob3.spec_linter import lint_acceptance_criteria, LintReport, LintIssue

    issues = lint_acceptance_criteria("MyFeature", [
        "File exists: src/foo.py",
        "works correctly",            # ambiguous — will be flagged
    ])
    if issues:
        print(issues[0].reason)
"""

from __future__ import annotations

from bob3.spec_quality.ambiguity_linter import (
    AmbiguityIssue,
    FeatureLintResult,
    SpecLintReport,
    lint_feature,
    lint_spec,
)

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

# Re-export from spec_linter package for convenience
from spec_linter.linter import LintIssue, LintReport, lint_acceptance_criteria
