"""bob.liveness — Public API for orchestrator liveness checks.

Thin wrappers over bob.orchestrator.liveness_probe with AC-specified names.

The underlying liveness probe implements a three-signal gate:
  1. No process matching ``bob[0-9]+ run`` in argv (covers gen-N aliases like bob14)
  2. The PID recorded in .bob.lock is no longer alive (kill -0)
  3. No feature row has status='executing' updated within the last 60 s

All three signals must agree that no orchestrator is alive before the lock
file may be safely removed (safe_to_remove_lock).
"""

from __future__ import annotations

import pathlib

import bob.orchestrator.liveness_probe as _liveness_probe
from bob.orchestrator.liveness_probe import (
    is_orchestrator_alive,
    lock_holder_pid_alive,
    safe_to_remove_lock,
)

__all__ = [
    "probe_matches_orchestrator",
    "probe_orchestrator_alive",
    "check_lock_file_holder",
    "check_orchestrator_running",
    "validate_lock_file_holder",
    "verify_lock_file_holder",
    "verify_db_activity",
    "safe_to_remove_lock",
    "is_orchestrator_alive",
    "lock_holder_pid_alive",
    # AC-mandated names for feature ad5a1225
    "match_orchestrator_process",
    "check_lock_holder_alive",
    "check_db_active",
    # AC-mandated names for feature 9739324d (this feature)
    "check_orchestrator_alive",
    # AC-mandated names for feature ce8a7658
    "is_lock_holder_alive",
    # AC-mandated names for feature f6a04322
    "probe_process_running",
    "is_db_active",
    # AC-mandated names for feature 6d80546d
    "matches_process_regex",
    "safe_lock_removal",
]


def probe_matches_orchestrator() -> bool:
    """Return True if any process whose argv matches ``bob[0-9]+ run`` is alive.

    This is the AC-mandated name for the regex-based process liveness check.
    Scans /proc for live processes matching the ``bob[0-9]+ run`` pattern,
    covering all gen-N binary aliases (e.g. bob14, bob59) in addition to the
    legacy ``bob run`` form.

    Excludes the current process, its ancestors, and shell wrappers that may
    quote a bobN run command without running as an orchestrator themselves.

    Signal #1 of the three-signal liveness gate.
    """
    return is_orchestrator_alive()


def probe_orchestrator_alive() -> bool:
    """Return True if a bob[0-9]+ run (or bob run) process is alive.

    Scans /proc for live processes matching the orchestrator pattern.
    Excludes the current process, its ancestors, and shell wrappers
    that may quote a bobN run command without being an orchestrator.

    Signal #1 of the three-signal liveness gate.
    """
    return is_orchestrator_alive()


#: Alias for probe_orchestrator_alive (original name retained for compatibility).
check_orchestrator_running = probe_orchestrator_alive


def check_lock_file_holder(lock_path: str | pathlib.Path) -> bool:
    """Return True if the PID recorded in lock_path is still alive.

    Reads the first token from the lock file and probes it with kill(pid, 0).
    Returns False when the file is absent, unreadable, malformed, or the
    PID is no longer alive.

    Signal #2 of the three-signal liveness gate.
    """
    return lock_holder_pid_alive(lock_path)


#: Alias for check_lock_file_holder (original name retained for compatibility).
validate_lock_file_holder = check_lock_file_holder

#: AC-mandated alias for check_lock_file_holder (feature c3c4f310).
verify_lock_file_holder = check_lock_file_holder


def verify_db_activity(db_path: pathlib.Path | None = None) -> bool:
    """Return True if the database shows recent executing activity.

    Checks whether any feature row has status='executing' with an
    updated_at timestamp within the last 60 seconds. Returns True
    (conservative) on any DB error so the caller never removes a lock
    when the DB state is uncertain.

    Signal #3 of the three-signal liveness gate.
    """
    try:
        return _liveness_probe._has_recent_executing_rows(db_path=db_path)
    except Exception:
        return True


# ---------------------------------------------------------------------------
# AC-mandated names (feature ad5a1225-9c27-4b96-8d11-c8207c173551)
# ---------------------------------------------------------------------------

def match_orchestrator_process() -> bool:
    """Return True if any process matching ``bob[0-9]+ run`` is alive.

    AC-mandated name for the regex-based process liveness check (AC-0).
    Delegates to is_orchestrator_alive() which scans /proc for live
    processes whose cmdline matches the ``bob[0-9]+ run`` pattern,
    covering all gen-N binary aliases (e.g. bob14, bob59).

    Signal #1 of the three-signal liveness gate.
    """
    return is_orchestrator_alive()


def check_lock_holder_alive(lock_path: str | pathlib.Path) -> bool:
    """Return True if the PID recorded in lock_path is still alive.

    AC-mandated name for the lock-holder liveness check (AC-1).
    Delegates to lock_holder_pid_alive() which reads the first token
    from the lock file and probes it with kill(pid, 0).

    Returns False when the file is absent, unreadable, malformed, or
    the PID is no longer alive.

    Signal #2 of the three-signal liveness gate.
    """
    return lock_holder_pid_alive(lock_path)


def check_db_active(db_path: pathlib.Path | None = None) -> bool:
    """Return True if the database shows recent executing activity.

    AC-mandated name for the DB-activity liveness check (AC-2).
    Delegates to verify_db_activity() which checks whether any feature
    row has status='executing' updated within the last 60 seconds.
    Returns True (conservative) on any DB error.

    Signal #3 of the three-signal liveness gate.
    """
    return verify_db_activity(db_path=db_path)


