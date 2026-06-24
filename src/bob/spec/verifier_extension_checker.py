"""AC discipline checker for verifier-extension features.

Features whose primary diff target is a verifier-extension module MUST NOT
carry behavior ACs — the running verifier cannot check patterns it doesn't yet
know. All ACs for such features MUST be either:
  - structural  ("file X contains regex/literal Y")
  - integration pytest ("pytest tests/test_X.py::test_Y passes")

This module exposes reject_behavior_ac_for_verifier_extension as the canonical
entry point for enforcing that rule at spec-extraction time.
"""

from __future__ import annotations

from bob.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
)


def reject_behavior_ac_for_verifier_extension(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    When *primary_diff_target* matches a VERIFIER_EXTENSION_MODULES path, every
    AC line starting with 'behavior:' is rejected — replaced with a skip-with-note
    string — and a WARNING is emitted suggesting the structural or integration
    pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings extracted from the spec. Must be a list.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier for log context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per rejected behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.

    Raises
    ------
    ValueError
        If *acceptance_criteria* is not a list.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )
    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


__all__ = [
    "reject_behavior_ac_for_verifier_extension",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
