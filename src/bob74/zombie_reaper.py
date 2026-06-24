"""Zombie sub_agent_runs reaper — close 'running' rows whose target feature is terminal.

sub_agent_runs.status='running' rows can outlive the actual subagent process
when the R9-001 update-before-unwind path is bypassed (SIGKILL, OOM, container
restart). Example: row 7fbefda3 stayed 'running' for 14+ hours while its target
feature 590b9008 had been 'completed' since 07:26 local.

This module joins sub_agent_runs against features and marks any 'running' row
whose target_id points to a feature in a terminal state as status='timeout' with
a completion timestamp. Without this, cost/duration telemetry is permanently
skewed and audit queries surface phantom in-flight work.

Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.

Public API
----------
reap_running_subagent_rows(project_id)
    Close all 'running' sub_agent_runs whose target feature is already in a
    terminal state. Returns list of reaped run IDs.
"""

from __future__ import annotations

from bob.orchestrator.zombie_run_reaper import scan_and_reap


def reap_running_subagent_rows(project_id: str) -> list[str]:
    """Close 'running' sub_agent_run rows whose target feature is already terminal.

    Joins sub_agent_runs (status='running') against features and marks any row
    whose target_id references a feature in a terminal state as status='timeout'
    with a completion timestamp.

    Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.

    Args:
        project_id: UUID of the project to scan. Must be a non-empty string.

    Returns:
        List of sub_agent_run IDs that were reaped (marked as 'timeout').
    """
    return scan_and_reap(project_id)
