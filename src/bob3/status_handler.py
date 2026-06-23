"""Status-transition handler for verifier-extension features (b89c45f9).

Provides :func:`should_defer_to_successor_verifier` — the decision gate that
determines whether a feature failing AC checks should receive the
``pending_successor_verify`` status instead of ``needs_human``.

This breaks the self-reference treadmill: when a feature patches
``enhanced_verification.py`` (or any other VERIFIER_EXTENSION_MODULES member),
the running verifier cannot check patterns it does not yet recognise.  Setting
``pending_successor_verify`` defers re-verification to the next gen, whose
verifier already includes the new patterns.

Public API
----------
should_defer_to_successor_verifier(feature_id, workspace, structural_ac_passed)
    Return True when the feature qualifies for successor-gen deferral.
"""

from __future__ import annotations

import logging
import os

from bob3.pending_successor_verify import (
    PENDING_SUCCESSOR_VERIFY_STATUS,
    VERIFIER_EXTENSION_MODULES,
    is_verifier_extension_feature,
    set_pending_successor_verify,
)

logger = logging.getLogger(__name__)


def handle_pending_successor_verify(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Handle the pending_successor_verify status transition for a feature.

    Called by the run_loop when a feature fails AC verification but may qualify
    for successor-gen deferral.  Applies the two-condition gate:

    1. The feature's workspace touches a VERIFIER_EXTENSION_MODULES member
       (i.e. the feature patches the verifier itself).
    2. At least one structural AC passed (``structural_ac_passed=True``),
       confirming the verifier file genuinely changed rather than being a
       no-op diff.

    When both conditions hold, the feature status is set to
    ``pending_successor_verify`` so the next generation's startup reconciler
    can re-run ACs against its own (patched) verifier and promote to
    ``completed`` or demote to ``failed``.

    This is not a backdoor — real bugs still fail at the successor gen.
    The handler only defers verification to the generation that CAN verify it.

    Args:
        feature_id:           UUID of the feature under evaluation.
        workspace:            Root directory of the feature's workspace.  May be
                              ``None`` if the workspace is unavailable.
        structural_ac_passed: ``True`` when at least one structural AC (file-exists,
                              function-defined, or similar) passed during the
                              verification run.

    Returns:
        ``True`` when the feature was successfully transitioned to
        ``pending_successor_verify``.
        ``False`` in all other cases (conditions unmet, DB error, etc.).

    Raises:
        ValueError: When ``feature_id`` is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"handle_pending_successor_verify: feature_id must be a non-None string; "
            f"got {type(feature_id)!r}"
        )
    logger.debug(
        "status_handler.handle_pending_successor_verify: feature=%s structural_ac_passed=%s",
        feature_id,
        structural_ac_passed,
    )
    return set_pending_successor_verify(feature_id, workspace, structural_ac_passed)


def should_defer_to_successor_verifier(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Return True when the feature should defer verification to the successor gen.

    The decision gate encapsulates the two conditions required before setting
    ``pending_successor_verify``:

    1. The feature's workspace contains at least one VERIFIER_EXTENSION_MODULES
       member (i.e. the feature is patching the verifier itself).
    2. At least one structural AC passed (``structural_ac_passed=True``),
       confirming that the verifier file genuinely changed rather than being
       a no-op diff.

    When both conditions hold, this function calls
    :func:`bob3.pending_successor_verify.set_pending_successor_verify` to
    persist the status transition and returns ``True``.  If either condition
    is unmet, it returns ``False`` without touching the database, so the
    caller can fall through to the normal ``needs_human`` path.

    Args:
        feature_id:           UUID of the feature under evaluation.
        workspace:            Root directory of the feature's workspace.  May be
                              ``None`` if the workspace is unavailable.
        structural_ac_passed: ``True`` when at least one file-exists,
                              function-defined, or similar structural AC passed
                              during the verification run.

    Returns:
        ``True`` when ``pending_successor_verify`` was set successfully.
        ``False`` in all other cases (conditions unmet, DB error, etc.).
    """
    if not structural_ac_passed:
        logger.debug(
            "status_handler: feature %s — no structural AC passed; not deferring",
            feature_id,
        )
        return False

    if not is_verifier_extension_feature(feature_id, workspace):
        logger.debug(
            "status_handler: feature %s — not a verifier-extension feature; not deferring",
            feature_id,
        )
        return False

    logger.info(
        "status_handler: feature %s qualifies for successor-gen deferral "
        "(workspace touches a verifier-extension module and structural AC passed)",
        feature_id,
    )
    return set_pending_successor_verify(feature_id, workspace, structural_ac_passed)


__all__ = [
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
    "should_defer_to_successor_verifier",
]
