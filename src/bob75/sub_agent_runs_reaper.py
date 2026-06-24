"""bob75 zombie sub_agent_runs reaper — close 'running' rows whose target feature is terminal.

Provides the bob75-namespace surface for the zombie run reaper.

Satisfies ACs:
  - Function defined: bob75.sub_agent_runs_reaper.close_zombie_runs
  - integration: bob.sub_agent_runs_reaper

The heavy logic lives in bob.orchestrator.zombie_run_reaper and
bob.sub_agent_runs_reaper; this module exposes the canonical
``close_zombie_runs`` entry point at the bob75 namespace level.

Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.
"""

from __future__ import annotations

from bob.sub_agent_runs_reaper import reap_zombie_runs  # noqa: F401 — re-exported


def close_zombie_runs(project_id: str) -> list[str]:
    """Close all 'running' sub_agent_run rows whose target feature is already terminal.

    Joins sub_agent_runs (status='running') against features and marks any row
    whose target_id references a feature in a terminal state as status='timeout'
    with a completion timestamp.

    This is the canonical bob75-namespace entry point. Delegates to
    bob.sub_agent_runs_reaper.reap_zombie_runs for the actual work.

    Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.

    Returns:
        List of sub_agent_run IDs that were reaped (marked as 'timeout').

    Raises:
        ValueError: If project_id is None or empty.
    """
    return reap_zombie_runs(project_id)


__all__ = [
    "close_zombie_runs",
    "reap_zombie_runs",
]
