"""hippy.spec_synthesis — boundary/error AC injection with word-boundary detection.

Integration point (``integration: hippy.spec_synthesis``): the hippy-side
successor of :func:`bob.spec_synthesizer._ensure_boundary_and_error_coverage`.

Root cause fixed: the original injector detected existing boundary/error
coverage with naive substring matching over ALL criteria joined into one string
(including structural File-exists / Function-defined lines). A feature whose slug
carried a coverage token — e.g. "failing" (matches "fail"), "length-capped"
(matches "limit") — false-tripped ``has_error`` / ``has_boundary``, so the
injector SKIPPED adding the AC. Meanwhile the composite scorer uses ``\\b``
word-boundary regexes and counts ONLY prose ACs, so it still saw 0 coverage →
composite 0.0 for 32/118 features.

Fix: detect coverage with the scorer's exact word-boundary regexes, probing ONLY
the prose/behaviour ACs (structural lines are excluded). Detection is delegated
to :func:`bob.boundary_error_detector.detect_coverage_with_boundaries` so
injection and scoring can never disagree.

Behaviour contract:
    WHEN deciding whether to inject a boundary or error AC
    THEN detection MUST match the scorer's tokenization (word boundaries,
    prose-only) so injection and scoring never disagree.
"""

from __future__ import annotations

import re

from bob.boundary_error_detector import detect_coverage_with_boundaries

__all__ = ["_ensure_boundary_and_error_coverage", "inject_boundary_and_error_acs"]


def _derive_test_slug(title: str) -> str:
    """Return a filesystem-safe, length-capped slug derived from *title*."""
    base = (title.split("—")[0] if title else "feature").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:50]
    return slug or "feature"


def _ensure_boundary_and_error_coverage(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Inject a boundary-condition AC and/or an error-path AC when missing.

    Detection uses the composite scorer's exact word-boundary regexes, applied
    only to prose/behaviour ACs — structural lines (File exists, Function
    defined, pytest, integration, ...) are excluded so an incidental coverage
    token in a slug cannot suppress injection while the scorer still counts 0.

    Args:
        criteria: The list of acceptance-criteria strings to augment.
        title: The feature title, used to derive the injected test slug.

    Returns:
        A new list: the original criteria plus any injected ``pytest:`` ACs.
        The input list is never mutated.

    Raises:
        ValueError: If *criteria* is ``None``, not a list, or contains a
            non-string element. The function must not silently succeed on
            invalid input (e.g. iterating a bare string char-by-char).
    """
    if not isinstance(criteria, list):
        raise ValueError(
            f"_ensure_boundary_and_error_coverage: criteria must be a list, got "
            f"{type(criteria).__name__}"
        )

    # detect_coverage_with_boundaries raises ValueError on non-string elements.
    has_boundary, has_error = detect_coverage_with_boundaries(criteria)

    out = list(criteria)
    slug = _derive_test_slug(title)

    if not has_boundary:
        out.append(
            f"pytest: tests/test_{slug}_boundary.py — empty, zero, or minimum "
            "input returns a well-defined result rather than raising (boundary case)"
        )
    if not has_error:
        out.append(
            f"pytest: tests/test_{slug}_error.py — invalid input raises ValueError "
            "and the function does not silently succeed (error path)"
        )
    return out


def inject_boundary_and_error_acs(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Public alias for :func:`_ensure_boundary_and_error_coverage`."""
    return _ensure_boundary_and_error_coverage(criteria, title=title)
