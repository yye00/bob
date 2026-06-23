"""Zombie sub_agent_runs reaper — close 'running' rows whose target feature is terminal (20cdfb11).

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
find_zombie_runs(project_id)
    Return SubAgentRun rows with status='running' whose target feature is terminal.

reap_zombie_run(run)
    Mark a single zombie run as status='timeout' with completed_at timestamp.

scan_and_reap(project_id)
    Convenience wrapper: find then reap all zombie runs for a project in one call.
    Intended to be called each orchestrator tick.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bob3 import db

if TYPE_CHECKING:
    from bob3.models import SubAgentRun

logger = logging.getLogger(__name__)

_TERMINAL_FEATURE_STATUSES = ("completed", "needs_human", "regression", "failed")


def find_zombie_runs(project_id: str) -> list["SubAgentRun"]:
    """Return sub_agent_runs with status='running' whose target feature is terminal.

    A run is a zombie when:
      - Its status is 'running'.
      - Its target_id is non-null.
      - The feature referenced by target_id has a terminal status
        ('completed', 'needs_human', 'regression', 'failed').

    Runs with a null target_id are skipped — they cannot be joined against
    a feature and are not zombies by this definition.

    Args:
        project_id: UUID of the project to scan.

    Returns:
        List of SubAgentRun objects that should be reaped.
    """
    running_runs = db.query_agent_runs(project_id=project_id, status="running")

    # Collect only runs that have a non-null target_id so we can check feature status.
    candidates = [r for r in running_runs if r.target_id is not None]
    if not candidates:
        return []

    # Build a set of terminal feature IDs for this project (one query, not N).
    terminal_feature_ids: set[str] = set()
    for status in _TERMINAL_FEATURE_STATUSES:
        for feature in db.list_features(project_id=project_id, status=status):
            terminal_feature_ids.add(feature.id)

    zombies = [r for r in candidates if r.target_id in terminal_feature_ids]
    return zombies


def reap_zombie_run(run: "SubAgentRun", now: datetime | None = None) -> None:
    """Mark a single zombie run as status='timeout' with a completion timestamp.

    Side effects:
    - Sets status='timeout'.
    - Sets completed_at = now.
    - Emits a structured INFO log with run ID, purpose, and target_id.

    Args:
        run: The SubAgentRun model instance to reap.
        now: Reference timestamp (defaults to UTC now).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    logger.info(
        "ZOMBIE_REAPER: closing zombie run %s (purpose=%s target_id=%s) as timeout",
        run.id[:8],
        run.purpose,
        run.target_id[:8] if run.target_id else None,
    )

    db.update_agent_run(
        run.id,
        status="timeout",
        completed_at=now,
    )


def scan_and_reap(project_id: str) -> list[str]:
    """Find and reap all zombie sub_agent_runs for *project_id*.

    Intended to be called on each orchestrator tick (or a dedicated timer).
    Idempotent and safe to call concurrently — each reap is an atomic
    UPDATE and double-reaping an already-closed run is harmless (the
    status field will already be 'timeout').

    Args:
        project_id: UUID of the project to scan.

    Returns:
        List of run IDs that were reaped.
    """
    zombies = find_zombie_runs(project_id)
    if not zombies:
        return []

    now = datetime.now(timezone.utc)
    reaped_ids: list[str] = []
    for run in zombies:
        try:
            reap_zombie_run(run, now=now)
            reaped_ids.append(run.id)
        except Exception:
            logger.warning(
                "ZOMBIE_REAPER: failed to reap run %s; skipping",
                run.id[:8],
                exc_info=True,
            )

    return reaped_ids
