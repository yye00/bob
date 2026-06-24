"""Stale-bytecode guard at relaunch (feature d2df584f-9b5a-4279-9a2c-d712609fe474).

Self-heal compares mtime of every .py file under src/bob*/orchestrator/ against
the previous bob_N process's start time. If any orchestrator source file is
newer than process start, kill+relaunch the process even when the DB looks
recoverable.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import signal
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def check_stale_bytecode(
    workspace: pathlib.Path,
    start_time: float,
) -> list[pathlib.Path]:
    """Return .py files under src/bob*/orchestrator/ that are newer than start_time.

    Compares the mtime of every .py file under src/bob*/orchestrator/ against
    the previous bob_N process's start_time. Any file with mtime > start_time
    indicates the running process holds pre-edit bytecode and must be relaunched.

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob72).
        start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        List of pathlib.Path objects for stale .py files. Empty if none.

    Raises:
        ValueError: If workspace is not a pathlib.Path or start_time is not a
            finite number.
    """
    if not isinstance(workspace, pathlib.Path):
        raise ValueError(
            f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}"
        )
    if not isinstance(start_time, (int, float)):
        raise ValueError(
            f"start_time must be a numeric type, got {type(start_time).__name__!r}"
        )
    import math
    if math.isnan(start_time) or math.isinf(start_time):
        raise ValueError(f"start_time must be a finite number, got {start_time!r}")

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


def check_and_relaunch_if_stale(
    workspace: pathlib.Path,
    start_time: Optional[float] = None,
    lock_file: Optional[pathlib.Path] = None,
    pid: Optional[int] = None,
) -> bool:
    """Kill and relaunch the bob_N process if orchestrator source files are stale.

    Compares mtime of every .py file under src/bob*/orchestrator/ against the
    previous bob_N process start time. If any file is newer than process start,
    sends SIGTERM to the target pid (default: os.getpid()) and re-execs the
    current process to pick up the updated bytecode.

    Conservative defaults protect against stale bytecode running undetected:
    - If start_time is not provided, it is read from lock_file (JSON started_at).
    - If lock_file is missing or unparseable, returns False (cannot determine
      staleness; caller must decide).

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob73).
        start_time: Explicit Unix timestamp of the previous bob_N process start.
            When given, lock_file is not consulted.
        lock_file: Path to .bob.lock containing JSON with "started_at" key.
            Consulted only when start_time is None.
        pid: PID to kill on stale detection. Defaults to os.getpid() (self).

    Returns:
        True when stale files were detected and kill+relaunch was triggered.
        False when no stale files found (or start_time could not be determined).

    Raises:
        ValueError: If workspace is not a pathlib.Path.
    """
    if not isinstance(workspace, pathlib.Path):
        raise ValueError(
            f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}"
        )

    resolved_start_time = _resolve_start_time_for_relaunch(start_time, lock_file)
    if resolved_start_time is None:
        return False

    stale_files = check_stale_bytecode(workspace, resolved_start_time)
    if not stale_files:
        return False

    target_pid = pid if pid is not None else os.getpid()
    logger.warning(
        "STALE-BYTECODE: %d stale orchestrator file(s) detected — "
        "killing PID %d and relaunching",
        len(stale_files),
        target_pid,
    )

    try:
        os.kill(target_pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as exc:
        logger.error(
            "STALE-BYTECODE: failed to send SIGTERM to PID %d: %s",
            target_pid,
            exc,
        )
        return True

    if target_pid == os.getpid():
        # Re-exec self so the updated source is loaded by the new process.
        logger.warning("STALE-BYTECODE: re-exec'ing self to pick up updated bytecode")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    return True


def _resolve_start_time_for_relaunch(
    explicit_start_time: Optional[float],
    lock_file: Optional[pathlib.Path],
) -> Optional[float]:
    """Return the process start time from explicit arg or lock file, or None."""
    if explicit_start_time is not None:
        return explicit_start_time

    if lock_file is None or not lock_file.exists():
        return None

    try:
        text = lock_file.read_text().strip()
        data = json.loads(text)
        if isinstance(data, dict) and "started_at" in data:
            return float(data["started_at"])
    except (json.JSONDecodeError, ValueError, OSError):
        pass

    return None


# Alias to satisfy AC "Function defined: bob_orchestrator.stale_bytecode_guard.check_source_freshness"
check_source_freshness = check_stale_bytecode
