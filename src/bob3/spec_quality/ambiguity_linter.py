"""Spec ambiguity linter — reject vague acceptance criteria.

Scans every acceptance_criteria entry and rejects ambiguous patterns:
- Bare verbs ("works", "handles", "supports") without a concrete subject/object
- Missing concrete identifiers (no file path, function name, or test path)
- Unbounded quantifiers ("all cases", "any input")
- Verbs without an observable subject

Each AC must match one of the structured forms:
  File exists: <path>
  Function defined: <dotted.path>
  Class defined: <dotted.path>
  pytest: <test_path>
  integration: <dotted.module>
  behavior: <subject> <verb> <object> when <condition>  (EARS-style)

Run at bob3 plan time. Fails the plan if any feature has an ambiguous AC
and emits a structured report naming the offending feature and AC index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Structured AC patterns (each must match exactly one form)
# ---------------------------------------------------------------------------

# Regex for each accepted AC form.
_AC_FORMS: list[tuple[str, re.Pattern[str]]] = [
    ("File exists", re.compile(r"^File exists\s*:\s*\S+", re.IGNORECASE)),
    ("Function defined", re.compile(r"^Function defined\s*:\s*[\w.]+", re.IGNORECASE)),
    ("Class defined", re.compile(r"^Class defined\s*:\s*[\w.]+", re.IGNORECASE)),
    ("pytest", re.compile(r"^pytest\s*:\s*\S+", re.IGNORECASE)),
    ("integration", re.compile(r"^integration\s*:\s*[\w./:-]+", re.IGNORECASE)),
    (
        "behavior (EARS)",
        re.compile(
            r"^behavior\s*:\s*.+\bwhen\b.+",
            re.IGNORECASE,
        ),
    ),
    # Also accept legacy python: form used by spec_linter_pre_spawn_quality_gate
    ("python", re.compile(r"^python\s*:\s*\S+", re.IGNORECASE)),
    # Field exists form
    ("Field exists", re.compile(r"^Field exists\s*.*:\s*\S+", re.IGNORECASE)),
]

# Bare-verb patterns that indicate vague criteria.
_BARE_VERB_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bworks\b", re.IGNORECASE),
    re.compile(r"\bhandles\b", re.IGNORECASE),
    re.compile(r"\bsupports\b", re.IGNORECASE),
    re.compile(r"^(system|app|module|code|it)\s+\w+s\b", re.IGNORECASE),
]

# Unbounded quantifier patterns.
_UNBOUNDED_QUANTIFIER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\ball\s+cases\b", re.IGNORECASE),
    re.compile(r"\bany\s+input\b", re.IGNORECASE),
    re.compile(r"\beverything\b", re.IGNORECASE),
    re.compile(r"\balways\s+works\b", re.IGNORECASE),
]


def _matches_structured_form(ac: str) -> bool:
    """Return True if the AC matches any accepted structured form."""
    stripped = ac.strip()
    return any(pattern.match(stripped) for _, pattern in _AC_FORMS)


def _detect_bare_verb(ac: str) -> str | None:
    """Return a description of the bare-verb issue if found, else None."""
    for pattern in _BARE_VERB_PATTERNS:
        if pattern.search(ac):
            return f"bare verb pattern detected: {pattern.pattern!r}"
    return None


def _detect_unbounded_quantifier(ac: str) -> str | None:
    """Return a description of the unbounded-quantifier issue if found, else None."""
    for pattern in _UNBOUNDED_QUANTIFIER_PATTERNS:
        if pattern.search(ac):
            return f"unbounded quantifier detected: {pattern.pattern!r}"
    return None


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass
class AmbiguityIssue:
    """One ambiguity finding for a single acceptance criterion."""

    ac_index: int
    criterion: str
    reason: str


@dataclass
class FeatureLintResult:
    """Ambiguity lint result for a single feature."""

    feature_name: str
    issues: list[AmbiguityIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0


@dataclass
class SpecLintReport:
    """Aggregate ambiguity lint report for an entire spec."""

    feature_results: list[FeatureLintResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.feature_results)

    @property
    def failed_features(self) -> list[FeatureLintResult]:
        return [r for r in self.feature_results if not r.passed]

    def format_report(self) -> str:
        """Return a human-readable structured report."""
        if self.passed:
            return "Spec ambiguity lint: PASSED (no ambiguous acceptance criteria found)"

        lines = ["Spec ambiguity lint: FAILED", ""]
        for result in self.failed_features:
            lines.append(f"Feature: {result.feature_name!r}")
            for issue in result.issues:
                lines.append(
                    f"  AC[{issue.ac_index}] {issue.criterion!r}: {issue.reason}"
                )
            lines.append("")
        return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Core linting logic
# ---------------------------------------------------------------------------

def lint_feature(
    feature_name: str,
    acceptance_criteria: list[str],
) -> FeatureLintResult:
    """Lint a single feature's acceptance criteria for ambiguity.

    Parameters
    ----------
    feature_name:
        The name of the feature being linted.
    acceptance_criteria:
        List of acceptance criterion strings.

    Returns
    -------
    FeatureLintResult
        Contains all ambiguity issues found. ``result.passed`` is True
        if no ambiguous criteria were found.
    """
    result = FeatureLintResult(feature_name=feature_name)

    # Zero-AC boundary: a feature with no ACs is unverifiable — fail it.
    if not acceptance_criteria:
        result.issues.append(AmbiguityIssue(
            ac_index=0,
            criterion="",
            reason="boundary failure: feature has zero acceptance criteria — no measurable outcome",
        ))
        return result

    for idx, ac in enumerate(acceptance_criteria):
        stripped = ac.strip()

        if not stripped:
            result.issues.append(AmbiguityIssue(
                ac_index=idx,
                criterion=stripped,
                reason="empty criterion — no measurable outcome",
            ))
            continue

        # Check if it matches a structured form first.
        if _matches_structured_form(stripped):
            continue

        # Not a structured form — check for specific ambiguity patterns.
        bare_verb_reason = _detect_bare_verb(stripped)
        unbounded_reason = _detect_unbounded_quantifier(stripped)

        reasons = []
        if bare_verb_reason:
            reasons.append(bare_verb_reason)
        if unbounded_reason:
            reasons.append(unbounded_reason)

        if not reasons:
            # No specific pattern matched and not a structured form —
            # reject as missing concrete identifier.
            reasons.append(
                "does not match any accepted AC form: "
                "'File exists: <path>', 'Function defined: <dotted.path>', "
                "'Class defined: <dotted.path>', 'pytest: <test_path>', "
                "'integration: <dotted.module>', or "
                "'behavior: <subject> <verb> <object> when <condition>'"
            )

        result.issues.append(AmbiguityIssue(
            ac_index=idx,
            criterion=stripped,
            reason="; ".join(reasons),
        ))

    return result


def is_ambiguous_ac(ac: str) -> bool:
    """Return True if the AC contains bare verb patterns indicating vagueness.

    Checks for bare verbs like "works", "handles", "supports" that appear
    without a structured form prefix, indicating the AC is too vague.
    """
    stripped = ac.strip()
    if _matches_structured_form(stripped):
        return False
    if _detect_bare_verb(stripped) is not None:
        return True
    return False


def has_concrete_identifier(ac: str) -> bool:
    """Return True if the AC contains a concrete identifier (file path, function name, test path).

    Returns False when no file path, function name, or test path is present.
    Structured AC forms inherently have concrete identifiers.
    """
    stripped = ac.strip()
    if not stripped:
        return False
    if _matches_structured_form(stripped):
        return True
    # Check for path-like patterns (e.g. src/bob3/foo.py, tests/test_bar.py)
    if re.search(r'\b\w+/\w+[\w./]*\.py\b', stripped):
        return True
    # Check for dotted module paths (e.g. bob3.module.function)
    if re.search(r'\b[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*){2,}\b', stripped):
        return True
    return False


def format_remediation_report(
    feature_results: list[FeatureLintResult],
) -> dict[str, list[int]]:
    """Return a remediation report dict keyed by feature name with ac_index lists.

    Parameters
    ----------
    feature_results:
        List of FeatureLintResult objects from lint_feature calls.

    Returns
    -------
    dict[str, list[int]]
        Keys are feature names (feature_id); values are lists of AC indices
        that have ambiguity issues. Only features with issues are included.
    """
    report: dict[str, list[int]] = {}
    for result in feature_results:
        if not result.passed:
            report[result.feature_name] = [issue.ac_index for issue in result.issues]
    return report


def lint_spec(
    features: list[dict[str, Any]] | str,
) -> SpecLintReport:
    """Lint an entire spec's features for ambiguous acceptance criteria.

    Parameters
    ----------
    features:
        List of feature dicts, each with at least 'name' and
        'acceptance_criteria' keys. The acceptance_criteria value may be
        a list of strings or a single string (treated as one criterion).

    Returns
    -------
    SpecLintReport
        Aggregate report. ``report.passed`` is True if no feature has
        ambiguous criteria. Use ``report.format_report()`` to get a
        human-readable structured report naming offending features and
        AC indices.

    Raises
    ------
    ValueError
        If ``features`` is a string that cannot be parsed as valid YAML,
        or if the parsed YAML is not a list. Message will contain "malformed".
    """
    # Accept a YAML string as input — parse it first.
    if isinstance(features, str):
        try:
            parsed = yaml.safe_load(features)
        except yaml.YAMLError as exc:
            raise ValueError(f"malformed YAML input: {exc}") from exc
        if parsed is None:
            raise ValueError("malformed YAML input: parsed to None (empty document)")
        if not isinstance(parsed, list):
            raise ValueError(
                f"malformed YAML input: expected a list of features, got {type(parsed).__name__}"
            )
        features = parsed

    report = SpecLintReport()

    for feature in features:
        name = feature.get("name") or feature.get("title") or "(unnamed feature)"
        ac_raw = feature.get("acceptance_criteria") or []

        # Normalise to list[str].
        if isinstance(ac_raw, str):
            criteria: list[str] = [ac_raw]
        elif isinstance(ac_raw, list):
            criteria = [str(c) for c in ac_raw]
        else:
            criteria = []

        feature_result = lint_feature(name, criteria)
        report.feature_results.append(feature_result)

    return report