# ---------------------------------------------------------------------------
# AC-mandated names for feature 9739324d (orchestrator-liveness probe MUST
# match bob[0-9]+ regex AND honor .bob.lock holder PID)
# ---------------------------------------------------------------------------

def check_orchestrator_alive() -> bool:
    """Return True if any process matching ``bob[0-9]+ run`` is alive.

    AC-mandated name for feature 9739324d. Delegates to is_orchestrator_alive()
    which scans /proc for live processes whose cmdline matches the
    ``bob[0-9]+ run`` pattern, covering all gen-N binary aliases (e.g. bob14,
    bob59) in addition to the legacy ``bob run`` form.

    Excludes the current process, its ancestors, and shell wrappers.

    Signal #1 of the three-signal liveness gate.

    AC: Function defined: bob.liveness.check_orchestrator_alive
    """
    return is_orchestrator_alive()


# ---------------------------------------------------------------------------
# AC-mandated names for feature ce8a7658 (orchestrator-liveness probe MUST
# match bob[0-9]+ regex AND honor .bob.lock holder PID — this feature)
# ---------------------------------------------------------------------------

def is_lock_holder_alive(lock_path: str | pathlib.Path) -> bool:
    """Return True if the PID recorded in lock_path is still alive.

    AC-mandated name for feature ce8a7658. Delegates to lock_holder_pid_alive()
    which reads the first whitespace-delimited token from the lock file and
    probes it with ``kill(pid, 0)``.

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

    AC: Function defined: bob.liveness.is_lock_holder_alive
    """
    return lock_holder_pid_alive(lock_path)


# ---------------------------------------------------------------------------
# AC-mandated names for feature f6a04322 (orchestrator-liveness probe MUST
# match bob[0-9]+ regex AND honor .bob.lock holder PID)
# ---------------------------------------------------------------------------

def probe_process_running() -> bool:
    """Return True if any process matching ``bob[0-9]+ run`` is alive.

    AC-mandated name for feature f6a04322. Delegates to is_orchestrator_alive()
    which scans /proc for live processes whose cmdline matches the
    ``bob[0-9]+ run`` pattern, covering all gen-N binary aliases (e.g. bob14,
    bob92) in addition to the legacy ``bob run`` form.

    This fixes the defect where the operator/watchdog used ``pgrep bob run``
    which missed a running ``bobN run --all`` process, causing false-stall
    detection that led to a second orchestrator racing on the same DB.

    Excludes the current process, its ancestors, and shell wrappers.

    Signal #1 of the three-signal liveness gate.

    AC: Function defined: bob.liveness.probe_process_running
    """
    return is_orchestrator_alive()


def is_db_active(db_path: pathlib.Path | None = None) -> bool:
    """Return True if the database shows recent executing activity.

    AC-mandated name for feature f6a04322. Checks whether any feature row
    has status='executing' with an updated_at timestamp within the last 60
    seconds. Returns True (conservative) on any DB error so the caller
    never removes a lock when the DB state is uncertain.

    The lock file MUST NOT be removed unless ALL three signals agree:
      1. probe_process_running() is False (no bob[0-9]+ run process found)
      2. check_lock_file_holder() is False (lock PID is not alive)
      3. is_db_active() is False (no recent executing rows)

    Signal #3 of the three-signal liveness gate.

    AC: Function defined: bob.liveness.is_db_active
    """
    return verify_db_activity(db_path=db_path)


# ---------------------------------------------------------------------------
# AC-mandated names for feature 6d80546d (this feature: orchestrator-liveness
# probe MUST match `bob[0-9]+` regex AND honor `.bob.lock` holder PID)
# ---------------------------------------------------------------------------

def matches_process_regex() -> bool:
    """Return True if any process matching ``bob[0-9]+ run`` is alive.

    AC-mandated name for feature 6d80546d. Delegates to is_orchestrator_alive()
    which scans /proc for live processes whose cmdline matches the
    ``bob[0-9]+ run`` pattern, covering all gen-N binary aliases (e.g. bob14,
    bob92, bob93) in addition to the legacy ``bob run`` form.

    This fixes the defect where the operator/watchdog used ``pgrep bob run``
    which missed a running ``bobN run --all`` process, causing false-stall
    detection that led to a second orchestrator racing on the same DB.

    Excludes the current process, its ancestors, and shell wrappers.

    Signal #1 of the three-signal liveness gate.

    AC: Function defined: bob.liveness.matches_process_regex
    """
    return is_orchestrator_alive()


def safe_lock_removal(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Return True ONLY when ALL three signals agree no orchestrator is running.

    AC-mandated name for feature 6d80546d. The lock file MUST NOT be removed
    unless ALL three signals agree:
      1. No process matching ``bob[0-9]+ run`` (pgrep/regex signal)
      2. The PID in .bob.lock is no longer alive (kill -0)
      3. No feature row has status='executing' updated in last 60 s (DB signal)

    Delegates to bob.orchestrator.liveness_probe.safe_to_remove_lock.

    Returns False if any signal indicates liveness, or on any error (conservative).

    AC: Function defined: bob.liveness.safe_lock_removal
    """
    return safe_to_remove_lock(lock_path, db_path=db_path)
