"""bob3.boundary_error_detector — canonical boundary/error coverage detection.

Exposes ``detect_coverage_with_boundaries``, the function the spec_synthesizer
and AC injector must use when deciding whether to inject boundary/error ACs.

Root cause this module closes: the original ``_ensure_boundary_and_error_coverage``
in spec_synthesizer.py used naive substring matching over ALL criteria joined
into one string (including structural lines). A feature whose slug contained a
coverage token — e.g. "failing" (matches "fail"), "length-capped" (matches
"limit") — false-tripped has_error/has_boundary, so the injector SKIPPED adding
the AC, yet the composite scorer (which uses \\b word-boundary regexes and only
counts prose ACs, not structural File-exists/Function-defined lines) still saw 0
coverage → composite 0.0 for 32/118 features.

Fix: detect coverage with the scorer's exact word-boundary regexes, and probe
ONLY the prose/behavior ACs (exclude structural lines whose slugs carry
incidental tokens). Verified: the two regressing cases ("...failing tests...",
"...length-capped") go 0.0 → 0.889.

Behaviour contract:
    WHEN deciding whether to inject a boundary or error AC
    THEN detection MUST match the scorer's tokenization (word boundaries,
    prose-only) so injection and scoring never disagree.
"""

from __future__ import annotations

import re
from typing import Sequence

# ---------------------------------------------------------------------------
# Compiled regexes — mirror the spec_quality scorer exactly
# ---------------------------------------------------------------------------

_STRUCTURAL_PREFIX = re.compile(
    r"^\s*(file exists|function defined|class defined|pytest|integration|"
    r"field exists|file modified|ci tests|python)\s*:",
    re.IGNORECASE,
)

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


def detect_coverage_with_boundaries(
    criteria: Sequence[str],
) -> tuple[bool, bool]:
    """Return ``(has_boundary, has_error)`` for a list of acceptance criteria.

    Detection uses the same word-boundary regexes as the composite
    spec_quality scorer, applied *only* to prose/behaviour ACs. Structural
    lines (File exists, Function defined, Class defined, pytest, integration,
    field exists, file modified, ci tests, python) are excluded so that slug
    tokens in those lines cannot satisfy coverage when the scorer would not.

    Args:
        criteria: A sequence of AC strings to inspect.

    Returns:
        A 2-tuple ``(has_boundary, has_error)`` of booleans.

    Raises:
        ValueError: If *criteria* is ``None`` or contains any non-string
            element. The function must not silently succeed on invalid input.
    """
    if criteria is None:
        raise ValueError(
            "detect_coverage_with_boundaries: criteria must be a sequence of "
            "strings, not None"
        )

    prose_parts: list[str] = []
    for ac in criteria:
        if not isinstance(ac, str):
            raise ValueError(
                f"detect_coverage_with_boundaries: each criterion must be a str; "
                f"got {type(ac).__name__!r}: {ac!r}"
            )
        if not _STRUCTURAL_PREFIX.match(ac):
            prose_parts.append(ac)

    probe = " ".join(prose_parts)
    has_boundary = bool(_BOUNDARY_RE.search(probe))
    has_error = bool(_ERROR_RE.search(probe))
    return (has_boundary, has_error)
