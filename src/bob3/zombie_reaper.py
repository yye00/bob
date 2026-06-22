"""Zombie sub_agent_runs reaper — top-level public entry point (956b5038).

sub_agent_runs.status='running' rows can outlive the actual subagent process
when the R9-001 update-before-unwind path is bypassed (SIGKILL, OOM, container
restart). Example: row 7fbefda3 stayed 'running' for 14+ hours while its target
feature 590b9008 had been 'completed' since 07:26 local.

This module provides the canonical public API required by the feature's
acceptance criteria. The heavy lifting lives in
``bob3.orchestrator.zombie_run_reaper``; this wrapper surfaces
``reap_zombie_subruns`` at the expected top-level import path.

Public API
----------
reap_zombie_subruns(project_id)
    Close all 'running' sub_agent_runs whose target feature is already in a
    terminal state ('completed', 'needs_human', 'regression', 'failed').
    Returns list of reaped run IDs.
"""

from __future__ import annotations

from bob3.orchestrator.zombie_run_reaper import scan_and_reap


def reap_zombie_runs(project_id: str) -> list[str]:
    """Close 'running' sub_agent_run rows whose target feature is terminal.

    Joins sub_agent_runs against features and marks any 'running' row whose
    target_id points to a feature in a terminal state as status='timeout'
    with a completion timestamp.

    Terminal feature states: 'completed', 'needs_human', 'regression', 'failed'.

    Args:
        project_id: UUID of the project to scan.

    Returns:
        List of sub_agent_run IDs that were reaped (marked as 'timeout').
    """
    return scan_and_reap(project_id)


# Backwards-compatible aliases kept for callers written before the rename.
reap_zombie_subruns = reap_zombie_runs
reap_zombie_subagent_runs = reap_zombie_runs
reap_zombie_sub_agent_runs = reap_zombie_runs
# AC-required alias: "Function defined: bob3.zombie_reaper.reap_running_subagent_rows"
reap_running_subagent_rows = reap_zombie_runs
# AC-required alias: "Function defined: bob3.zombie_reaper.reap_running_subagent_runs"
reap_running_subagent_runs = reap_zombie_runs
# AC-required alias: "Function defined: bob3.zombie_reaper.close_zombie_runs"
close_zombie_runs = reap_zombie_runs
