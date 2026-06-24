"""Final reaper sweep — flips orphan 'executing' rows to 'failed' on orchestrator exit.

Public entry point for the feature 3b5fe995 hot-fix:

    sweep_orphans_on_exit(project_id)

Must be called immediately before _run_locked returns its LoopTermination on
ALL_BLOCKED or BUDGET_EXCEEDED terminations.  Delegates to bob.final_reaper
so the two modules stay in sync and there is a single canonical implementation.

The integration point for the orchestrator is:

    from bob.final_reaper_sweep import sweep_orphans_on_exit
    ...
    # immediately before returning LoopTermination
    sweep_orphans_on_exit(project_id)
    return loop_termination
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def sweep_orphans_on_exit(project_id: str) -> list[str]:
    """Sweep orphan executing rows immediately before the orchestrator returns LoopTermination.

    Delegates to bob.final_reaper.sweep_orphans_on_exit which performs the
    full two-step sweep:

    1. Run sweep_orphan_subagents() — the same reaper called in the main loop
       tick — to reap PID entries for features already in terminal states.
    2. Query all features in status='executing' for the project and flip any
       whose subagent PID is gone to status='failed' with
       last_improvement_type='orchestrator_exit_during_execution'.

    The sweep is idempotent: a second call with the same DB state produces zero
    additional writes.  Per-feature errors are caught and logged; the sweep
    continues to the remaining rows so a single broken row never aborts cleanup.

    Args:
        project_id: UUID of the project whose orphan executing rows to sweep.
                    Must be a non-empty string.

    Returns:
        List of feature IDs that were flipped to 'failed'.

    Raises:
        ValueError: If project_id is None or not a string.
    """
    from bob.final_reaper import sweep_orphans_on_exit as _sweep

    return _sweep(project_id)
