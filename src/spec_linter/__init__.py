"""Spec ambiguity linter package — public entry point.

Pre-plan gate that scans every acceptance_criteria entry and rejects
ambiguous patterns. Each AC must match one of the structured forms:

  File exists: <path>
  Function defined: <dotted.path>
  Class defined: <dotted.path>
  pytest: <test_path>
  integration: <dotted.module>
  behavior: <subject> <verb> <object> when <condition>
"""

from spec_linter.linter import (
    LintIssue,
    LintReport,
    lint_acceptance_criteria,
)
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
