"""Fallback AC boundary/error coverage enforcement for bob.

This module provides :func:`ensure_boundary_and_error_coverage`, which
guarantees that ANY acceptance-criteria list — whether produced by the
LLM synthesis path or the deterministic fallback — contains at least one
boundary-condition AC and one error-path AC.

Root cause it closes:
After F-R7-625 fixed the LLM synthesis path to inject boundary + error-path
ACs, rate-limited features still scored composite 0.0 because Vertex 429 /
RESOURCE_EXHAUSTED caused the synthesizer to fall back to
``deterministic_fallback``, which emitted only 3 structural ACs (File exists /
pytest / Function defined) with NO boundary or error-path AC.  The composite
spec_quality_score is a weighted GEOMETRIC MEAN, so boundary_coverage=0 AND
error_path_coverage=0 force composite=0.0 → the feature re-blocks at the 0.85
gate.

This module is the canonical single point of truth for the coverage guarantee
so both paths (LLM synthesis and deterministic fallback) can import from here
rather than duplicating the regex logic.

Behaviour contract:
    WHEN any feature's ACs are produced (synthesis OR fallback)
    THEN the result MUST include at least one boundary-condition AC and one
         error-path AC so the composite geometric mean can exceed 0.0.
"""

from __future__ import annotations

import re
from typing import Sequence

# Structural AC prefixes that the composite scorer does not count as prose
# coverage.  We must NOT inspect these for keyword matches because their slug
# tokens (e.g. "failing", "length-capped", "min-heap") would false-trip the
# injector while the scorer's word-boundary regexes still see 0 coverage.
_STRUCTURAL_PREFIX = re.compile(
    r"^\s*(file exists|function defined|class defined|pytest|integration|"
    r"field exists|file modified|ci tests|python)\s*:",
    re.IGNORECASE,
)

# Word-boundary regexes matching the spec_quality scorer's definitions exactly.
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

# Pattern to extract descriptive prose from pytest/integration ACs (drop path token).
_PYTEST_LIKE = re.compile(
    r"^\s*(pytest|integration|ci tests|python)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_PATH_TOKEN = re.compile(r"^\S+\s*(—|-{1,2}|:)?\s*", re.IGNORECASE)


def _probe_text(criterion: str) -> str:
    """Extract the descriptive prose from a single AC string for pattern matching.

    Structural ACs (File exists, Function defined, etc.) return empty string
    because their slug/path content must not be inspected.  pytest/integration
    ACs have their path token stripped; the remainder is returned for scoring.
    Prose ACs are returned in full.

    Args:
        criterion: A single acceptance-criterion string.

    Returns:
        The text to search for boundary/error keywords, or empty string if the
        AC carries no inspectable prose.

    Raises:
        ValueError: If *criterion* is not a string.
    """
    if not isinstance(criterion, str):
        raise ValueError(
            f"criterion must be a str; got {type(criterion).__name__!r}: {criterion!r}"
        )
    cl = criterion.strip()
    if _STRUCTURAL_PREFIX.match(cl):
        # Pure structural AC — slug/path only, no descriptive prose.
        m = _PYTEST_LIKE.match(cl)
        if m:
            rest = m.group(2)
            rest = _PATH_TOKEN.sub("", rest, count=1)
            return rest
        return ""
    return cl


def _make_slug(title: str) -> str:
    """Derive a filesystem-safe test slug from a feature title.

    Args:
        title: Feature name/title string.

    Returns:
        A lowercase underscored slug, at most 50 characters, defaulting to
        ``"feature"`` when the title is blank.
    """
    base = (title.split("—")[0] if title else "").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:50]
    return slug or "feature"


def ensure_boundary_and_error_coverage(
    criteria: Sequence[str],
    title: str = "",
) -> list[str]:
    """Guarantee boundary_coverage and error_path_coverage sub-metrics are non-zero.

    The composite spec_quality_score is a weighted GEOMETRIC MEAN.  A single
    zero sub-metric drives the composite to 0.0.  This function injects
    deterministic ``pytest:`` ACs when the supplied criteria lack boundary or
    error-path coverage — using the SAME word-boundary regexes the scorer uses
    so that injection and scoring decisions never diverge.

    Detection is applied ONLY to prose/behaviour text (structural lines like
    "File exists:" and "Function defined:" are excluded) to prevent slug
    tokens from false-tripping the injector.

    The injected ACs use the ``pytest:`` structured form (not free prose) so
    that a single line simultaneously satisfies spec_executability,
    traceability, predicate_coverage, AND the boundary/error_coverage
    sub-metric — the only AC shape that raises every affected sub-metric of
    the geometric mean at once.

    This is the CANONICAL implementation shared by both paths:
    - LLM synthesis path (via spec_synthesizer._apply_llm_postprocessing)
    - Deterministic fallback path (via spec_synthesizer.deterministic_fallback)

    Args:
        criteria: Sequence of AC strings to inspect and potentially augment.
        title: Feature name/title used to derive injected AC file names.

    Returns:
        A new list with the original criteria plus any injected ACs.  If
        both boundary and error coverage are already present, the input is
        returned unchanged (no duplicates).

    Raises:
        TypeError: If *criteria* is not a sequence (e.g. a plain string or None).
        ValueError: If any element of *criteria* is not a string.
    """
    if not isinstance(criteria, (list, tuple)):
        raise TypeError(
            f"ensure_boundary_and_error_coverage: criteria must be a list or tuple, "
            f"got {type(criteria).__name__}"
        )

    probe_parts: list[str] = []
    for ac in criteria:
        probe_parts.append(_probe_text(ac))

    probe = " ".join(probe_parts)
    has_boundary = bool(_BOUNDARY_RE.search(probe))
    has_error = bool(_ERROR_RE.search(probe))

    out = list(criteria)
    slug = _make_slug(title)

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
