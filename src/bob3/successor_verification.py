"""Successor-gen verification handoff for verifier-extension features (afe52d5b).

When a feature's diff modifies ``src/bob3/enhanced_verification.py`` or any module
listed in VERIFIER_EXTENSION_MODULES, the running verifier cannot validate patterns
it doesn't yet recognize — causing a self-reference treadmill where these features
always NH in their own generation.

This module provides the canonical entry-points for the orchestrator and startup
reconciler to defer and promote verifier-extension features.

The deferral is safe: real bugs still fail at the successor gen. It only defers
verification to the gen that CAN verify the new patterns.

Public API
----------
should_defer_to_successor_gen(feature_id, workspace, structural_ac_passed)
    Decision gate: returns True when the feature qualifies for successor-gen deferral.
    Raises ValueError for None or non-string feature_id.

promote_pending_successor_verify(feature_id, acceptance_criteria, workspace)
    Called by the startup reconciler of the next gen to re-verify deferred features.
    Returns the new status string: 'completed', 'failed', or 'pending_successor_verify'.

set_pending_successor_verify(feature_id, workspace, structural_ac_passed)
    Sets DB status to 'pending_successor_verify'.  Returns True on success.
    Returns False (and never raises) when guard conditions are not met.

PENDING_SUCCESSOR_VERIFY_STATUS
    The canonical status string ``'pending_successor_verify'``.

VERIFIER_EXTENSION_MODULES
    Tuple of module paths that qualify a feature as a verifier extension,
    re-exported from ``bob3.spec_quality.spec_extractor``.
"""

from __future__ import annotations

import logging
import os

from bob3.pending_successor_verify import (
    PENDING_SUCCESSOR_VERIFY_STATUS,
    is_verifier_extension_feature,
    promote_from_successor_gen as _promote_from_successor_gen,
    set_pending_successor_verify as set_pending_successor_verify_impl,
)
from bob3.spec_quality.spec_extractor import VERIFIER_EXTENSION_MODULES

logger = logging.getLogger(__name__)

__all__ = [
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
    "promote_pending_successor_verify",
    "set_pending_successor_verify",
    "should_defer_to_successor_gen",
]


def set_pending_successor_verify(
    feature_id: str | None,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Set status to 'pending_successor_verify' for verifier-extension features.

    Entry point exported as ``bob3.orchestrator.set_pending_successor_verify``.
    Delegates to ``bob3.pending_successor_verify.set_pending_successor_verify``
    after applying input validation guards.

    Guard conditions (both must hold to transition):
    1. ``feature_id`` is a non-empty string.
    2. ``structural_ac_passed`` is truthy — at least one structural AC passed.
    3. The workspace contains a verifier-extension module.

    Args:
        feature_id:           UUID of the feature to transition.  None or
                              non-string values cause an immediate False return.
        workspace:            Root directory of the feature's workspace.
        structural_ac_passed: True when at least one structural AC (file-exists,
                              function-defined, or similar) passed during the
                              verification run.

    Returns:
        True when the status was updated to 'pending_successor_verify'.
        False when any guard condition is not met, input is invalid, or the
        DB update fails.  Never raises.
    """
    if feature_id is None or not isinstance(feature_id, str):
        logger.debug(
            "successor_verification.set_pending_successor_verify: invalid feature_id %r — returning False",
            feature_id,
        )
        return False

    if not structural_ac_passed:
        logger.debug(
            "successor_verification.set_pending_successor_verify: feature %s skipped — no structural AC passed",
            feature_id,
        )
        return False

    return set_pending_successor_verify_impl(feature_id, workspace, structural_ac_passed)


def should_defer_to_successor_gen(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Return True when a verifier-extension feature should defer to the successor gen.

    Decision gate used by the run_loop after AC verification fails: if the feature
    modifies the verifier itself AND at least one structural AC passed (the file
    genuinely changed), it should receive ``pending_successor_verify`` status rather
    than ``needs_human``.

    Conditions for deferral (both must hold):
    1. The feature's workspace contains at least one ``VERIFIER_EXTENSION_MODULES``
       member (i.e. the feature is patching the verifier itself).
    2. ``structural_ac_passed`` is ``True`` — at least one structural AC passed,
       confirming the verifier file genuinely changed (not a no-op diff).

    Args:
        feature_id:           UUID of the feature under evaluation.
        workspace:            Root directory of the feature's workspace.
        structural_ac_passed: True when at least one structural AC passed.

    Returns:
        True when the feature was successfully set to 'pending_successor_verify'.
        False in all other cases (conditions unmet, DB error, etc.).

    Raises:
        ValueError: When ``feature_id`` is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"should_defer_to_successor_gen: feature_id must be a non-None string; "
            f"got {type(feature_id)!r}"
        )

    if not structural_ac_passed:
        logger.debug(
            "successor_verification.should_defer_to_successor_gen: feature %s skipped — no structural AC passed",
            feature_id,
        )
        return False

    return set_pending_successor_verify_impl(feature_id, workspace, structural_ac_passed)


def promote_pending_successor_verify(
    feature_id: str,
    acceptance_criteria=None,
    workspace: str | os.PathLike[str] | None = None,
) -> str:
    """Promote a pending_successor_verify feature in the successor generation.

    Called by the startup reconciler of the next generation to re-verify features
    whose status was deferred because they patched the verifier itself.  The
    successor gen's verifier already includes the patched patterns and can correctly
    evaluate ACs that the prior generation's verifier could not.

    Args:
        feature_id:           UUID of the feature to promote.
        acceptance_criteria:  Optional list of AC strings (reserved for future use).
        workspace:            Root directory of the feature's workspace.  None
                              triggers optimistic promotion (no re-scan).

    Returns:
        The new feature status string: 'completed', 'failed', or
        'pending_successor_verify' if the DB update failed.

    Raises:
        ValueError: When ``feature_id`` is None or not a string.
    """
    return _promote_from_successor_gen(feature_id, acceptance_criteria, workspace)
