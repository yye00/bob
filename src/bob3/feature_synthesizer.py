"""bob3.feature_synthesizer — public AC synthesis helpers for feature specs.

Feature: bfa7789d-a524-4330-a3aa-ed808edd9e27

Provides :func:`ensure_boundary_and_error_coverage` as a stable public entry
point so that BOTH the LLM synthesis path and the deterministic fallback path
can guarantee gate-passing ACs.  The composite spec_quality_score is a
weighted geometric mean; a zero boundary_coverage or error_path_coverage sub-
metric collapses the composite to 0.0, re-blocking the feature at the 0.85
gate regardless of how many structural ACs are present.

Public API::

    from bob3.feature_synthesizer import ensure_boundary_and_error_coverage
"""

from __future__ import annotations

from bob3.spec_synthesizer import _ensure_boundary_and_error_coverage


def ensure_boundary_and_error_coverage(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Guarantee boundary_coverage and error_path_coverage sub-metrics are non-zero.

    Delegates to :func:`bob3.spec_synthesizer._ensure_boundary_and_error_coverage`
    so that either the LLM path or the deterministic fallback path produces
    gate-passing ACs.

    Parameters
    ----------
    criteria:
        List of AC strings to check and potentially augment.
    title:
        Feature title used to derive a filesystem-safe slug for injected ACs.

    Returns
    -------
    list[str]
        The original criteria, possibly with boundary and/or error-path ACs
        appended.  Never returns fewer elements than were passed in.

    Raises
    ------
    TypeError
        If ``criteria`` is not a list or tuple.
    ValueError
        If any element of ``criteria`` is not a string.
    """
    return _ensure_boundary_and_error_coverage(criteria, title=title)
