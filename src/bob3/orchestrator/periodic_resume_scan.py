"""Periodic resume scan — promote 'interrupted' rows mid-run, not only at startup (f9f35288).

``_resume_interrupted_work`` in OrchestrationLoop runs only at orchestrator startup.
A feature whose subagent is cancelled mid-run (max_turns hit, async timeout, etc.)
is marked 'interrupted' with artifacts on disk but is NEVER re-picked-up by the loop
unless the orchestrator restarts.  Observed: feature d8483d98 (Sticky-completed gate)
had 7 artifact files on disk, sat in 'interrupted' for 30+ min, never advanced.

This module provides ``periodic_resume_scan`` — a module-level function intended to be
called on every orchestrator tick (or a dedicated 60 s timer) so that interrupted rows
are re-queued without requiring a relaunch.

Combined with F-R7-501 (stuck-executing reaper) this eliminates the two paths by which
the orchestrator silently stalls on rows it should re-dispatch.

Public API
----------
periodic_resume_scan(project_id)
    Promote any 'interrupted' features back to 'ready' mid-run.  Returns a list of
    feature IDs that were promoted.  DB errors are caught and logged so that a transient
    lock does not crash the loop.
"""

from __future__ import annotations

import logging

from bob3 import db

logger = logging.getLogger(__name__)


def periodic_resume_scan(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Called periodically from the main orchestrator tick loop (not only at startup)
    so that a feature cancelled mid-run (max_turns hit, async timeout, etc.) is
    re-queued without requiring an orchestrator restart.

    Idempotent: already-ready features are not touched.  Safe to call concurrently —
    each promotion is an atomic UPDATE.

    Args:
        project_id: UUID of the project to scan.

    Returns:
        List of feature IDs that were promoted from 'interrupted' to 'ready'.
    """
    promoted: list[str] = []
    try:
        interrupted = db.list_features(project_id=project_id, status="interrupted")
    except Exception:
        logger.debug(
            "periodic_resume_scan: list_features failed; skipping this tick",
            exc_info=True,
        )
        return promoted

    for feat in interrupted:
        try:
            db.update_feature(feat.id, status="ready")
            promoted.append(feat.id)
            logger.info(
                "periodic_resume_scan: promoted interrupted feature %s (%s) to 'ready'",
                feat.id,
                feat.name,
            )
        except Exception:
            logger.debug(
                "periodic_resume_scan: update_feature failed for %s; skipping",
                feat.id,
                exc_info=True,
            )

    return promoted


scan_and_promote_interrupted = periodic_resume_scan


def run_periodic_resume_scan(project_id: str) -> list[str]:
    """Run the periodic resume scan and return promoted feature IDs.

    Alias for :func:`periodic_resume_scan` that satisfies the
    ``bob3.orchestrator.periodic_resume_scan.run_periodic_resume_scan`` AC.

    Args:
        project_id: UUID of the project to scan.

    Returns:
        List of feature IDs promoted from 'interrupted' to 'ready'.
    """
    return periodic_resume_scan(project_id)
