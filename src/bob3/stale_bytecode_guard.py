"""Stale-bytecode guard at relaunch.

Self-heal compares mtime of every .py file under src/bob*/orchestrator/ against
the previous bob_N process's start time. If any orchestrator source file is
newer than process start, kill+relaunch the process even when the DB looks
recoverable.
"""

from __future__ import annotations

import logging
import math
import pathlib

logger = logging.getLogger(__name__)


def check_stale_bytecode(
    workspace: pathlib.Path,
    start_time: float,
) -> list[pathlib.Path]:
    """Return .py files under src/bob*/orchestrator/ that are newer than start_time.

    Self-heal decision point: compares the mtime of every .py file under
    src/bob*/orchestrator/ against the previous bob_N process's start_time.
    Any file with mtime > start_time indicates the running process holds
    pre-edit bytecode and must be killed and relaunched.

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob84).
        start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        List of pathlib.Path objects for stale .py files. Empty if none.

    Raises:
        ValueError: If workspace is not a pathlib.Path, or start_time is not
            a finite number.
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


def check_stale_orchestrator_bytecode(
    workspace: pathlib.Path,
    start_time: float,
) -> list[pathlib.Path]:
    """Return .py files under src/bob*/orchestrator/ that are newer than start_time.

    Self-heal decision point: compares the mtime of every .py file under
    src/bob*/orchestrator/ against the previous bob_N process's start_time.
    Any file with mtime > start_time indicates the running process holds
    pre-edit bytecode and must be killed and relaunched.

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob81).
        start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        List of pathlib.Path objects for stale .py files. Empty if none.

    Raises:
        ValueError: If workspace is not a pathlib.Path, or start_time is not
            a finite number.
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


def check_orchestrator_staleness(
    workspace: pathlib.Path,
    start_time: float,
) -> list[pathlib.Path]:
    """Return .py files under src/bob*/orchestrator/ that are newer than start_time.

    Self-heal decision point: compares the mtime of every .py file under
    src/bob*/orchestrator/ against the previous bob_N process's start_time.
    Any file with mtime > start_time indicates the running process holds
    pre-edit bytecode and must be killed and relaunched.

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob86).
        start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        List of pathlib.Path objects for stale .py files. Empty if none.

    Raises:
        ValueError: If workspace is not a pathlib.Path, or start_time is not
            a finite number.
    """
    return check_stale_bytecode(workspace, start_time)


def check_stale_orchestrator_files(
    workspace: pathlib.Path,
    start_time: float,
) -> list[pathlib.Path]:
    """Return .py files under src/bob*/orchestrator/ that are newer than start_time.

    Self-heal decision point: compares the mtime of every .py file under
    src/bob*/orchestrator/ against the previous bob_N process's start_time.
    Any file with mtime > start_time indicates the running process holds
    pre-edit bytecode and must be killed and relaunched.

    Args:
        workspace: Root of the bob generation directory (e.g. /path/to/bob81).
        start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        List of pathlib.Path objects for stale .py files. Empty if none.

    Raises:
        ValueError: If workspace is not a pathlib.Path, or start_time is not
            a finite number.
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


def detect_stale_orchestrator_files(
    workspace: pathlib.Path,
    process_start_time: float,
) -> list[pathlib.Path]:
    """Return orchestrator .py files whose mtime is newer than process_start_time.

    Compares the mtime of every .py file under src/bob*/orchestrator/ against
    the recorded bob_N process start time. Any file newer than the start time
    indicates the running process holds stale bytecode and must be relaunched.

    Args:
        workspace: Root of the bob generation directory.
        process_start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        List of pathlib.Path objects for stale .py files. Empty list if none.

    Raises:
        ValueError: If workspace is not a pathlib.Path or process_start_time is
            not a finite number.
    """
    return check_stale_orchestrator_files(workspace, process_start_time)


def should_relaunch_on_stale_bytecode(
    workspace: pathlib.Path,
    process_start_time: float,
) -> bool:
    """Return True when any orchestrator source file is newer than process_start_time.

    Self-heal decision point: if any .py file under src/bob*/orchestrator/ was
    modified after the bob_N process started, the running process holds stale
    bytecode and must be killed and relaunched even when the DB looks recoverable.

    Args:
        workspace: Root of the bob generation directory.
        process_start_time: Unix timestamp of the previous bob_N process start.

    Returns:
        True when at least one stale orchestrator file is detected.
        False when no stale files are found.

    Raises:
        ValueError: If workspace is not a pathlib.Path or process_start_time is
            not a finite number.
    """
    return bool(detect_stale_orchestrator_files(workspace, process_start_time))
