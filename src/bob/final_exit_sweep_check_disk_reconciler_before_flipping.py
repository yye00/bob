"""_final_exit_sweep — check disk_reconciler BEFORE flipping orphan-executing to failed (F-R7-598).

Implements the reconciler-before-sweep guard described in the feature spec:

  Before the _final_exit_sweep flips an orphan-executing feature to 'failed',
  it must invoke disk_reconciler.promote_if_acs_satisfied.  If all ACs are
  already satisfied on disk, the feature is atomically promoted to 'completed'
  and the flip-to-failed is skipped.

This module exposes the canonical entry point:
``final_exit_sweep_check_disk_reconciler_before_flipping`` — a pure function
that accepts a list of orphan-executing feature objects and returns a summary
dict with counts of promoted vs. flipped-to-failed outcomes.

Safety invariant: only PROMOTES on disk evidence.  If the disk check fails or
raises, the feature falls through to the existing flip-to-failed path.  No
failure is silenced.
"""

from __future__ import annotations

import logging
from typing import Any

from bob.disk_reconciler import promote_if_acs_satisfied

logger = logging.getLogger(__name__)


def final_exit_sweep_check_disk_reconciler_before_flipping(
    *,
    project_id: str,
    orphan_executing_features: list[Any],
) -> dict[str, int]:
    """Check disk_reconciler for each orphan-executing feature before flipping to failed.

    For each feature in *orphan_executing_features* (features whose subagent
    PID is no longer alive at orchestrator drain time):

    1. Call ``promote_if_acs_satisfied`` with the feature's ACs.
    2. If promotion succeeds → count as promoted, skip the flip-to-failed.
    3. If promotion fails (or raises) → count as flipped_failed.

    Returns
    -------
    dict with keys:
        ``promoted``      — number of features promoted to 'completed' by disk check.
        ``flipped_failed``— number of features that must be flipped to 'failed'.

    The caller is responsible for actually writing the 'failed' status to the
    database for the ``flipped_failed`` features.  This function only performs
    the disk-promotion side.
    """
    promoted = 0
    flipped_failed = 0

    for feature in orphan_executing_features:
        feature_id = feature.id
        feature_name = feature.name
        acceptance_criteria_json = feature.acceptance_criteria

        try:
            disk_promoted = promote_if_acs_satisfied(
                project_id=project_id,
                feature_id=feature_id,
                feature_name=feature_name,
                acceptance_criteria_json=acceptance_criteria_json,
            )
        except Exception:
            logger.debug(
                "final_exit_sweep: promote_if_acs_satisfied raised for feature %s; "
                "falling through to flip-to-failed",
                feature_id,
                exc_info=True,
            )
            disk_promoted = False

        if disk_promoted:
            logger.info(
                '{"event":"FINAL_SWEEP_DISK_PROMOTED","feature_id":"%s"}',
                feature_id,
            )
            promoted += 1
        else:
            flipped_failed += 1

    logger.info(
        '{"event":"FINAL_SWEEP_SUMMARY","promoted":%d,"flipped_failed":%d}',
        promoted,
        flipped_failed,
    )

    return {"promoted": promoted, "flipped_failed": flipped_failed}


__all__ = ["final_exit_sweep_check_disk_reconciler_before_flipping"]
