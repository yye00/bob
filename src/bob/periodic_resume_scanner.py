"""Periodic resume scanner — promote 'interrupted' rows mid-run, not only at startup.

``_resume_interrupted_work`` in OrchestrationLoop runs only at orchestrator startup.
A feature whose subagent is cancelled mid-run (max_turns hit, async timeout, etc.)
is marked 'interrupted' with artifacts on disk but is NEVER re-picked-up by the loop
unless the orchestrator restarts.

This module exposes ``scan_and_promote_interrupted`` — a top-level function intended
to be called on every orchestrator tick (or a dedicated 60 s timer) so that
interrupted rows are re-queued without requiring a relaunch.

Combined with F-R7-501 (stuck-executing reaper) this eliminates the two paths by
which the orchestrator silently stalls on rows it should re-dispatch.

Public API
----------
scan_and_promote_interrupted(project_id)
    Promote any 'interrupted' features back to 'ready' mid-run.  Returns a list of
    feature IDs that were promoted.  DB errors are caught and logged so that a
    transient lock does not crash the loop.  Raises ValueError for invalid project_id.
"""

from __future__ import annotations

import logging

from bob import db

logger = logging.getLogger(__name__)


def scan_and_promote_interrupted(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Called periodically from the main orchestrator tick loop (not only at startup)
    so that a feature cancelled mid-run (max_turns hit, async timeout, etc.) is
    re-queued without requiring an orchestrator restart.

    Idempotent: already-ready features are not touched.  Safe to call on every
    tick — each promotion is an atomic UPDATE.

    Args:
        project_id: UUID of the project to scan.  Must be a non-empty string.

    Returns:
        List of feature IDs promoted from 'interrupted' to 'ready'.

    Raises:
        ValueError: If *project_id* is not a non-empty string.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError(
            f"project_id must be a non-empty string, got {project_id!r}"
        )

    promoted: list[str] = []
    try:
        interrupted = db.list_features(project_id=project_id, status="interrupted")
    except Exception:
        logger.debug(
            "scan_and_promote_interrupted: list_features failed; skipping this tick",
            exc_info=True,
        )
        return promoted

    for feat in interrupted:
        try:
            db.update_feature(feat.id, status="ready")
            promoted.append(feat.id)
            logger.info(
                "scan_and_promote_interrupted: promoted interrupted feature %s (%s) to 'ready'",
                feat.id,
                feat.name,
            )
        except Exception:
            logger.debug(
                "scan_and_promote_interrupted: update_feature failed for %s; skipping",
                feat.id,
                exc_info=True,
            )

    return promoted
