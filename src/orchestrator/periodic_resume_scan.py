"""Periodic resume scan — promote 'interrupted' rows mid-run (feature 95d0125a).

Provides ``promote_interrupted_rows`` to be called on every orchestrator tick
so that interrupted features are re-queued without requiring a relaunch.

Public API
----------
promote_interrupted_rows(project_id)
    Promote any 'interrupted' features back to 'ready' mid-run.  Returns a
    list of feature IDs that were promoted.  DB errors are caught and logged
    so that a transient lock does not crash the loop.
"""

from __future__ import annotations

import logging

from bob3 import db

logger = logging.getLogger(__name__)


def promote_interrupted_rows(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Called periodically from the main orchestrator tick loop (not only at
    startup) so that a feature cancelled mid-run (max_turns hit, async
    timeout, etc.) is re-queued without requiring an orchestrator restart.

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.

    Returns:
        List of feature IDs that were promoted from 'interrupted' to 'ready'.

    Raises:
        ValueError: If project_id is None, empty, whitespace-only, or not a string.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError(
            f"project_id must be a non-empty string; got {project_id!r}"
        )

    promoted: list[str] = []
    try:
        interrupted = db.list_features(project_id=project_id, status="interrupted")
    except Exception:
        logger.debug(
            "promote_interrupted_rows: list_features failed; skipping this tick",
            exc_info=True,
        )
        return promoted

    for feat in interrupted:
        try:
            db.update_feature(feat.id, status="ready")
            promoted.append(feat.id)
            logger.info(
                "promote_interrupted_rows: promoted interrupted feature %s (%s) to 'ready'",
                feat.id,
                feat.name,
            )
        except Exception:
            logger.debug(
                "promote_interrupted_rows: update_feature failed for %s; skipping",
                feat.id,
                exc_info=True,
            )

    return promoted
