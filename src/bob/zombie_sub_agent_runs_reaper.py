"""Zombie sub_agent_runs reaper — close 'running' rows whose target feature is terminal.

sub_agent_runs.status='running' rows can outlive the actual subagent process when
the R9-001 update-before-unwind path is bypassed (SIGKILL, OOM, container
restart). Example: row 7fbefda3 (purpose=feature_research, target_id=590b9008)
stayed 'running' for 14+ hours while feature 590b9008 had been 'completed' since
07:26 local. Without reaping, cost/duration telemetry is permanently skewed and
audit queries surface phantom in-flight work.

This module exposes the AC-required public entry point. The scan/find/reap
machinery is shared with ``bob.orchestrator.zombie_run_reaper`` — this wrapper
validates input and delegates to it so there is a single source of truth.

Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.

Public API
----------
reap_zombie_sub_agent_runs(project_id)
    Close all 'running' sub_agent_runs whose target feature is already terminal.
    Returns the list of reaped run IDs. Raises ValueError on empty project_id.
"""

from __future__ import annotations

from bob.orchestrator.zombie_run_reaper import scan_and_reap


def reap_zombie_sub_agent_runs(project_id: str) -> list[str]:
    """Close 'running' sub_agent_run rows whose target feature is already terminal.

    Joins sub_agent_runs (status='running') against features and marks any row
    whose target_id references a feature in a terminal state as status='timeout'
    with a completion timestamp. Runs with a null target_id are skipped.

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.

    Returns:
        List of sub_agent_run IDs that were reaped (marked as 'timeout').

    Raises:
        ValueError: If project_id is None, empty, or whitespace-only.
    """
    if project_id is None or not isinstance(project_id, str) or not project_id.strip():
        raise ValueError(
            f"project_id must be a non-empty string, got {project_id!r}"
        )

    return scan_and_reap(project_id)
