"""Status-transition handlers for Bob orchestration (6ff3ca07).

This module provides handlers for special feature statuses that require
custom logic beyond a simple DB update.  Currently implements the
``pending_successor_verify`` handler, which resolves the self-reference
treadmill where verifier-extension features cannot be verified by the
very verifier they are patching.

Public API
----------
handle_pending_successor_verify(feature_id, workspace, structural_ac_passed)
    Transition gate: set ``pending_successor_verify`` status when a feature
    patches a verifier-extension module AND at least one structural AC passed.
    Returns True on success, False otherwise.
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


def handle_pending_successor_verify(
    feature_id: str,
    workspace: "str | os.PathLike[str] | None",
    structural_ac_passed: bool,
) -> bool:
    """Handle the pending_successor_verify status transition for a feature.

    This is the primary handler called by the run_loop when a feature fails
    AC verification but may qualify for successor-gen deferral.  Applies the
    two-condition gate:

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
    """
    logger.debug(
        "status_handlers.handle_pending_successor_verify: feature=%s structural_ac_passed=%s",
        feature_id,
        structural_ac_passed,
    )
    return set_pending_successor_verify(feature_id, workspace, structural_ac_passed)


__all__ = [
    "handle_pending_successor_verify",
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
]
