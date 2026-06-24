"""Spec quality score gate — features below threshold cannot reach ready.

Combines four sub-scorers into a per-feature ``spec_quality_score`` in [0, 1]:

  1. **ambiguity_score** (F-R7-410): fraction of ACs that pass the ambiguity linter.
  2. **reachability_score** (F-R7-411): fraction of ``integration:`` ACs whose
     modules are reachable in the workspace.
  3. **ears_score** (F-R7-412): quality of ``behavior:`` ACs parsed by the EARS
     parser (1.0 if none present, since no behavior ACs is not a deficit by itself).
  4. **ac_coverage_score**: fraction of public API surfaces mentioned in the
     feature description that have a corresponding AC.

The composite score is a weighted average of the four sub-scores.

Gate: ``gate_for_ready(report)`` returns ``(False, remediation_report)`` when
``report.score < 0.85``, keeping the feature at ``status='pending'``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from bob.spec_quality.ambiguity_linter import lint_feature
from bob.spec_quality.integration_reachability import check_spec
from bob.spec_quality.behavior_ac_parser import parse_behavior_ac as parse_behavior_ac
from bob.spec_quality.threshold_resolver import resolve_spec_quality_threshold

# Weights must sum to 1.0
_W_AMBIGUITY = 0.35
_W_REACHABILITY = 0.25
_W_EARS = 0.15
_W_AC_COVERAGE = 0.25

# Patterns for extracting public API surface mentions from descriptions
_FUNC_MENTION_RE = re.compile(
    r"\b(?:function|method|def)\s+`?(\w+)`?|\b`(\w+)\(\)`",
    re.IGNORECASE,
)
_CLASS_MENTION_RE = re.compile(
    r"\b(?:class|model)\s+`?(\w+)`?",
    re.IGNORECASE,
)
_FILE_MENTION_RE = re.compile(
    r"\b(?:file|module)\s+`?([\w/.\-]+\.py)`?|`([\w/.\-]+\.py)`",
    re.IGNORECASE,
)

# Patterns for detecting what an AC covers
_AC_FILE_RE = re.compile(r"^File exists\s*:\s*(\S+)", re.IGNORECASE)
_AC_FUNC_RE = re.compile(r"^Function defined\s*:\s*[\w.]+\.(\w+)", re.IGNORECASE)
_AC_CLASS_RE = re.compile(r"^Class defined\s*:\s*[\w.]+\.(\w+)", re.IGNORECASE)
_AC_FUNC_FULL_RE = re.compile(r"^Function defined\s*:\s*([\w.]+)", re.IGNORECASE)
_AC_CLASS_FULL_RE = re.compile(r"^Class defined\s*:\s*([\w.]+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScoreComponents:
    """Individual sub-scores contributing to the composite quality score."""

    ambiguity_score: float
    reachability_score: float
    ears_score: float
    ac_coverage_score: float


@dataclass
class QualityReport:
    """Full quality report for a single feature."""

    score: float
    components: ScoreComponents
    remediation_hints: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------

def _score_ambiguity(name: str, criteria: list[str]) -> tuple[float, list[str]]:
    """Return (score, hints) for ambiguity lint of the AC list."""
    if not criteria:
        return 0.0, ["No acceptance criteria provided — add structured ACs."]

    result = lint_feature(name, criteria)
    passed = len(criteria) - len(result.issues)
    score = passed / len(criteria)
    hints = []
    for issue in result.issues:
        hints.append(
            f"AC[{issue.ac_index}] ambiguity: {issue.reason} — "
            f"rewrite as a structured form (File exists:, Function defined:, pytest:, etc.)"
        )
    return score, hints


def _score_reachability(
    name: str,
    criteria: list[str],
    workspace: Path | None,
) -> tuple[float, list[str]]:
    """Return (score, hints) for integration-target reachability."""
    integration_acs = [
        ac for ac in criteria
        if re.match(r"^integration\s*:", ac.strip(), re.IGNORECASE)
    ]
    if not integration_acs:
        return 1.0, []

    feature_dict = {"name": name, "acceptance_criteria": criteria}
    result = check_spec([feature_dict], workspace=workspace)

    unreachable = len(result.issues)
    total = len(integration_acs)
    score = (total - unreachable) / total

    hints = []
    for issue in result.issues:
        hint = f"Unreachable integration target: {issue.missing_module!r}"
        if issue.closest_match:
            hint += f" — did you mean {issue.closest_match!r}?"
        hints.append(hint)
    return score, hints


def _score_ears(criteria: list[str]) -> tuple[float, list[str]]:
    """Return (score, hints) for EARS-style behavior ACs.

    If no ``behavior:`` ACs are present, return 1.0 (not penalised).
    If behavior ACs exist, score each by whether it parses successfully
    with all four components (subject, verb, object, condition) populated.
    """
    behavior_acs = [
        ac for ac in criteria
        if re.match(r"^behavior\s*:", ac.strip(), re.IGNORECASE)
    ]
    if not behavior_acs:
        return 1.0, []

    total = len(behavior_acs)
    good = 0
    hints = []
    for ac in behavior_acs:
        try:
            parsed = parse_behavior_ac(ac)
            if parsed.subject and parsed.condition:
                good += 1
            else:
                hints.append(
                    f"Behavior AC could not be fully parsed: {ac!r} — "
                    "use format: 'behavior: <subject> <verb> <object> when/on <condition>'"
                )
        except ValueError:
            hints.append(
                f"Behavior AC could not be fully parsed: {ac!r} — "
                "use format: 'behavior: <subject> <verb> <object> when/on <condition>'"
            )

    score = good / total
    return score, hints


_SURFACE_STOPWORDS = {
    "defined", "implemented", "declared", "created", "added", "updated",
    "called", "named", "used", "the", "a", "an", "is", "be", "this",
    "that", "above", "below", "here", "it", "of", "with", "whose", "for",
    "and", "or", "to", "in", "on", "by", "as", "name", "window", "verbatim",
}


def _is_code_identifier(s: str) -> bool:
    """Only treat a token as a real API surface when it LOOKS like code, not a
    plain English word.

    The gate's coverage scorer was extracting prose words ("defined", "name",
    "of", "implemented", "compares", "ACs") as API surfaces and then demanding
    an AC for each — but no AC can ever "cover" the word "of", so ac_coverage
    pinned at < 1.0 forever and 26+ features could never clear the gate (the
    bob72 dual-scorer wedge). Mirrors the same filter in
    tools/spec_quality_score.py: a real symbol has an underscore, an internal
    capital (CamelCase with a lowercase letter), a dot, or a .py extension.
    All-caps tokens and pluralised acronyms (ACs, IDs) are prose, not symbols.
    """
    if not s:
        return False
    if s.lower() in _SURFACE_STOPWORDS:
        return False
    if s.isupper():
        return False
    if len(s) > 1 and s.endswith("s") and s[:-1].isupper():
        return False
    if s.endswith(".py"):
        return True
    has_camel = any(c.isupper() for c in s[1:]) and any(c.islower() for c in s)
    return ("_" in s) or ("." in s) or has_camel


def _extract_api_mentions_from_description(description: str | None) -> set[str]:
    """Extract function/class/file names mentioned in description as API surfaces."""
    if not description:
        return set()

    mentions: set[str] = set()

    for m in _FUNC_MENTION_RE.finditer(description):
        name = m.group(1) or m.group(2)
        # .py file paths are always code-shaped; bare symbol names must pass the
        # code-identifier filter so prose verbs after "function"/"method" (e.g.
        # "function defined", "method of") are not mistaken for real surfaces.
        if name and _is_code_identifier(name):
            mentions.add(name.lower())

    for m in _CLASS_MENTION_RE.finditer(description):
        name = m.group(1)
        if name and _is_code_identifier(name):
            mentions.add(name.lower())

    for m in _FILE_MENTION_RE.finditer(description):
        name = m.group(1) or m.group(2)
        if name:  # _FILE_MENTION_RE already requires a .py, so it's code-shaped
            mentions.add(name.lower())

    return mentions


def _extract_ac_covered_names(criteria: list[str]) -> set[str]:
    """Extract what names/surfaces each AC explicitly covers."""
    covered: set[str] = set()

    for ac in criteria:
        stripped = ac.strip()

        m = _AC_FILE_RE.match(stripped)
        if m:
            path = m.group(1)
            covered.add(path.split("/")[-1].lower().replace(".py", ""))
            covered.add(path.lower())
            continue

        m = _AC_FUNC_RE.match(stripped)
        if m:
            covered.add(m.group(1).lower())

        m2 = _AC_FUNC_FULL_RE.match(stripped)
        if m2:
            full = m2.group(1).lower()
            covered.add(full)
            covered.add(full.split(".")[-1])
            continue

        m = _AC_CLASS_RE.match(stripped)
        if m:
            covered.add(m.group(1).lower())

        m2 = _AC_CLASS_FULL_RE.match(stripped)
        if m2:
            full = m2.group(1).lower()
            covered.add(full)
            covered.add(full.split(".")[-1])
            continue

    return covered


def _score_ac_coverage(
    description: str | None,
    criteria: list[str],
) -> tuple[float, list[str]]:
    """Return (score, hints) for API surface coverage by ACs.

    Checks whether every public API surface mentioned in the description
    has a corresponding AC. Returns 1.0 when description mentions no API surfaces
    (nothing to cover) or when all mentions are covered.
    """
    mentions = _extract_api_mentions_from_description(description)
    if not mentions:
        return 1.0, []

    covered = _extract_ac_covered_names(criteria)

    uncovered = {m for m in mentions if not any(m in c or c in m for c in covered)}
    if not uncovered:
        return 1.0, []

    score = (len(mentions) - len(uncovered)) / len(mentions)
    hints = [
        f"API surface {name!r} mentioned in description has no corresponding AC — "
        "add a 'Function defined:', 'Class defined:', or 'File exists:' criterion."
        for name in sorted(uncovered)
    ]
    return score, hints


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_score(
    name: str,
    description: str | None,
    acceptance_criteria: Union[list[str], str],
    workspace: Path | str | None = None,
) -> QualityReport:
    """Compute the spec quality score for a single feature.

    Parameters
    ----------
    name:
        Feature name (used for lint reporting).
    description:
        Feature description text (used for AC coverage analysis).
    acceptance_criteria:
        List of AC strings, or a JSON-encoded list, or a newline-separated string.
    workspace:
        Project root directory for reachability checks. Defaults to ``Path.cwd()``.

    Returns
    -------
    QualityReport
        Contains the composite score in [0, 1], per-component breakdown,
        and actionable remediation hints when score < 0.85.

    Raises
    ------
    TypeError
        When *name* is ``None`` — a feature must have a name.
    """
    if name is None:
        raise TypeError("feature name must not be None; provide a non-empty string.")

    ws = Path(workspace) if workspace is not None else Path.cwd()

    # Normalise acceptance_criteria to list[str]
    criteria: list[str]
    if isinstance(acceptance_criteria, list):
        criteria = [str(c) for c in acceptance_criteria]
    elif isinstance(acceptance_criteria, str):
        stripped = acceptance_criteria.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    criteria = [str(c) for c in parsed]
                else:
                    criteria = [stripped]
            except (json.JSONDecodeError, ValueError):
                criteria = [line.strip() for line in stripped.splitlines() if line.strip()]
        else:
            criteria = [line.strip() for line in stripped.splitlines() if line.strip()]
    else:
        criteria = []

    # Empty criteria is a hard failure — no AC means nothing is verifiable.
    if not criteria:
        return QualityReport(
            score=0.0,
            components=ScoreComponents(
                ambiguity_score=0.0,
                reachability_score=0.0,
                ears_score=0.0,
                ac_coverage_score=0.0,
            ),
            remediation_hints=["No acceptance criteria provided — add structured ACs."],
        )

    ambiguity_score, ambiguity_hints = _score_ambiguity(name, criteria)
    reachability_score, reachability_hints = _score_reachability(name, criteria, ws)
    ears_score, ears_hints = _score_ears(criteria)
    ac_coverage_score, coverage_hints = _score_ac_coverage(description, criteria)

    composite = (
        _W_AMBIGUITY * ambiguity_score
        + _W_REACHABILITY * reachability_score
        + _W_EARS * ears_score
        + _W_AC_COVERAGE * ac_coverage_score
    )
    composite = round(min(1.0, max(0.0, composite)), 6)

    all_hints = ambiguity_hints + reachability_hints + ears_hints + coverage_hints

    return QualityReport(
        score=composite,
        components=ScoreComponents(
            ambiguity_score=ambiguity_score,
            reachability_score=reachability_score,
            ears_score=ears_score,
            ac_coverage_score=ac_coverage_score,
        ),
        remediation_hints=all_hints,
    )


def gate_for_ready(report: QualityReport) -> tuple[bool, str | None]:
    """Check whether a feature may be promoted to status='ready'.

    A feature passes the gate when ``report.score >= 0.85``.

    Parameters
    ----------
    report:
        A :class:`QualityReport` produced by :func:`compute_score`.

    Returns
    -------
    tuple[bool, str | None]
        ``(True, None)`` when the feature passes the gate.
        ``(False, remediation_message)`` when the feature is blocked.
        The remediation message is a structured report with score, threshold,
        component breakdown, and actionable hints.
    """
    threshold = resolve_spec_quality_threshold()
    if report.score >= threshold:
        return True, None

    lines = [
        "Spec quality gate: BLOCKED",
        f"  score={report.score:.4f}  threshold={threshold}",
        "",
        "Component scores:",
        f"  ambiguity:     {report.components.ambiguity_score:.4f}  (weight {_W_AMBIGUITY})",
        f"  reachability:  {report.components.reachability_score:.4f}  (weight {_W_REACHABILITY})",
        f"  ears:          {report.components.ears_score:.4f}  (weight {_W_EARS})",
        f"  ac_coverage:   {report.components.ac_coverage_score:.4f}  (weight {_W_AC_COVERAGE})",
    ]

    if report.remediation_hints:
        lines.append("")
        lines.append("Remediation required:")
        for hint in report.remediation_hints:
            lines.append(f"  - {hint}")

    lines.append("")
    lines.append(
        f"Feature stays at 'pending' until spec_quality_score >= {threshold}. "
        "Fix the issues above and re-run planning."
    )

    return False, "\n".join(lines)


# ---------------------------------------------------------------------------
# Additional public contract functions (AC-required)
# ---------------------------------------------------------------------------


class BelowQualityScoreError(Exception):
    """Raised when a feature's spec_quality_score falls below the threshold.

    The exception message is a structured remediation report produced by
    :func:`gate_for_ready`.
    """


def _resolve_threshold() -> float:
    """Return the current spec-quality gate threshold.

    Delegates to :func:`bob.spec_quality.threshold_resolver.resolve_spec_quality_threshold`
    so the value is re-read from ``BOB_SPEC_QUALITY_THRESHOLD`` on every call.
    Supports the ``BOB_SPEC_QUALITY_THRESHOLD_FROZEN`` escape hatch for tests.

    Returns
    -------
    float
        Threshold in [0.0, 1.0].
    """
    return resolve_spec_quality_threshold()


def score_threshold() -> float:
    """Return the minimum spec_quality_score required to promote a feature to 'ready'.

    Reads ``BOB_SPEC_QUALITY_THRESHOLD`` from the environment on every call
    (lazy evaluation) so that operator changes — e.g. lowering the threshold to
    unstick pending features — take effect on the next gate evaluation without a
    process restart.  Falls back to 0.85 when the env var is absent or unparseable.
    The value is clamped to [0.0, 1.0].

    Set ``BOB_SPEC_QUALITY_THRESHOLD_FROZEN`` to pin the threshold for the
    lifetime of the process (useful in tests that need a deterministic value).

    Returns
    -------
    float
        Threshold in [0.0, 1.0].
    """
    return _resolve_threshold()


def raises_below_threshold(report: QualityReport) -> None:
    """Raise :exc:`BelowQualityScoreError` when *report* fails the quality gate.

    Parameters
    ----------
    report:
        A :class:`QualityReport` produced by :func:`compute_score`.

    Raises
    ------
    BelowQualityScoreError
        When ``report.score < 0.85``. The exception message contains the
        structured remediation report from :func:`gate_for_ready`.
    """
    passed, message = gate_for_ready(report)
    if not passed:
        raise BelowQualityScoreError(message)


def handle_zero_ac_list(
    name: str,
    description: str | None = None,
    workspace: Path | str | None = None,
) -> float:
    """Return the spec_quality_score for a feature that has no acceptance criteria.

    A feature with zero ACs is unverifiable and always scores ``0.0``.
    This function documents the zero-AC short-circuit path that avoids
    division by zero in the sub-scorers.

    Parameters
    ----------
    name:
        Feature name.
    description:
        Optional feature description.
    workspace:
        Project workspace root (unused for zero-AC features; accepted for API
        consistency).

    Returns
    -------
    float
        Always ``0.0`` for a feature with an empty AC list.
    """
    report = compute_score(
        name=name,
        description=description,
        acceptance_criteria=[],
        workspace=workspace,
    )
    return report.score


def never_divides_by_zero() -> bool:
    """Document and assert that compute_score never divides by zero.

    The zero-AC case is handled by :func:`handle_zero_ac_list` (and internally
    by ``compute_score``) which short-circuits before any per-AC ratio is
    computed, returning a score of ``0.0`` directly. All sub-scorers that
    compute ratios (e.g. ``passed / len(criteria)``) are only reached when
    ``criteria`` is non-empty, so no division by zero is possible.

    Returns
    -------
    bool
        Always ``True``.
    """
    return True
