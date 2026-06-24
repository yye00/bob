"""Stale-bytecode guard at relaunch for bob orchestrator (feature fd401bd3-2afa-4eee-b67d-6af7449dfaac).

Self-heal compares mtime of every file under src/bob*/orchestrator/ against
the previous bob_N process's start time. If any orchestrator source file is
newer than process start, kill+relaunch the process even when the DB looks
recoverable.
"""

from __future__ import annotations

import logging
import math
import os
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)


def should_relaunch_on_stale_bytecode(
    workspace: pathlib.Path,
    process_start_time: float,
) -> bool:
    """Return True when any orchestrator source file is newer than process start.

    Compares mtime of every .py file under src/bob*/orchestrator/ against the
    previous bob_N process's start_time. If any file is newer than process start,
    the running process holds pre-edit bytecode and must be killed+relaunched
    even when the DB looks recoverable.

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob79).
        process_start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        True when at least one orchestrator .py file has mtime > process_start_time.
        False when all files are older or no orchestrator directories exist.

    Raises:
        ValueError: If workspace is not a pathlib.Path, or process_start_time
            is not a finite numeric value.
    """
    if not isinstance(workspace, pathlib.Path):
        raise ValueError(
            f"workspace must be a pathlib.Path, got {type(workspace).__name__!r}"
        )
    if not isinstance(process_start_time, (int, float)):
        raise ValueError(
            f"process_start_time must be a numeric type, "
            f"got {type(process_start_time).__name__!r}"
        )
    if math.isnan(process_start_time) or math.isinf(process_start_time):
        raise ValueError(
            f"process_start_time must be a finite number, got {process_start_time!r}"
        )

    src_dir = workspace / "src"
    if not src_dir.is_dir():
        return False

    for orch_dir in sorted(src_dir.glob("bob*/orchestrator")):
        if not orch_dir.is_dir():
            continue
        try:
            entries = list(os.scandir(orch_dir))
        except PermissionError as exc:
            raise PermissionError(
                f"permission denied reading orchestrator dir {orch_dir}: {exc}"
            ) from exc
        for entry in entries:
            if not entry.name.endswith(".py"):
                continue
            mtime = entry.stat().st_mtime
            if mtime > process_start_time:
                logger.warning(
                    "STALE-BYTECODE: %s modified at %.3f, process started at %.3f "
                    "— relaunch required",
                    entry.path,
                    mtime,
                    process_start_time,
                )
                return True

    return False
