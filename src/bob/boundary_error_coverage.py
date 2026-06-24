"""Boundary/error coverage detection for bob AC sets.

Mirrors the exact word-boundary regexes used by the composite spec_quality scorer
so that injection and scoring decisions never disagree.

Only prose/behaviour ACs are probed — structural lines (File exists, Function
defined, pytest, integration, etc.) are filtered out before pattern matching to
prevent incidental slug tokens (e.g. "failing", "length-capped") from satisfying
coverage when the scorer would not.

Root cause fixed: the original _ensure_boundary_and_error_coverage in
spec_synthesizer.py used naive substring matching over ALL criteria (including
structural lines). A feature whose slug contained a coverage token — e.g.
"failing" (matches "fail"), "length-capped" (matches "limit") — false-tripped
has_error/has_boundary, so the injector SKIPPED adding the AC, yet the composite
scorer (which uses \\b word-boundary regexes and only counts prose ACs, not
structural File-exists/Function-defined lines) still saw 0 coverage → composite
0.0 for 32/118 features.

Fix: detect coverage with the scorer's exact word-boundary regexes, and probe
ONLY the prose/behavior ACs (exclude structural lines whose slugs carry
incidental tokens).
"""

from __future__ import annotations

import re
from typing import Sequence

# Structural AC prefixes that the scorer does not count as prose coverage.
_STRUCTURAL_PREFIX = re.compile(
    r"^\s*(file exists|function defined|class defined|pytest|integration|"
    r"field exists|file modified|ci tests|python)\s*:",
    re.IGNORECASE,
)

# Word-boundary patterns matching the spec_quality scorer's definitions.
_BOUNDARY_RE = re.compile(
    r"\b(empty|null|none|zero|negative|maximum|minimum|max|min|"
    r"boundary|edge case|corner case|overflow|underflow|limit|"
    r"threshold|floor|ceiling)\b",
    re.IGNORECASE,
)

_ERROR_RE = re.compile(
    r"\b(error|exception|fail|invalid|reject|raise|abort|refuse|"
    r"block|does not|cannot|must not|shall not|ValueError|KeyError|"
    r"TypeError|RuntimeError)\b",
    re.IGNORECASE,
)


def is_prose_ac(ac: str) -> bool:
    """Return True if *ac* is a prose/behaviour AC (not a structural line).

    Structural lines (File exists, Function defined, Class defined, pytest,
    integration, field exists, file modified, ci tests, python) return False.
    All other strings — including behavior: ACs — return True.

    Args:
        ac: A single AC string to classify.

    Returns:
        True if the AC is prose/behaviour, False if structural.

    Raises:
        ValueError: If *ac* is not a string.
    """
    if not isinstance(ac, str):
        raise ValueError(
            f"ac must be a str; got {type(ac).__name__!r}: {ac!r}"
        )
    return not bool(_STRUCTURAL_PREFIX.match(ac))


def filter_prose_acs(criteria: Sequence[str]) -> list[str]:
    """Return only the prose/behaviour ACs from *criteria*, filtering structural lines.

    Structural lines (File exists, Function defined, Class defined, pytest,
    integration, field exists, file modified, ci tests, python) are excluded
    because their slugs/paths carry incidental tokens that could false-match
    boundary/error patterns.

    Args:
        criteria: Sequence of AC strings to filter.

    Returns:
        List of prose ACs (non-structural lines), preserving order.

    Raises:
        ValueError: If *criteria* is None or contains non-string elements.
    """
    if criteria is None:
        raise ValueError("criteria must be a sequence of strings, not None")

    prose: list[str] = []
    for ac in criteria:
        if not isinstance(ac, str):
            raise ValueError(
                f"Each criterion must be a str; got {type(ac).__name__!r}: {ac!r}"
            )
        if not _STRUCTURAL_PREFIX.match(ac):
            prose.append(ac)
    return prose


# Canonical public name used by the spec_synthesizer injector and ACs.
get_prose_acs = filter_prose_acs


def ensure_boundary_and_error_coverage(
    criteria: Sequence[str],
) -> tuple[bool, bool]:
    """Return (has_boundary, has_error) for a list of acceptance criteria.

    Detection uses the same word-boundary regexes as the composite
    spec_quality scorer, applied only to prose/behaviour ACs (structural
    lines such as "File exists:", "pytest:", "integration:" are excluded).

    This prevents naive substring matching over slug tokens from false-tripping
    the injector — e.g. a feature slug "failing" must not satisfy error coverage,
    and "length-capped" must not satisfy boundary coverage.

    Args:
        criteria: Sequence of AC strings to inspect.

    Returns:
        A 2-tuple ``(has_boundary, has_error)`` of booleans.

    Raises:
        ValueError: If *criteria* is not a sequence of strings (None or
            non-iterable type is not accepted).
    """
    prose_parts = filter_prose_acs(criteria)
    prose = " ".join(prose_parts)
    has_boundary = bool(_BOUNDARY_RE.search(prose))
    has_error = bool(_ERROR_RE.search(prose))
    return (has_boundary, has_error)


# Legacy alias kept for backward compatibility.
detect_coverage_with_boundaries = ensure_boundary_and_error_coverage

# Canonical public name required by ACs — mirrors scorer's word-boundary logic.
detect_coverage_with_word_boundaries = ensure_boundary_and_error_coverage


def is_prose_criterion(ac: str) -> bool:
    """Return True if *ac* is a prose/behaviour criterion (not a structural line).

    Structural lines (File exists, Function defined, Class defined, pytest,
    integration, field exists, file modified, ci tests, python) return False.
    All other strings — including behavior: ACs — return True.

    This is the canonical name required by the AC:
      Function defined: bob.boundary_error_coverage.is_prose_criterion

    Args:
        ac: A single AC string to classify.

    Returns:
        True if the AC is prose/behaviour, False if structural.

    Raises:
        ValueError: If *ac* is not a string.
    """
    if not isinstance(ac, str):
        raise ValueError(
            f"ac must be a str; got {type(ac).__name__!r}: {ac!r}"
        )
    return not bool(_STRUCTURAL_PREFIX.match(ac))


def detect_coverage_tokens(
    criteria: Sequence[str],
) -> tuple[bool, bool]:
    """Return (has_boundary, has_error) by probing prose ACs with word-boundary regexes.

    Mirrors the exact detection logic used by the composite spec_quality scorer:
    - Only prose/behaviour ACs are probed (structural lines excluded).
    - Word-boundary regexes prevent slug-substring false positives.

    This is the canonical name required by the AC:
      Function defined: bob.boundary_error_coverage.detect_coverage_tokens

    Args:
        criteria: Sequence of AC strings to inspect.

    Returns:
        A 2-tuple ``(has_boundary, has_error)`` of booleans.

    Raises:
        ValueError: If *criteria* is not a sequence of strings (None or
            non-iterable type is not accepted).
    """
    return ensure_boundary_and_error_coverage(criteria)
