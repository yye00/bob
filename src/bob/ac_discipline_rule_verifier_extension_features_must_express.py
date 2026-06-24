"""AC discipline rule: verifier-extension features MUST express ACs as structural + integration pytest only.

Enforces the rule (F-2b0d6c5b / companion to F-R7-592) that features whose primary diff
target is a verifier-extension module cannot carry behavior ACs — the running verifier
cannot check patterns it doesn't yet know.  All ACs for such features MUST be either:
  - structural  ("file X contains regex/literal Y")
  - integration pytest ("pytest tests/test_X.py::test_Y passes")

Delegates to bob.spec_quality.spec_extractor.filter_behavior_acs_for_verifier_extension
for the actual enforcement logic.
"""

from __future__ import annotations

from bob.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
)


def ac_discipline_rule_verifier_extension_features_must_express(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Enforce AC discipline for verifier-extension features.

    When *primary_diff_target* resolves to a VERIFIER_EXTENSION_MODULES path,
    every AC line starting with 'behavior:' is demoted to a skip-with-note and
    a WARNING is emitted.  Non-verifier-extension features pass through unchanged.

    Parameters
    ----------
    acceptance_criteria:
        List of raw AC strings.
    primary_diff_target:
        The primary file/module this feature changes.
    feature_id:
        Optional feature identifier for log context.

    Returns
    -------
    ACFilterResult
        filtered_acs: AC list with behavior ACs replaced by skip-with-note strings.
        demoted: list of DemotedAC records (one per removed behavior AC).
        is_verifier_extension: True when the primary_diff_target matched.
    """
    return filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


__all__ = [
    "ac_discipline_rule_verifier_extension_features_must_express",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
