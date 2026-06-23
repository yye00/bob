"""Boundary/error coverage detection — top-level src/ public API.

Mirrors the exact word-boundary regexes used by the composite spec_quality
scorer so that injection and scoring decisions never disagree.

Only prose/behaviour ACs are probed — structural lines (File exists, Function
defined, pytest, integration, etc.) are filtered out before pattern matching to
prevent incidental slug tokens (e.g. "failing", "length-capped") from satisfying
coverage when the scorer would not.

The bug this fixes: the original _ensure_boundary_and_error_coverage in
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

Integration with ears_criteria: behavior: ACs are identified via the EARS
criterion grammar (ears_criteria.parse_behavior) so they are treated as prose,
not structural, during coverage detection.
"""

from __future__ import annotations

import re
from typing import Sequence

# Import ears_criteria to treat behavior: ACs as prose (they carry real
# descriptive text the scorer counts — not path/slug tokens).
from ears_criteria import parse_behavior  # noqa: F401

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


def get_prose_acs(criteria: Sequence[str]) -> list[str]:
    """Return only the prose/behaviour ACs from *criteria*, filtering structural lines.

    Structural lines (File exists, Function defined, Class defined, pytest,
    integration, field exists, file modified, ci tests, python) are excluded
    because their slugs/paths carry incidental tokens that could false-match
    boundary/error patterns.

    behavior: ACs are kept as prose since the EARS criterion grammar
    (ears_criteria.parse_behavior) treats them as descriptive, not structural.

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


def ensure_boundary_and_error_coverage(
    criteria: Sequence[str],
) -> tuple[bool, bool]:
    """Return (has_boundary, has_error) for a list of acceptance criteria.

    Detection uses the same word-boundary regexes as the composite
    spec_quality scorer, applied only to prose/behaviour ACs (structural
    lines such as "File exists:", "pytest:", "integration:" are excluded).

    behavior: ACs parsed by the EARS grammar (ears_criteria) are included
    in prose detection since they carry real descriptive text.

    Args:
        criteria: Sequence of AC strings to inspect.

    Returns:
        A 2-tuple ``(has_boundary, has_error)`` of booleans.

    Raises:
        ValueError: If *criteria* is not a sequence of strings (None or
            non-iterable type is not accepted).
    """
    prose_parts = get_prose_acs(criteria)
    prose = " ".join(prose_parts)
    has_boundary = bool(_BOUNDARY_RE.search(prose))
    has_error = bool(_ERROR_RE.search(prose))
    return (has_boundary, has_error)
