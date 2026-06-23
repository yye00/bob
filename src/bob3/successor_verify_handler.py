"""Successor-gen verification handoff handler (1e768c51).

Provides the two functions required by the feature AC:

- :func:`should_defer_to_successor_verify` — decision gate: should this feature
  receive ``pending_successor_verify`` status instead of ``needs_human``?
- :func:`promote_successor_verified_features` — reconciler entry: re-verify a
  ``pending_successor_verify`` feature in the successor generation and promote
  to ``completed`` or demote to ``failed``.

Both functions delegate to :mod:`bob3.pending_successor_verify` which owns the
canonical implementation.  This module is a thin named entry point so that the
acceptance criteria ``Function defined: bob3.successor_verify_handler.*`` can
be satisfied without duplicating logic.

Background
----------
Verifier-extension features (those that modify ``enhanced_verification.py`` or
any other ``VERIFIER_EXTENSION_MODULES`` member) form a self-reference treadmill:
the running verifier cannot recognise patterns it does not yet know about, so it
always fails these features in their own generation.  The fix is to set
``pending_successor_verify`` status so the next generation's startup reconciler
can re-run ACs against its now-patched verifier and close them.

This is not a backdoor — real bugs still fail at the successor gen.  The handler
only defers verification to the generation that CAN evaluate the new patterns.
"""

from __future__ import annotations

import logging
import os

from bob3.pending_successor_verify import (
    PENDING_SUCCESSOR_VERIFY_STATUS,
    VERIFIER_EXTENSION_MODULES,
    is_verifier_extension_feature,
    promote_from_successor_gen,
    set_pending_successor_verify,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
    "should_defer_to_successor_verify",
    "promote_successor_verified_features",
]


def should_defer_to_successor_verify(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Return True when a verifier-extension feature should defer to the successor gen.

    Decision gate called by the run_loop after AC verification fails.  If the
    feature modifies the verifier itself AND at least one structural AC passed
    (confirming the file genuinely changed), the feature receives
    ``pending_successor_verify`` status rather than ``needs_human``.

    The successor generation's startup reconciler re-runs the ACs using its own
    (now-patched) verifier and promotes to ``completed`` or flips to ``failed``.

    Conditions for deferral (both must hold):

    1. The feature's workspace contains at least one ``VERIFIER_EXTENSION_MODULES``
       member — i.e. the feature patches the verifier itself.
    2. ``structural_ac_passed`` is ``True`` — at least one structural AC (file-
       exists, function-defined, or similar) passed, confirming the verifier
       file genuinely changed rather than being a no-op diff.

    When both conditions hold, sets the DB status to ``pending_successor_verify``
    via :func:`bob3.pending_successor_verify.set_pending_successor_verify` and
    returns ``True``.  If either condition is unmet, returns ``False`` without
    touching the database so the caller can fall through to ``needs_human``.

    Args:
        feature_id:           UUID of the feature under evaluation.
        workspace:            Root directory of the feature's workspace.  May be
                              ``None`` if the workspace is unavailable.
        structural_ac_passed: ``True`` when at least one structural AC passed
                              during the verification run.

    Returns:
        ``True`` when the feature was successfully set to
        ``pending_successor_verify``.
        ``False`` in all other cases (conditions unmet, DB error, etc.).
    """
    logger.debug(
        "successor_verify_handler.should_defer_to_successor_verify: "
        "feature=%s structural_ac_passed=%s",
        feature_id,
        structural_ac_passed,
    )
    return set_pending_successor_verify(feature_id, workspace, structural_ac_passed)


def promote_successor_verified_features(
    feature_id: str,
    acceptance_criteria=None,
    workspace: str | os.PathLike[str] | None = None,
) -> str:
    """Re-verify a ``pending_successor_verify`` feature in the successor generation.

    Called by the startup reconciler of the next generation.  This generation's
    verifier already includes the patched patterns, so it can correctly evaluate
    ACs that the prior generation's verifier could not.  Promotes the feature to
    ``completed`` when the workspace confirms the verifier-extension is present,
    or flips to ``failed`` when the workspace no longer qualifies.

    On DB error, returns ``'pending_successor_verify'`` unchanged so the next
    generation can retry.

    Args:
        feature_id:           UUID of the feature to promote.  Must be a non-None
                              string; raises ``ValueError`` otherwise.
        acceptance_criteria:  Optional list of AC strings (or JSON-encoded list).
                              Accepted for forward-compatibility; currently passed
                              through to the underlying implementation.
        workspace:            Root directory of the feature's workspace.  ``None``
                              triggers optimistic promotion (no workspace re-scan).

    Returns:
        The new feature status string: ``'completed'``, ``'failed'``, or
        ``'pending_successor_verify'`` if the DB update failed.

    Raises:
        ValueError: When ``feature_id`` is ``None`` or not a string.
    """
    logger.debug(
        "successor_verify_handler.promote_successor_verified_features: feature=%s",
        feature_id,
    )
    return promote_from_successor_gen(feature_id, acceptance_criteria, workspace)
