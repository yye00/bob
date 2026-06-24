"""Zombie sub_agent_runs reaper — canonical module for feature 54f2447f.

sub_agent_runs.status='running' rows can outlive the actual subagent process
when the R9-001 update-before-unwind path is bypassed (SIGKILL, OOM, container
restart). Example: row 7fbefda3 stayed 'running' for 14+ hours while its target
feature 590b9008 had been 'completed' since 07:26 local.

This module exposes the canonical public API required by the feature's acceptance
criteria under the exact module path bob3.zombie_subruns_reaper.

Public API
----------
reap_zombie_subruns(project_id)
    Find and reap all zombie sub_agent_runs for the project. Returns list of
    reaped run IDs. Raises ValueError for invalid project_id (None or empty).

Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.
"""

from __future__ import annotations

from bob3.orchestrator.zombie_run_reaper import scan_and_reap


def reap_zombie_subruns(project_id: str) -> list[str]:
    """Close 'running' sub_agent_run rows whose target feature is already terminal.

    Joins sub_agent_runs (status='running') against features and marks any row
    whose target_id references a feature in a terminal state as status='timeout'
    with a completion timestamp.

    Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.

    Returns:
        List of sub_agent_run IDs that were reaped (marked as 'timeout').

    Raises:
        ValueError: If project_id is None or an empty/whitespace-only string.
    """
    if project_id is None or (isinstance(project_id, str) and not project_id.strip()):
        raise ValueError(
            f"project_id must be a non-empty string, got {project_id!r}"
        )
    return scan_and_reap(project_id)
