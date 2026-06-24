"""bob77.zombie_reaper — Zombie sub_agent_runs reaper for the bob77 orchestrator.

sub_agent_runs.status='running' rows can outlive the actual subagent process
when the R9-001 update-before-unwind path is bypassed (SIGKILL, OOM, container
restart). Example: row 7fbefda3 stayed 'running' for 14+ hours while its target
feature 590b9008 had been 'completed' since 07:26 local.

This module provides the canonical public API required by the feature's
acceptance criteria. The heavy lifting lives in
``bob.orchestrator.zombie_run_reaper``; this wrapper surfaces
``reap_zombie_runs`` at the expected top-level import path for bob77.

Without this reaper, cost/duration telemetry is permanently skewed and audit
queries surface phantom in-flight work.

Public API
----------
reap_zombie_runs(project_id)
    Close all 'running' sub_agent_runs whose target feature is already in a
    terminal state ('completed', 'needs_human', 'regression', 'failed').
    Returns list of reaped run IDs.
"""

from __future__ import annotations

from bob.zombie_reaper import (  # noqa: F401 — integration: bob.ac_handler
    reap_zombie_runs,
    reap_zombie_subruns,
    reap_zombie_subagent_runs,
)

__all__ = ["reap_zombie_runs", "reap_zombie_subruns", "reap_zombie_subagent_runs"]
