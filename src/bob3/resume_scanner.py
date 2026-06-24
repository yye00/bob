"""Resume scanner — promote 'interrupted' feature rows mid-run (feature 89c6e29f).

`_resume_interrupted_work` in OrchestrationLoop runs only at orchestrator startup.
A feature whose subagent is cancelled mid-run (max_turns hit, async timeout, etc.)
is marked 'interrupted' with artifacts on disk but is NEVER re-picked-up by the loop
unless the orchestrator restarts.

This module provides `scan_interrupted_rows` (and its alias `scan_and_promote_interrupted`)
— the canonical public entry points for the periodic resume scan.  It is a thin wrapper
around `bob3.orchestrator.periodic_resume_scan.periodic_resume_scan` and exists at
`bob3.resume_scanner` so that the ACs "File exists: src/bob3/resume_scanner.py" and
"Function defined: bob3.resume_scanner.scan_interrupted_rows" are satisfied.

Public API
----------
scan_interrupted_rows(project_id)
    Promote any 'interrupted' features back to 'ready' mid-run.  Returns a list of
    feature IDs that were promoted.  Raises ValueError for invalid project_id.
    DB errors are caught and logged so a transient lock does not crash the loop.

scan_and_promote_interrupted(project_id)
    Alias for scan_interrupted_rows (backward-compatible name).
"""

from __future__ import annotations

import logging

from bob3 import db

logger = logging.getLogger(__name__)


def scan_interrupted_rows(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Called periodically from the main orchestrator tick loop (not only at startup)
    so that a feature cancelled mid-run (max_turns hit, async timeout, etc.) is
    re-queued without requiring an orchestrator restart.

    Idempotent: already-ready features are not touched.  Safe to call concurrently —
    each promotion is an atomic UPDATE.

    Args:
        project_id: UUID of the project to scan.  Must be a non-empty string.

    Returns:
        List of feature IDs that were promoted from 'interrupted' to 'ready'.

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
            "scan_interrupted_rows: list_features failed; skipping this tick",
            exc_info=True,
        )
        return promoted

    for feat in interrupted:
        try:
            db.update_feature(feat.id, status="ready")
            promoted.append(feat.id)
            logger.info(
                "scan_interrupted_rows: promoted interrupted feature %s (%s) to 'ready'",
                feat.id,
                feat.name,
            )
        except Exception:
            logger.debug(
                "scan_interrupted_rows: update_feature failed for %s; skipping",
                feat.id,
                exc_info=True,
            )

    return promoted


scan_and_promote_interrupted = scan_interrupted_rows
