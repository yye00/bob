"""AC discipline rule enforcer for verifier-extension features.

Enforces the rule (companion to F-R7-592): features whose primary diff
target includes a VERIFIER_EXTENSION_MODULES path MUST NOT express behavior
ACs at spec-extraction time. The running verifier cannot check patterns it
does not yet know.

All ACs for verifier-extension features MUST be either:
  - structural  ("file X contains regex/literal Y")
  - integration pytest ("pytest tests/test_X.py::test_Y passes")

Public entry point: reject_behavior_acs_for_verifier_extensions()
"""

from __future__ import annotations

import logging

from bob3.spec_quality.spec_extractor import (
    ACFilterResult,
    DemotedAC,
    VERIFIER_EXTENSION_MODULES,
    filter_behavior_acs_for_verifier_extension,
)

logger = logging.getLogger(__name__)


def reject_behavior_acs_for_verifier_extensions(
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
        ACFilterResult with filtered_acs, demoted list, and is_verifier_extension flag.

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
            "(primary_diff_target=%r, feature_id=%r). Use 'structural:' or "
            "'integration: pytest ...' forms instead.",
            len(result.demoted),
            primary_diff_target,
            feature_id,
        )

    return result


__all__ = [
    "reject_behavior_acs_for_verifier_extensions",
    "ACFilterResult",
    "DemotedAC",
    "VERIFIER_EXTENSION_MODULES",
]
