"""Boundary/error coverage detection for bob77 AC sets.

Exposes detect_coverage_with_boundaries — the same word-boundary regex logic
used by the composite spec_quality scorer — so that injection and scoring
decisions never disagree.

Only prose/behaviour ACs are probed.  Structural lines (File exists, Function
defined, pytest, integration, etc.) are filtered out before pattern matching to
prevent incidental slug tokens (e.g. "failing", "length-capped") from satisfying
coverage when the scorer would not.
"""

from __future__ import annotations

from typing import Sequence

from boundary_error_coverage import (
    ensure_boundary_and_error_coverage,
    get_prose_acs,
)


def detect_coverage_with_boundaries(
    criteria: Sequence[str],
) -> tuple[bool, bool]:
    """Return (has_boundary, has_error) for a list of acceptance criteria.

    Detection uses the same word-boundary regexes as the composite
    spec_quality scorer, applied only to prose/behaviour ACs (structural
    lines such as "File exists:", "pytest:", "integration:" are excluded).

    Args:
        criteria: Sequence of AC strings to inspect.

    Returns:
        A 2-tuple ``(has_boundary, has_error)`` of booleans.

    Raises:
        ValueError: If *criteria* is not a sequence of strings (None or
            non-iterable type is not accepted).
    """
    return ensure_boundary_and_error_coverage(criteria)


__all__ = ["detect_coverage_with_boundaries", "get_prose_acs"]
