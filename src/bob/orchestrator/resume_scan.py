"""Periodic resume scan — promote 'interrupted' rows mid-run (87f0d6aa).

Public API
----------
resume_scan(project_id)
    Promote any 'interrupted' features back to 'ready'.  Returns a list of
    feature IDs that were promoted.  Raises ValueError for invalid input.
    DB errors are caught and logged so that a transient lock does not crash
    the main orchestrator loop.
"""

from __future__ import annotations

import logging

from bob import db

logger = logging.getLogger(__name__)


def resume_scan(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Called periodically from the main orchestrator tick loop so that a feature
    cancelled mid-run (max_turns hit, async timeout, etc.) is re-queued without
    requiring an orchestrator restart.

    Idempotent: already-ready features are not touched.  Safe to call
    concurrently — each promotion is an atomic UPDATE.

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
            "resume_scan: list_features failed for project %s; skipping this tick",
            project_id,
            exc_info=True,
        )
        return promoted

    for feat in interrupted:
        try:
            db.update_feature(feat.id, status="ready")
            promoted.append(feat.id)
            logger.info(
                "resume_scan: promoted interrupted feature %s (%s) to 'ready'",
                feat.id,
                feat.name,
            )
        except Exception:
            logger.debug(
                "resume_scan: update_feature failed for %s; skipping",
                feat.id,
                exc_info=True,
            )

    return promoted
