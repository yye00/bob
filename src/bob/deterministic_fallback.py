"""bob.deterministic_fallback — top-level public module for boundary + error-path AC injection.

Feature: 44b6870f-23a3-4841-9602-88c9ba68bb43

Guarantees that EITHER the LLM synthesis path OR the deterministic fallback
path yields gate-passing ACs.  The composite spec_quality_score is a weighted
geometric mean; boundary_coverage=0 OR error_path_coverage=0 forces the
composite to 0.0 → the feature re-blocks at the 0.85 gate regardless of how
many structural ACs were synthesised.

Root cause it closes:
After F-R7-625 fixed the LLM synthesis path to inject boundary + error-path
ACs, rate-limited features still scored composite 0.0 because Vertex 429 /
RESOURCE_EXHAUSTED caused the synthesiser to fall back to
``deterministic_fallback``, which emitted only 3 structural ACs (File exists /
pytest / Function defined) with NO boundary or error-path AC.

Behaviour contract:
    WHEN any feature's ACs are produced (synthesis OR fallback)
    THEN the result MUST include at least one boundary-condition AC and one
         error-path AC so the composite geometric mean can exceed 0.0.

Public API::

    from bob.deterministic_fallback import ensure_boundary_and_error_coverage
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
        If ``criteria`` is not a list or tuple.
    ValueError
        If any element of ``criteria`` is not a string.
    """
    return _ensure_boundary_and_error_coverage(criteria, title=title)
