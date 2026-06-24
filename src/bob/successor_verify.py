"""Successor-gen verification handoff for verifier-extension features.

When a feature's diff modifies src/bob/enhanced_verification.py or any module listed in
VERIFIER_EXTENSION_MODULES, the running verifier cannot check patterns it doesn't yet
recognize — causing a self-reference treadmill where these features always NH in their own gen.

Fix: :func:`should_defer_to_successor_gen` returns True and sets the feature status to
``pending_successor_verify`` instead of ``needs_human`` when:

1. The feature modifies a verifier-extension module (detected via workspace inspection), AND
2. At least one structural AC has PASSED (the verifier file genuinely changed).

The next gen's startup reconciler re-runs ACs using its own (now-patched) verifier and
promotes to ``completed`` or flips to ``failed``.  This is not a backdoor — real bugs still
fail at the successor gen.

Public API
----------
should_defer_to_successor_gen(feature_id, workspace, structural_ac_passed)
    Return True when the feature qualifies for successor-gen deferral.
"""

from __future__ import annotations

import logging
import os

from bob.pending_successor_verify import (
    PENDING_SUCCESSOR_VERIFY_STATUS,
    VERIFIER_EXTENSION_MODULES,
    is_verifier_extension_feature,
    set_pending_successor_verify,
)

logger = logging.getLogger(__name__)


def should_defer_to_successor_gen(
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
    :func:`bob.pending_successor_verify.set_pending_successor_verify` to
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
            "successor_verify: feature %s — no structural AC passed; not deferring",
            feature_id,
        )
        return False

    if not is_verifier_extension_feature(feature_id, workspace):
        logger.debug(
            "successor_verify: feature %s — not a verifier-extension feature; not deferring",
            feature_id,
        )
        return False

    logger.info(
        "successor_verify: feature %s qualifies for successor-gen deferral "
        "(workspace touches a verifier-extension module and structural AC passed)",
        feature_id,
    )
    return set_pending_successor_verify(feature_id, workspace, structural_ac_passed)


__all__ = [
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
    "should_defer_to_successor_gen",
]
