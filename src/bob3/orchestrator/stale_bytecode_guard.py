"""Stale-bytecode guard for bob3 self-heal (feature 67a3cb40-85aa-40eb-a26f-6d150ee0d298).

Self-heal compares mtime of every .py file under src/bob*/orchestrator/ against
the previous bob_N process's start time.  If any file is newer than the process
start, the running process held pre-edit bytecode and must be killed+relaunched
even when the DB looks recoverable.

Direct response to the 2026-05-23 incident where F-R6-318/319/321 patches were
on disk but the running process held stale bytecode for 90+ minutes.
"""

from __future__ import annotations

import json
import logging
import math
import os
import pathlib
import time
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
        workspace: Root of the bob generation directory (e.g. /path/to/bob78).
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


def record_start_time(
    lock_file: pathlib.Path,
    pid: Optional[int] = None,
    started_at: Optional[float] = None,
) -> None:
    """Write a JSON lock file recording the current process pid and start time.

    Overwrites any existing lock file (including the old plain-PID format).

    Args:
        lock_file: Path to .bob3.lock.
        pid: Process ID to record; defaults to os.getpid().
        started_at: Unix timestamp to record; defaults to time.time().
    """
    if pid is None:
        pid = os.getpid()
    if started_at is None:
        started_at = time.time()

    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(json.dumps({"pid": pid, "started_at": started_at}))


def _read_start_time_from_lock(lock_file: pathlib.Path) -> Optional[float]:
    """Extract started_at from a JSON lock file; return None on any failure."""
    try:
        text = lock_file.read_text().strip()
        data = json.loads(text)
        if isinstance(data, dict) and "started_at" in data:
            return float(data["started_at"])
    except (json.JSONDecodeError, ValueError, OSError):
        pass
    return None


def check_freshness(
    workspace: pathlib.Path,
    start_time: Optional[float] = None,
    *,
    lock_file: Optional[pathlib.Path] = None,
) -> list[pathlib.Path]:
    """Return .py files under src/bob*/orchestrator/ that are newer than start_time.

    If start_time is not given, lock_file must be provided and must contain a
    JSON-encoded {"started_at": <float>} entry written by record_start_time.
    Old plain-PID lock files have no start time; in that case the function
    returns an empty list (cannot determine staleness).

    Emits a WARNING log line for each stale file naming the path, so operators
    can correlate with their edits.

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob12).
        start_time: Unix timestamp of the previous bob_N process start.
        lock_file: Path to .bob3.lock; used when start_time is None.

    Returns:
        List of pathlib.Path objects for stale .py files (empty if none).
    """
    if start_time is None:
        if lock_file is None:
            raise ValueError("Either start_time or lock_file must be provided")
        start_time = _read_start_time_from_lock(lock_file)
        if start_time is None:
            # Old plain-PID format — cannot determine process start time
            return []

    stale: list[pathlib.Path] = []
    src_dir = workspace / "src"
    if not src_dir.is_dir():
        return []

    for orch_dir in src_dir.glob("bob*/orchestrator"):
        if not orch_dir.is_dir():
            continue
        # Use os.scandir so an unreadable directory raises PermissionError
        # (pathlib.glob silently returns empty on permission-denied dirs).
        try:
            entries = list(os.scandir(orch_dir))
        except PermissionError as exc:
            raise PermissionError(
                f"permission denied reading orchestrator dir {orch_dir}: {exc}"
            ) from exc
        for entry in sorted(entries, key=lambda e: e.name):
            if not entry.name.endswith(".py"):
                continue
            py_file = pathlib.Path(entry.path)
            mtime = entry.stat().st_mtime
            if mtime > start_time:
                stale.append(py_file)
                logger.warning(
                    "STALE-BYTECODE: %s modified at %.3f, process started at %.3f "
                    "— relaunch required",
                    py_file,
                    mtime,
                    start_time,
                )

    return stale


def is_stale(
    workspace: pathlib.Path,
    start_time: Optional[float] = None,
    *,
    lock_file: Optional[pathlib.Path] = None,
) -> bool:
    """Return True when any orchestrator file mtime > recorded start_time.

    Args:
        workspace: Root of the bob generation directory.
        start_time: Unix timestamp of the previous bob_N process start.
        lock_file: Path to .bob3.lock; used when start_time is None.

    Returns:
        True if any stale file found; False otherwise (including when
        start_time cannot be determined).
    """
    if start_time is None and lock_file is None:
        return False
    return bool(check_freshness(workspace, start_time, lock_file=lock_file))


def log_stale_file(path: pathlib.Path, mtime: float, start_time: float) -> None:
    """Emit a WARNING log line naming the stale path so operators can correlate.

    Args:
        path: Path to the stale orchestrator source file.
        mtime: File modification time as a Unix timestamp.
        start_time: Process start time as a Unix timestamp.
    """
    logger.warning(
        "STALE-BYTECODE: %s modified at %.3f, process started at %.3f — relaunch required",
        path,
        mtime,
        start_time,
    )


def handle_missing_lock_file(lock_file: pathlib.Path) -> bool:
    """Return True conservatively when .bob3.lock is absent.

    If the lock file does not exist we cannot determine whether the running
    process holds stale bytecode.  Return True to force a relaunch rather
    than silently running with potentially stale bytecode.

    Args:
        lock_file: Path to .bob3.lock.

    Returns:
        True when the lock file is absent (conservative/safe default).
        False when the lock file exists.
    """
    return not lock_file.exists()
