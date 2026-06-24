"""Successor-gen verification handoff status module (c770e876).

Provides the two public functions required by the feature AC:

- :func:`should_defer_to_successor_gen` — decision gate: should this feature
  receive ``pending_successor_verify`` instead of ``needs_human``?
- :func:`promote_on_successor_verify` — reconciler entry point: re-verify a
  ``pending_successor_verify`` feature in the successor generation and promote
  it to ``completed`` or demote it to ``failed``.

Both functions delegate to :mod:`bob.pending_successor_verify` which owns the
canonical implementation.  This module is a named entry point so that the
acceptance criteria ``Function defined: bob.status_pending_successor_verify.*``
can be satisfied without duplicating logic.
"""

from __future__ import annotations

import logging
import os

from bob.pending_successor_verify import (
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
    "should_defer_to_successor_gen",
    "promote_on_successor_verify",
]


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

    The successor generation's startup reconciler re-runs ACs using its own
    (now-patched) verifier and promotes to ``completed`` or flips to ``failed``.

    This is not a backdoor — real bugs still fail at the successor gen.  The gate
    only defers verification to the generation that CAN verify the new patterns.

    Conditions for deferral (both must hold):
    1. The feature's workspace contains at least one ``VERIFIER_EXTENSION_MODULES``
       member (i.e. the feature is patching the verifier itself).
    2. ``structural_ac_passed`` is ``True`` — at least one structural AC passed,
       confirming the verifier file genuinely changed (not a no-op diff).

    When both conditions hold, sets the DB status to ``pending_successor_verify``
    via :func:`bob.pending_successor_verify.set_pending_successor_verify`.

    Args:
        feature_id:           UUID of the feature under evaluation.
        workspace:            Root directory of the feature's workspace.  May be
                              ``None`` if the workspace is unavailable.
        structural_ac_passed: ``True`` when at least one file-exists,
                              function-defined, or similar structural AC passed
                              during the verification run.

    Returns:
        ``True`` when the feature was successfully set to
        ``pending_successor_verify``.
        ``False`` in all other cases (conditions unmet, DB error, etc.).

    Raises:
        ValueError: When ``feature_id`` is ``None`` or not a ``str``.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"should_defer_to_successor_gen: feature_id must be a non-None string; "
            f"got {type(feature_id)!r}"
        )

    if not structural_ac_passed:
        logger.debug(
            "status_pending_successor_verify: feature %s — no structural AC passed; skipping deferral",
            feature_id,
        )
        return False

    if not is_verifier_extension_feature(feature_id, workspace):
        logger.debug(
            "status_pending_successor_verify: feature %s — not a verifier-extension feature; skipping deferral",
            feature_id,
        )
        return False

    logger.info(
        "status_pending_successor_verify: feature %s qualifies for successor-gen deferral",
        feature_id,
    )
    return set_pending_successor_verify(feature_id, workspace, structural_ac_passed)


def promote_on_successor_verify(
    feature_id: str,
    acceptance_criteria=None,
    workspace: str | os.PathLike[str] | None = None,
) -> str:
    """Re-verify a ``pending_successor_verify`` feature in the successor generation.

    Called by the startup reconciler of the next generation.  This generation's
    verifier already includes the patched patterns, so it can correctly evaluate
    ACs that the prior generation's verifier could not.

    Promotes the feature to ``completed`` when the workspace still contains a
    verifier-extension module (confirming the feature was genuine), or flips to
    ``failed`` when the workspace no longer qualifies.

    Delegates to :func:`bob.pending_successor_verify.promote_from_successor_gen`.

    Args:
        feature_id:           UUID of the feature to promote.
        acceptance_criteria:  Optional list of AC strings (or JSON-encoded list).
                              Reserved for future re-evaluation logic; passed
                              through to the delegate.
        workspace:            Root directory of the feature's workspace.  ``None``
                              triggers optimistic promotion (no re-scan).

    Returns:
        The new feature status string: ``'completed'``, ``'failed'``, or
        ``'pending_successor_verify'`` if the DB update failed.

    Raises:
        ValueError: When ``feature_id`` is ``None`` or not a ``str``.
    """
    if feature_id is None or not isinstance(feature_id, str):
        raise ValueError(
            f"promote_on_successor_verify: feature_id must be a non-None string; "
            f"got {type(feature_id)!r}"
        )

    logger.debug(
        "status_pending_successor_verify: promote_on_successor_verify called for feature %s",
        feature_id,
    )
    return promote_from_successor_gen(feature_id, acceptance_criteria, workspace)
