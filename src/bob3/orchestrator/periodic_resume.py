"""Periodic resume scan — module alias for periodic_resume_scan (feature e072706e).

Provides ``resume_scan`` and ``resume_interrupted_rows`` as canonical entry
points for promoting 'interrupted' feature rows back to 'ready' mid-run,
so that features cancelled mid-run (max_turns hit, async timeout, etc.) are
re-queued without requiring an orchestrator restart.

Public API
----------
resume_scan(project_id)
    Promote any 'interrupted' features back to 'ready'.  Returns a list of
    feature IDs that were promoted.  Raises ValueError for invalid input.
    DB errors are caught and logged so that a transient lock does not crash
    the main orchestrator loop.

resume_interrupted_rows(project_id)
    Alias for resume_scan — promotes 'interrupted' rows to 'ready' mid-run.
    Same signature and semantics as resume_scan.
"""

from __future__ import annotations

from bob3.orchestrator.periodic_resume_scan import periodic_resume_scan as _periodic_resume_scan


def resume_scan(project_id: str) -> list[str]:
    """Promote any 'interrupted' features back to 'ready' mid-run.

    Called periodically from the main orchestrator tick loop so that a feature
    cancelled mid-run (max_turns hit, async timeout, etc.) is re-queued without
    requiring an orchestrator restart.

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
    return _periodic_resume_scan(project_id)


def resume_interrupted_rows(project_id: str) -> list[str]:
    """Promote any 'interrupted' feature rows back to 'ready' mid-run.

    Fires on every orchestrator tick (or a dedicated 60 s timer) so that
    interrupted rows are re-queued without requiring an orchestrator restart.
    Combined with the stuck-executing reaper this eliminates the two paths by
    which the orchestrator silently stalls on rows it should re-dispatch.

    Args:
        project_id: UUID of the project to scan.  Must be a non-empty string.

    Returns:
        List of feature IDs promoted from 'interrupted' to 'ready'.

    Raises:
        ValueError: If *project_id* is not a non-empty string.
    """
    return resume_scan(project_id)


__all__ = ["resume_scan", "resume_interrupted_rows"]
