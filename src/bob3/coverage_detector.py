"""Boundary/error coverage detection for bob3 AC sets.

Mirrors the exact word-boundary regexes used by the composite spec_quality scorer
so that injection and scoring decisions never disagree.

Only prose/behaviour ACs are probed — structural lines (File exists, Function
defined, pytest, integration, etc.) are filtered out before pattern matching to
prevent incidental slug tokens (e.g. "failing", "length-capped") from satisfying
coverage when the scorer would not.
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


def detect_boundary_error_coverage(
    criteria: Sequence[str],
) -> tuple[bool, bool]:
    """Return (has_boundary, has_error) for a list of acceptance criteria.

    Detection uses the same word-boundary regexes as the composite
    spec_quality scorer, applied only to prose/behaviour ACs (structural
    lines such as "File exists:", "pytest:", "integration:" are excluded).

    Args:
        criteria: List of AC strings to inspect.

    Returns:
        A 2-tuple ``(has_boundary, has_error)`` of booleans.

    Raises:
        ValueError: If *criteria* is not a sequence of strings (None or
            non-iterable type is not accepted).
    """
    if criteria is None:
        raise ValueError("criteria must be a sequence of strings, not None")

    prose_parts: list[str] = []
    for ac in criteria:
        if not isinstance(ac, str):
            raise ValueError(
                f"Each criterion must be a str; got {type(ac).__name__!r}: {ac!r}"
            )
        if not _STRUCTURAL_PREFIX.match(ac):
            prose_parts.append(ac)

    prose = " ".join(prose_parts)
    has_boundary = bool(_BOUNDARY_RE.search(prose))
    has_error = bool(_ERROR_RE.search(prose))
    return (has_boundary, has_error)


#: Canonical name alias satisfying AC: Function defined: bob3.coverage_detector.detect_boundary_and_error_coverage
detect_boundary_and_error_coverage = detect_boundary_error_coverage
