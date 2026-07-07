"""bob.skip_ratio_gate — bound the skip/xfail ratio so a suite gate is not gameable.

Root cause (hippy/hipsci spec cross-review): a feature proposed gating on
"upstream test-suite pass count ratchets upward, no regressions on
already-passing tests." A reviewer showed the ratchet is gameable — an
attempt-pressured builder maximizes a pass-count / pass-rate / coverage gate by
aggressively marking the HARD tests ``skip``/``xfail`` (a blanket
``NOT_YET_IMPLEMENTED`` reason is a perfect escape hatch): the pass COUNT never
regresses, the gate stays green, and real coverage silently stalls or shrinks.
This generalizes to ANY bob feature that gates on an external/vendored test
suite, a coverage percentage, or a pass-rate — not just the GPU clone.

Fix at extraction (spec-over-code-fix): whenever the synthesizer emits an AC
that gates on a TEST-SUITE pass count, pass rate, or coverage fraction, it MUST
also emit a companion AC that BOUNDS the skip/xfail RATIO (skipped+xfailed over
total collected). Every skip/xfail MUST carry a machine-readable reason from a
fixed taxonomy; untagged skips fail the gate. Deliberately-deferred
OUT_OF_SCOPE tests, counted under a distinct taxonomy reason, do NOT count
against the implementable-skip ratio.

Public API:
  emit_skip_ratio_bound(criteria, title="")      -> list[str]
  classify_skip_reason(reason)                    -> str  (taxonomy tag)
  counts_against_implementable_ratio(tag)         -> bool
  gates_on_suite_metric(criterion)               -> bool
  is_skip_ratio_bound_ac(criterion)              -> bool
  compute_skip_ratio(skipped, xfailed, total)    -> float
  evaluate_skip_ratio(...)                        -> SkipRatioResult
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Fixed skip/xfail reason taxonomy. UNTAGGED is the catch-all for a missing or
# unrecognized reason — it fails the gate (an untagged skip is never allowed).
TAXONOMY: tuple[str, ...] = (
    "NOT_YET_IMPLEMENTED",
    "FLAKY",
    "PLATFORM",
    "EXTERNAL_DEP",
    "OUT_OF_SCOPE",
    "UNTAGGED",
)

# Reasons that are deliberately deferred and therefore do NOT count against the
# implementable-skip ratio.
_NON_IMPLEMENTABLE_TAGS: frozenset[str] = frozenset({"OUT_OF_SCOPE"})

# Default skip/xfail ratio ceiling (skipped+xfailed over total collected).
DEFAULT_SKIP_RATIO_THRESHOLD: float = 0.10

# Ordered (tag, pattern) rules for freeform reason classification. First match
# wins; order matters so specific reasons are matched before broader ones.
_REASON_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OUT_OF_SCOPE", re.compile(r"out[\s_-]*of[\s_-]*scope|deferred|wont[\s_-]*fix|won't[\s_-]*fix", re.I)),
    ("NOT_YET_IMPLEMENTED", re.compile(r"not[\s_-]*yet[\s_-]*implemented|nyi|unimplemented|todo|stub", re.I)),
    ("FLAKY", re.compile(r"flak|intermittent|nondeterministic|non[\s_-]*deterministic|race", re.I)),
    ("PLATFORM", re.compile(r"platform|windows|macos|linux[\s_-]*only|arch|cpu[\s_-]*only|no[\s_-]*gpu|requires[\s_-]*gpu", re.I)),
    ("EXTERNAL_DEP", re.compile(r"external|network|no[\s_-]*internet|missing[\s_-]*dep|requires[\s_-]*service|api[\s_-]*key", re.I)),
)

# Detects an AC that gates on a suite pass-count / pass-rate / coverage fraction.
_SUITE_METRIC_RE = re.compile(
    r"\b("
    r"pass[\s_-]*count|pass[\s_-]*rate|pass[\s_-]*ratio|"
    r"coverage|"
    r"ratchet|"
    r"tests?[\s_-]*pass(ing|ed)?|"
    r"suite[\s_-]*(pass|green)|"
    r"no[\s_-]*regressions?"
    r")\b",
    re.IGNORECASE,
)

# Marker phrase used to recognize (and dedupe) a skip-ratio-bound companion AC.
_BOUND_MARKER_RE = re.compile(r"skip.{0,20}(x?fail).{0,40}ratio|skip/xfail\s+ratio", re.IGNORECASE)


@dataclass(frozen=True)
class SkipRatioResult:
    """Outcome of evaluating an observed skip/xfail ratio against a bound."""

    ratio: float
    threshold: float
    flagged: bool
    baseline_initialized: bool
    baseline_ratio: float | None


def classify_skip_reason(reason: str) -> str:
    """Classify a skip/xfail reason string into a fixed-taxonomy tag.

    A blank or unrecognized reason classifies as ``"UNTAGGED"`` (which fails the
    gate) rather than raising — the caller decides what to do with an untagged
    skip. Both exact taxonomy names and freeform prose are recognized.

    Args:
        reason: the ``skip``/``xfail`` reason string.

    Returns:
        One of :data:`TAXONOMY`.

    Raises:
        ValueError: if *reason* is not a string.
    """
    if not isinstance(reason, str):
        raise ValueError(
            f"classify_skip_reason: reason must be a str, got {type(reason).__name__!r}"
        )
    stripped = reason.strip()
    if not stripped:
        return "UNTAGGED"
    # Exact taxonomy name (case-insensitive) wins immediately.
    upper = re.sub(r"[\s\-]+", "_", stripped.upper())
    if upper in TAXONOMY:
        return upper
    for tag, pattern in _REASON_RULES:
        if pattern.search(stripped):
            return tag
    return "UNTAGGED"


def counts_against_implementable_ratio(tag: str) -> bool:
    """Whether a taxonomy *tag* counts against the implementable-skip ratio.

    Deliberately-deferred OUT_OF_SCOPE tests do not count; every other tag
    (including UNTAGGED, which fails the gate outright) does.

    Args:
        tag: a taxonomy tag, e.g. the return of :func:`classify_skip_reason`.

    Returns:
        ``True`` when the skip counts against the implementable ratio.

    Raises:
        ValueError: if *tag* is not a string.
    """
    if not isinstance(tag, str):
        raise ValueError(
            f"counts_against_implementable_ratio: tag must be a str, got {type(tag).__name__!r}"
        )
    return tag.strip().upper() not in _NON_IMPLEMENTABLE_TAGS


def gates_on_suite_metric(criterion: str) -> bool:
    """Whether *criterion* gates on a suite pass-count / pass-rate / coverage.

    Args:
        criterion: an acceptance-criterion string.

    Returns:
        ``True`` when the AC gates on a test-suite metric that is gameable by
        mass-skipping.

    Raises:
        ValueError: if *criterion* is not a string.
    """
    if not isinstance(criterion, str):
        raise ValueError(
            f"gates_on_suite_metric: criterion must be a str, got {type(criterion).__name__!r}"
        )
    return bool(_SUITE_METRIC_RE.search(criterion))


def is_skip_ratio_bound_ac(criterion: str) -> bool:
    """Whether *criterion* is a skip-ratio-bound companion AC.

    Args:
        criterion: an acceptance-criterion string.

    Returns:
        ``True`` when the AC bounds the skip/xfail ratio.

    Raises:
        ValueError: if *criterion* is not a string.
    """
    if not isinstance(criterion, str):
        raise ValueError(
            f"is_skip_ratio_bound_ac: criterion must be a str, got {type(criterion).__name__!r}"
        )
    return bool(_BOUND_MARKER_RE.search(criterion))


def emit_skip_ratio_bound(criteria: list[str], title: str = "") -> list[str]:
    """Emit a companion skip-ratio-bound AC when any AC gates on a suite metric.

    Whenever *criteria* contains an AC that gates on a suite pass-count / pass-
    rate / coverage fraction, this appends a single companion AC that bounds the
    skip/xfail ratio and requires every skip to carry a taxonomy-tagged reason
    (untagged skips fail the gate). Idempotent: no duplicate bound is added if
    one is already present, and no bound is added when no gating AC exists.

    Args:
        criteria: list of AC strings.
        title: feature title (accepted for signature parity with the boundary/
            error injector; not required for the emitted text).

    Returns:
        A new list; a superset of *criteria* with at most one companion AC
        appended. The input list is never mutated.

    Raises:
        ValueError: if *criteria* is not a list, or any element is not a string.
    """
    if not isinstance(criteria, list):
        raise ValueError(
            f"emit_skip_ratio_bound: criteria must be a list, got {type(criteria).__name__!r}"
        )
    for item in criteria:
        if not isinstance(item, str):
            raise ValueError(
                f"emit_skip_ratio_bound: all criteria must be strings, "
                f"got {type(item).__name__!r}: {item!r}"
            )

    out = list(criteria)
    if any(is_skip_ratio_bound_ac(c) for c in out):
        return out
    if not any(gates_on_suite_metric(c) for c in out):
        return out

    pct = int(round(DEFAULT_SKIP_RATIO_THRESHOLD * 100))
    out.append(
        f"The skip/xfail ratio (skipped+xfailed over total collected) MUST stay "
        f"at or below {pct}%; a batch of new skips/xfails that pushes the ratio "
        f"above the threshold is FLAGGED for human review, every skip/xfail MUST "
        f"carry a machine-readable reason from the fixed taxonomy "
        f"({', '.join(t for t in TAXONOMY if t != 'UNTAGGED')}), and untagged "
        f"skips fail the gate (OUT_OF_SCOPE deferrals do not count against the ratio)."
    )
    return out


def compute_skip_ratio(skipped: int, xfailed: int, total_collected: int) -> float:
    """Compute the skip/xfail ratio (skipped+xfailed over total collected).

    Args:
        skipped: number of skipped tests (>= 0).
        xfailed: number of xfailed tests (>= 0).
        total_collected: total tests collected (>= 0).

    Returns:
        The ratio in ``[0.0, 1.0]``. Zero collected tests yields ``0.0`` (no
        division error).

    Raises:
        ValueError: if any count is not an int, is negative, or if
            ``skipped + xfailed`` exceeds ``total_collected``.
    """
    for name, val in (("skipped", skipped), ("xfailed", xfailed), ("total_collected", total_collected)):
        if not isinstance(val, int) or isinstance(val, bool):
            raise ValueError(f"compute_skip_ratio: {name} must be an int, got {type(val).__name__!r}")
        if val < 0:
            raise ValueError(f"compute_skip_ratio: {name} must be >= 0, got {val}")
    if skipped + xfailed > total_collected:
        raise ValueError(
            f"compute_skip_ratio: skipped+xfailed ({skipped + xfailed}) "
            f"exceeds total_collected ({total_collected})"
        )
    if total_collected == 0:
        return 0.0
    return (skipped + xfailed) / total_collected


def evaluate_skip_ratio(
    skipped: int,
    xfailed: int,
    total_collected: int,
    baseline_ratio: float | None = None,
    threshold: float = DEFAULT_SKIP_RATIO_THRESHOLD,
) -> SkipRatioResult:
    """Evaluate an observed skip/xfail ratio against a baseline and threshold.

    A first run with no prior baseline (``baseline_ratio is None``) initializes
    the baseline cleanly and never flags. Once a baseline exists, the run is
    flagged when the observed ratio exceeds the max of the threshold and the
    baseline — a batch of new skips that pushes the ratio up is caught.

    Args:
        skipped: number of skipped tests.
        xfailed: number of xfailed tests.
        total_collected: total tests collected.
        baseline_ratio: prior ratio, or ``None`` for a first run.
        threshold: ratio ceiling in ``[0.0, 1.0]``.

    Returns:
        A :class:`SkipRatioResult`.

    Raises:
        ValueError: on invalid counts (see :func:`compute_skip_ratio`), or if
            *baseline_ratio* / *threshold* is out of ``[0.0, 1.0]``.
    """
    ratio = compute_skip_ratio(skipped, xfailed, total_collected)
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValueError(f"evaluate_skip_ratio: threshold must be a number, got {type(threshold).__name__!r}")
    if not 0.0 <= float(threshold) <= 1.0:
        raise ValueError(f"evaluate_skip_ratio: threshold must be in [0.0, 1.0], got {threshold}")
    if baseline_ratio is not None:
        if not isinstance(baseline_ratio, (int, float)) or isinstance(baseline_ratio, bool):
            raise ValueError(
                f"evaluate_skip_ratio: baseline_ratio must be a number or None, "
                f"got {type(baseline_ratio).__name__!r}"
            )
        if not 0.0 <= float(baseline_ratio) <= 1.0:
            raise ValueError(f"evaluate_skip_ratio: baseline_ratio must be in [0.0, 1.0], got {baseline_ratio}")

    if baseline_ratio is None:
        return SkipRatioResult(
            ratio=ratio,
            threshold=float(threshold),
            flagged=False,
            baseline_initialized=True,
            baseline_ratio=ratio,
        )
    ceiling = max(float(threshold), float(baseline_ratio))
    return SkipRatioResult(
        ratio=ratio,
        threshold=float(threshold),
        flagged=ratio > ceiling,
        baseline_initialized=False,
        baseline_ratio=float(baseline_ratio),
    )


__all__ = [
    "TAXONOMY",
    "DEFAULT_SKIP_RATIO_THRESHOLD",
    "SkipRatioResult",
    "classify_skip_reason",
    "counts_against_implementable_ratio",
    "gates_on_suite_metric",
    "is_skip_ratio_bound_ac",
    "emit_skip_ratio_bound",
    "compute_skip_ratio",
    "evaluate_skip_ratio",
]
