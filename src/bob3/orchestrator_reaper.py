"""Orchestrator reaper — final sweep of orphan 'executing' rows on orchestrator exit.

Public entry point:

    finalize_orphans_on_exit(project_id)

Must be called immediately before _run_locked returns its LoopTermination on
ALL_BLOCKED or BUDGET_EXCEEDED terminations.  Delegates to
bob3.orchestrator.run_loop._final_exit_sweep which performs the full two-step
sweep: invoke sweep_orphan_subagents then flip any remaining orphan 'executing'
rows to 'failed' with reason 'orchestrator_exit_during_execution'.

The sweep is idempotent and safe — the same reaper logic that runs in the main
loop tick.

Stale-bytecode integration: before sweeping orphans, the reaper checks whether
any orchestrator source file under src/bob*/orchestrator/ was modified after the
bob_N process started. If stale bytecode is detected, the process must be
killed and relaunched so the updated source takes effect — even when the DB
looks recoverable. See bob3.orchestrator.stale_bytecode_guard.check_stale_bytecode.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)


def _get_check_stale_bytecode():
    from bob3.orchestrator.stale_bytecode_guard import check_stale_bytecode  # noqa: PLC0415
    return check_stale_bytecode


def finalize_orphans_on_exit(project_id: str) -> None:
    """Flip orphan 'executing' rows to 'failed' immediately before LoopTermination returns.

    Invokes the final exit sweep from bob3.orchestrator.run_loop which:

    1. Calls sweep_orphan_subagents() — the same reaper as the main-loop tick —
       to reap PID entries for features already in terminal states.
    2. Queries all features in status='executing' for the project.
    3. For each, checks whether a live PID is still attached. If none, flips
       status to 'failed' with
       last_improvement_type='orchestrator_exit_during_execution'.

    The sweep is idempotent: a second call with the same DB state produces zero
    additional writes.  Per-feature errors are caught and logged; the sweep
    continues to the remaining rows so a single broken row never aborts cleanup.

    Args:
        project_id: UUID of the project whose orphan executing rows to sweep.
                    Must be a non-empty string.

    Raises:
        ValueError: If project_id is None or not a string (propagated from
                    the underlying implementation).
    """
    from bob3.orchestrator.run_loop import _final_exit_sweep  # noqa: PLC0415

    _final_exit_sweep(project_id)


def check_stale_bytecode_before_reap(
    workspace: pathlib.Path,
    start_time: float,
) -> list[pathlib.Path]:
    """Return stale orchestrator .py files detected before reaping orphan rows.

    Wrapper around bob3.orchestrator.stale_bytecode_guard.check_stale_bytecode
    that may be called by the reaper before sweeping orphan executing rows.
    If stale files are found, the orchestrator should kill+relaunch the process
    rather than attempting in-process recovery from a stale bytecode state.

    Args:
        workspace: Root of the bob generation directory.
        start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        List of stale .py paths, or [] if none detected.
    """
    check_stale_bytecode = _get_check_stale_bytecode()
    return check_stale_bytecode(workspace, start_time)
