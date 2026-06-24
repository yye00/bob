"""Stale-bytecode guard at relaunch (feature e6c0019a-9c17-48e3-a7ad-63f233d48a50).

Self-heal decision point: compares mtime of every .py file under
src/bob*/orchestrator/ against the previous bob_N process's start time.
If any orchestrator source file is newer than process start, the process
must be killed and relaunched even when the DB looks recoverable.

This addresses the risk that a running process holds pre-edit bytecode
while updated source files are already on disk.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)


def stale_bytecode_guard_relaunch(
    workspace: pathlib.Path,
    lock_file: Optional[pathlib.Path] = None,
    *,
    start_time: Optional[float] = None,
) -> bool:
    """Return True when kill+relaunch is required due to stale bytecode.

    Compares the mtime of every .py file under src/bob*/orchestrator/ against
    the previous bob_N process start time. Returns True if any file is newer,
    meaning the running process holds stale bytecode.

    Conservative defaults protect against data loss:
    - Missing lock file → True (cannot determine staleness; force relaunch)
    - Unparseable lock file (old plain-PID format) → True (same reason)
    - No orchestrator dirs found → False (nothing to check)

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob66).
        lock_file: Path to .bob.lock. When provided and start_time is None,
            the started_at value is read from the lock file JSON.
        start_time: Explicit Unix timestamp of the previous bob_N process start.
            When given, lock_file is not read (even if provided).

    Returns:
        True when relaunch is required; False when all source files predate
        the recorded start time (process bytecode is up to date).
    """
    resolved_start_time = _resolve_start_time(lock_file, start_time)
    if resolved_start_time is None:
        return True

    stale_files = _collect_stale_files(workspace, resolved_start_time)
    return bool(stale_files)


def _resolve_start_time(
    lock_file: Optional[pathlib.Path],
    explicit_start_time: Optional[float],
) -> Optional[float]:
    """Return the process start time, or None when it cannot be determined.

    None signals the caller to apply the conservative default (force relaunch).
    """
    if explicit_start_time is not None:
        return explicit_start_time

    if lock_file is None:
        return None

    if not lock_file.exists():
        logger.warning(
            "STALE-BYTECODE: lock file %s absent — conservative relaunch required",
            lock_file,
        )
        return None

    try:
        text = lock_file.read_text().strip()
        data = json.loads(text)
        if isinstance(data, dict) and "started_at" in data:
            return float(data["started_at"])
    except (json.JSONDecodeError, ValueError, OSError):
        pass

    logger.warning(
        "STALE-BYTECODE: lock file %s has no parseable started_at — "
        "conservative relaunch required",
        lock_file,
    )
    return None


def _collect_stale_files(
    workspace: pathlib.Path,
    start_time: float,
) -> list[pathlib.Path]:
    """Return .py files under src/bob*/orchestrator/ newer than start_time."""
    src_dir = workspace / "src"
    if not src_dir.is_dir():
        return []

    stale: list[pathlib.Path] = []
    for orch_dir in sorted(src_dir.glob("bob*/orchestrator")):
        if not orch_dir.is_dir():
            continue
        for entry in sorted(orch_dir.iterdir()):
            if entry.suffix != ".py":
                continue
            mtime = entry.stat().st_mtime
            if mtime > start_time:
                stale.append(entry)
                logger.warning(
                    "STALE-BYTECODE: %s modified at %.3f, process started at %.3f "
                    "— relaunch required",
                    entry,
                    mtime,
                    start_time,
                )
    return stale
