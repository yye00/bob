"""AC discipline rule for verifier-extension features.

Enforces the rule (companion to F-R7-592) that features whose primary diff
target is a VERIFIER_EXTENSION_MODULES path MUST NOT express behavior ACs.
The running verifier cannot check patterns it does not yet know.

All ACs for verifier-extension features MUST be either:
  - structural  ("file X contains regex/literal Y") — any verifier version can check
  - integration pytest ("pytest tests/test_X.py::test_Y passes") — runs against
    post-change code directly

Enforces at spec-extraction time: reject_behavior_acs_for_extensions() is the
public entry point called by the extractor pipeline when a feature declares a
VERIFIER_EXTENSION_MODULES path as its primary diff target.

Integration: bob.spec_quality.spec_extractor
"""

from __future__ import annotations

import logging

from bob.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
)

logger = logging.getLogger(__name__)


def reject_behavior_acs_for_extensions(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Reject behavior ACs for verifier-extension features at spec-extraction time.

    When *primary_diff_target* includes a path from VERIFIER_EXTENSION_MODULES,
    every AC line starting with 'behavior:' is rejected — replaced with a
    skip-with-note string — and a WARNING is emitted suggesting the structural
    or integration pytest form instead.

    Non-verifier-extension features pass through unchanged.

    Args:
        acceptance_criteria:  List of raw AC strings extracted from the spec.
        primary_diff_target:  The primary file/module this feature changes.
        feature_id:           Optional feature identifier for log context.

    Returns:
        ACFilterResult:
            filtered_acs — AC list with behavior ACs replaced by skip-with-note strings.
            demoted — list of DemotedAC records (one per rejected behavior AC).
            is_verifier_extension — True when the primary_diff_target matched.

    Raises:
        ValueError: If *acceptance_criteria* is not a list.
    """
    if not isinstance(acceptance_criteria, list):
        raise ValueError(
            f"acceptance_criteria must be a list, got {type(acceptance_criteria).__name__!r}"
        )

    result = filter_behavior_acs_for_verifier_extension(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )

    if result.is_verifier_extension and result.demoted:
        logger.warning(
            "AC discipline: %d behavior AC(s) rejected for verifier-extension feature "
            "(primary_diff_target=%r, feature_id=%r). Use structural: or integration: "
            "pytest ... forms instead.",
            len(result.demoted),
            primary_diff_target,
            feature_id,
        )

    return result


def validate_verifier_extension_acs(
    acceptance_criteria: list[str],
    primary_diff_target: str,
    *,
    feature_id: str | None = None,
) -> ACFilterResult:
    """Validate and enforce AC discipline for verifier-extension features.

    Alias for reject_behavior_acs_for_extensions. Enforces the rule that
    features targeting VERIFIER_EXTENSION_MODULES paths MUST NOT express
    behavior ACs — the running verifier cannot check patterns it doesn't yet
    know.

    Args:
        acceptance_criteria:  List of raw AC strings extracted from the spec.
        primary_diff_target:  The primary file/module this feature changes.
        feature_id:           Optional feature identifier for log context.

    Returns:
        ACFilterResult with filtered ACs, demoted list, and extension flag.

    Raises:
        ValueError: If *acceptance_criteria* is not a list.
    """
    return reject_behavior_acs_for_extensions(
        acceptance_criteria,
        primary_diff_target,
        feature_id=feature_id,
    )


__all__ = [
    "reject_behavior_acs_for_extensions",
    "validate_verifier_extension_acs",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
