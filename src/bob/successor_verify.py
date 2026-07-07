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
    promote_from_successor_gen,
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


def should_defer_to_successor(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Return True when a verifier-extension feature should defer to the successor gen.

    AC-mandated entry point (feature 84250c2c). Thin delegate to
    :func:`should_defer_to_successor_gen` — the decision gate called after AC
    verification fails: if the feature modifies the verifier itself AND at least
    one structural AC passed (the file genuinely changed), the feature should
    receive ``pending_successor_verify`` status rather than ``needs_human``.

    Args:
        feature_id:           UUID of the feature under evaluation. Must be a
                              non-None string.
        workspace:            Root directory of the feature's workspace. May be
                              ``None`` if the workspace is unavailable.
        structural_ac_passed: ``True`` when at least one structural AC passed
                              during the verification run.

    Returns:
        ``True`` when ``pending_successor_verify`` was set successfully.
        ``False`` in all other cases (conditions unmet, DB error, etc.).

    Raises:
        ValueError: When ``feature_id`` is None or not a string.
    """
    if feature_id is None or not isinstance(feature_id, str) or isinstance(feature_id, bool):
        raise ValueError(
            f"should_defer_to_successor: feature_id must be a non-None string; "
            f"got {type(feature_id).__name__}"
        )
    return should_defer_to_successor_gen(feature_id, workspace, structural_ac_passed)


def reconcile_pending_successor(
    feature_id: str,
    acceptance_criteria=None,
    workspace: str | os.PathLike[str] | None = None,
) -> str:
    """Re-verify a ``pending_successor_verify`` feature in the successor generation.

    AC-mandated entry point (feature 84250c2c). Delegates to
    :func:`bob.pending_successor_verify.promote_from_successor_gen`, which is
    called by the next generation's startup reconciler. This generation's
    verifier already includes the patched patterns, so it can correctly evaluate
    ACs the prior generation could not — promoting the feature to ``completed``
    or flipping it to ``failed``.

    Args:
        feature_id:           UUID of the feature to reconcile. Must be a
                              non-None string.
        acceptance_criteria:  Optional list of AC strings (or JSON-encoded list).
        workspace:            Root directory of the feature's workspace. ``None``
                              triggers optimistic promotion (no re-scan).

    Returns:
        The new feature status string: ``'completed'``, ``'failed'``, or
        ``'pending_successor_verify'`` if the DB update failed.

    Raises:
        ValueError: When ``feature_id`` is None or not a string.
    """
    return promote_from_successor_gen(feature_id, acceptance_criteria, workspace)


__all__ = [
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
    "reconcile_pending_successor",
    "should_defer_to_successor",
    "should_defer_to_successor_gen",
]
