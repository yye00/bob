"""bob3.liveness_probe — Public API for orchestrator liveness checks (feature 28e1082f).

Thin wrappers over bob3.orchestrator.liveness_probe with AC-mandated names:
  - check_orchestrator_alive  (AC: Function defined: bob3.liveness_probe.check_orchestrator_alive)
  - is_lock_holder_alive      (AC: Function defined: bob3.liveness_probe.is_lock_holder_alive)

The underlying liveness probe implements a three-signal gate:
  1. No process matching ``bob[0-9]+ run`` in argv (covers gen-N aliases like bob14)
  2. The PID recorded in .bob3.lock is no longer alive (kill -0)
  3. No feature row has status='executing' updated within the last 60 s

All three signals must agree that no orchestrator is alive before the lock
file may be safely removed (safe_to_remove_lock).
"""

from __future__ import annotations

import pathlib

from bob3.orchestrator.liveness_probe import (
    is_orchestrator_alive,
    lock_holder_pid_alive,
    safe_to_remove_lock,
)

__all__ = [
    "check_orchestrator_alive",
    "check_orchestrator_running",
    "is_lock_holder_alive",
    "safe_remove_lock_file",
    "safe_to_remove_lock",
    "should_remove_lock_file",
    "is_orchestrator_alive",
    "lock_holder_pid_alive",
    "validate_lock_file_holder",
]


def check_orchestrator_running() -> bool:
    """Return True if any process matching ``bob[0-9]+ run`` is alive.

    AC-mandated name for the regex-based process liveness check
    (feature aad0f2e8). Delegates to is_orchestrator_alive() which
    scans /proc for live processes whose cmdline matches the
    ``bob[0-9]+ run`` pattern, covering all gen-N binary aliases
    (e.g. bob14, bob59) in addition to the legacy ``bob3 run`` form.

    Excludes the current process, its ancestors, and shell wrappers.

    Signal #1 of the three-signal liveness gate.

    AC: Function defined: bob3.liveness_probe.check_orchestrator_running
    """
    return is_orchestrator_alive()


def check_orchestrator_alive() -> bool:
    """Return True if any process matching ``bob[0-9]+ run`` is alive.

    Scans /proc for live processes whose cmdline matches the orchestrator
    pattern, covering all gen-N binary aliases (e.g. bob14, bob59) in
    addition to the legacy ``bob3 run`` form.

    Excludes the current process, its ancestors, and shell wrappers that
    may quote a bobN run command without running as an orchestrator.

    Signal #1 of the three-signal liveness gate.

    AC: Function defined: bob3.liveness_probe.check_orchestrator_alive
    """
    return is_orchestrator_alive()


def should_remove_lock_file(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Return True ONLY when ALL three signals agree no orchestrator is running.

    The lock file MUST NOT be removed unless ALL three signals agree:
      1. No process matching ``bob[0-9]+ run`` (pgrep signal)
      2. The PID in .bob3.lock is no longer alive (kill -0)
      3. No feature row has status='executing' updated in last 60 s (DB signal)

    This is the AC-mandated name (feature 249a58e1) for the three-signal gate
    that determines whether it is safe to remove the orchestrator lock file.

    Delegates to bob3.orchestrator.liveness_probe.safe_to_remove_lock.

    AC: Function defined: bob3.liveness_probe.should_remove_lock_file
    """
    return safe_to_remove_lock(lock_path, db_path=db_path)


def is_lock_holder_alive(lock_path: str | pathlib.Path) -> bool:
    """Return True if the PID recorded in lock_path is still alive.

    Reads the first whitespace-delimited token from the lock file,
    interprets it as a PID, and probes it with ``kill(pid, 0)``.

    Raises ValueError when lock_path is not a str, bytes, or path-like object.

    Returns False when:
    - The lock file is absent or unreadable
    - The file contains no parseable PID
    - The PID is ≤ 0
    - The process is not alive (ProcessLookupError)

    Returns True when:
    - kill(pid, 0) succeeds (process alive and signalable by us)
    - kill(pid, 0) raises PermissionError (process alive, different owner)

    Signal #2 of the three-signal liveness gate.

    AC: Function defined: bob3.liveness_probe.is_lock_holder_alive
    """
    return lock_holder_pid_alive(lock_path)


def validate_lock_file_holder(lock_path: str | pathlib.Path) -> bool:
    """Return True if the PID recorded in lock_path is still alive.

    Reads the first whitespace-delimited token from the lock file,
    interprets it as a PID, and probes it with ``kill(pid, 0)``.

    Raises ValueError when lock_path is not a str, bytes, or path-like object.

    Returns False when:
    - The lock file is absent or unreadable
    - The file contains no parseable PID
    - The PID is ≤ 0
    - The process is not alive (ProcessLookupError)

    Returns True when:
    - kill(pid, 0) succeeds (process alive and signalable by us)
    - kill(pid, 0) raises PermissionError (process alive, different owner)

    Signal #2 of the three-signal liveness gate.

    AC: Function defined: bob3.liveness_probe.validate_lock_file_holder
    """
    return lock_holder_pid_alive(lock_path)


def safe_remove_lock_file(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Remove lock_path ONLY when ALL three signals agree no orchestrator is running.

    The lock file MUST NOT be removed unless ALL three signals agree:
      1. No process matching ``bob[0-9]+ run`` (pgrep signal)
      2. The PID in .bob3.lock is no longer alive (kill -0)
      3. No feature row has status='executing' updated in last 60 s (DB signal)

    Returns True if the lock file was successfully removed.
    Returns False if any signal indicates liveness, the lock file does not
    exist, or the removal fails.

    This is the AC-mandated name for the function that combines the three-signal
    gate check with actual lock file removal.

    Delegates to bob3.orchestrator.liveness_probe.remove_stale_lock.

    AC: Function defined: bob3.liveness_probe.safe_remove_lock_file
    """
    from bob3.orchestrator.liveness_probe import remove_stale_lock
    return remove_stale_lock(lock_path, db_path=db_path)
