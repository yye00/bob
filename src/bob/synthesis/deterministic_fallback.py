"""bob.synthesis.deterministic_fallback — boundary + error-path AC injection.

Ensures that EITHER the LLM synthesis path OR the deterministic fallback path
yields gate-passing ACs. The composite spec_quality_score is a weighted
geometric mean; boundary_coverage=0 OR error_path_coverage=0 forces the
composite to 0.0 → feature re-blocks at the 0.85 gate regardless of how many
structural ACs were synthesised.

This module exposes :func:`ensure_boundary_and_error_coverage` as the
canonical public entry-point under ``bob.synthesis``.  It delegates to
:func:`bob.spec_synthesizer._ensure_boundary_and_error_coverage` which holds
the authoritative implementation so that a single code-path governs both the
LLM and fallback routes.

Public API::

    from bob.synthesis.deterministic_fallback import ensure_boundary_and_error_coverage
"""

from __future__ import annotations

from bob.spec_synthesizer import _ensure_boundary_and_error_coverage


def ensure_boundary_and_error_coverage(
    criteria: list[str],
    title: str = "",
) -> list[str]:
    """Guarantee boundary_coverage and error_path_coverage sub-metrics are non-zero.

    Delegates to the authoritative implementation in
    :func:`bob.spec_synthesizer._ensure_boundary_and_error_coverage` so that
    EITHER the LLM path or the deterministic fallback path produces gate-passing
    ACs.  A single zero sub-metric in the weighted geometric mean drives the
    composite spec_quality_score to 0.0 → the feature re-blocks at the 0.85
    gate even if all structural ACs are present.

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
        If ``criteria`` is not a list.
    ValueError
        If any element of ``criteria`` is not a string (re-raised from the
        underlying implementation on detection).
    """
    return _ensure_boundary_and_error_coverage(criteria, title=title)
