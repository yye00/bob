"""Spec ambiguity linter — pre-plan gate rejecting vague acceptance criteria.

Scans every acceptance_criteria entry and rejects ambiguous patterns.
Each AC must match one of the structured forms:

  File exists: <path>
  Function defined: <dotted.path>
  Class defined: <dotted.path>
  pytest: <test_path>
  integration: <dotted.module>
  behavior: <subject> <verb> <object> when <condition>  (EARS-style)

The linter fails the plan if any feature has an ambiguous AC and emits a
structured report naming the offending feature and AC index.

Public API::

    from bob.spec_ambiguity_linter import lint_acceptance_criteria, LintReport, LintIssue

    issues = lint_acceptance_criteria("MyFeature", [
        "File exists: src/foo.py",
        "works correctly",   # ambiguous — will be flagged
    ])
    if issues:
        print(issues[0].reason)
"""

from __future__ import annotations

from spec_linter.linter import (
    LintIssue,
    LintReport,
    lint_acceptance_criteria,
    lint_and_repair,
    lint_feature,
    lint_spec,
)
from bob.spec_quality.ambiguity_linter import (
    AmbiguityIssue,
    FeatureLintResult,
    SpecLintReport,
    is_ambiguous_ac,
    is_ambiguous_criterion,
)

__all__ = [
    "AmbiguityIssue",
    "FeatureLintResult",
    "LintIssue",
    "LintReport",
    "SpecLintReport",
    "is_ambiguous_ac",
    "is_ambiguous_criterion",
    "lint_acceptance_criteria",
    "lint_and_repair",
    "lint_feature",
    "lint_spec",
]
