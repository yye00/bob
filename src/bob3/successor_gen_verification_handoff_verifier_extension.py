"""Successor-gen verification handoff for verifier-extension features.

When a feature's diff modifies src/bob3/enhanced_verification.py or any module
in VERIFIER_EXTENSION_MODULES, the running verifier cannot validate patterns it
doesn't yet recognize — causing a self-reference treadmill where these features
always NH in their own generation.

This module provides the main entry-point function
``successor_gen_verification_handoff_verifier_extension`` which orchestrates
the status transition: setting the feature to 'pending_successor_verify' so the
next generation's startup reconciler re-runs the ACs with its own (now-patched)
verifier and promotes to 'completed' or flips to 'failed'.

Public API
----------
successor_gen_verification_handoff_verifier_extension(feature_id, workspace, structural_ac_passed)
    Main entry point. Delegates to set_pending_successor_verify. Returns True
    when the status was successfully set to 'pending_successor_verify'.

PENDING_SUCCESSOR_VERIFY_STATUS
    The status string 'pending_successor_verify'.

VERIFIER_EXTENSION_MODULES
    Canonical list of module paths that qualify a feature as a verifier extension.

is_verifier_extension_feature(feature_id, workspace)
    Return True when the feature workspace contains a verifier-extension module.

detect_verification_features(feature_name, acceptance_criteria)
    Return True when any AC body contains a path-token or the title-fallback triggers.
"""

from __future__ import annotations

import logging
import os

from bob3.pending_successor_verify import (
    PENDING_SUCCESSOR_VERIFY_STATUS,
    detect_verification_features,
    is_verifier_extension_feature,
    scan_ac_body_for_tokens,
    set_pending_successor_verify,
)
from bob3.spec_quality.spec_extractor import VERIFIER_EXTENSION_MODULES

logger = logging.getLogger(__name__)


def successor_gen_verification_handoff_verifier_extension(
    feature_id: str,
    workspace: str | os.PathLike[str] | None,
    structural_ac_passed: bool,
) -> bool:
    """Orchestrate the successor-gen verification handoff for verifier-extension features.

    When a feature modifies a verifier-extension module and at least one structural
    AC has passed (confirming the file genuinely changed), this function sets the
    feature status to 'pending_successor_verify'. The next generation's startup
    reconciler re-runs the ACs using its own patched verifier and promotes to
    'completed' or flips to 'failed'.

    This is safe: real bugs still fail at the successor gen. This only defers
    verification to the gen that CAN verify it, breaking the self-reference
    treadmill where verifier-extension features always NH in their own generation.

    Args:
        feature_id:           UUID of the feature to transition.
        workspace:            Root directory of the feature's workspace.
        structural_ac_passed: True when at least one structural AC (file-exists,
                              function-defined, or similar) passed during the
                              verification run.

    Returns:
        True when the status was updated to 'pending_successor_verify'.
        False when either condition is not met or the DB update fails.
    """
    if not structural_ac_passed:
        logger.debug(
            "successor_gen_verification_handoff: feature %s skipped — no structural AC passed",
            feature_id,
        )
        return False

    if not is_verifier_extension_feature(feature_id, workspace):
        logger.debug(
            "successor_gen_verification_handoff: feature %s skipped — not a verifier-extension feature",
            feature_id,
        )
        return False

    result = set_pending_successor_verify(feature_id, workspace, structural_ac_passed)
    if result:
        logger.info(
            "successor_gen_verification_handoff: feature %s deferred to successor-gen verification"
            " (verifier-extension, next gen will re-verify)",
            feature_id,
        )
    return result


__all__ = [
    "PENDING_SUCCESSOR_VERIFY_STATUS",
    "VERIFIER_EXTENSION_MODULES",
    "detect_verification_features",
    "is_verifier_extension_feature",
    "scan_ac_body_for_tokens",
    "successor_gen_verification_handoff_verifier_extension",
]
