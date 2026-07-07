"""Orchestrator liveness probe (b6cc32ea).

Provides three public functions used to determine whether an orchestrator
is already running and whether its lock file is safe to remove.

Background
----------
Bob gen-N installs its CLI as ``bobN`` (e.g. ``bob14``) via the editable
install entry_points. A naive ``pgrep bob run`` misses a running
``bob14 run --all`` process, causing false-stall detection that leads to
a second orchestrator racing on the same SQLite database.

The contract here requires ALL THREE independent signals to agree that no
orchestrator is alive before the lock file may be removed:

    1. No process matching ``bob[0-9]+ run`` (or ``bob run``) in argv
    2. The PID recorded in .bob.lock is no longer alive (kill -0)
    3. No feature row has status='executing' updated within the last 60 s
"""

from __future__ import annotations

import logging
import os
import pathlib
import re

from bob.orchestrator.probe_ancestry import collect_ancestor_pids, is_shell_wrapper

logger = logging.getLogger(__name__)

# Regex matches: 'bob run', 'bob14 run', '/path/to/bob14 run', etc.
# The generation digits are optional so both the legacy 'bob run' form and the
# gen-N binary alias 'bobN run' (e.g. bob14) are detected.
_ORCHESTRATOR_PATTERN = re.compile(r"(?:^|[\s/])bob[0-9]*\s+run(?:\s|$)")

# How many seconds of executing-row recency counts as "live".
_EXECUTING_RECENCY_SECONDS = 60


# ---------------------------------------------------------------------------
# Internal helpers (thin wrappers to allow unit-test patching)
# ---------------------------------------------------------------------------

def _iter_candidate_pids() -> list[tuple[int, str]]:
    """Return (pid, cmdline) pairs for every live process via /proc."""
    results: list[tuple[int, str]] = []
    proc_root = "/proc"
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return results
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            pid = int(entry)
            cmdline_path = os.path.join(proc_root, entry, "cmdline")
            with open(cmdline_path, "rb") as fh:
                raw = fh.read()
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
            results.append((pid, cmdline))
        except (OSError, ValueError):
            continue
    return results


def _has_recent_executing_rows(db_path: pathlib.Path | None = None) -> bool:
    """Return True if any feature has status='executing' updated within 60 s.

    Falls back to True (conservative) on any DB error so that the caller
    never removes a lock when the DB is unreadable.
    """
    from bob import db as _db
    sql = (
        "SELECT COUNT(*) FROM features "
        "WHERE status = 'executing' "
        "AND (julianday('now') - julianday(updated_at)) * 86400 < ?"
    )
    try:
        with _db.connect(db_path=db_path) as conn:
            row = conn.execute(sql, (_EXECUTING_RECENCY_SECONDS,)).fetchone()
        return (row[0] if row else 0) > 0
    except Exception:
        logger.debug("_has_recent_executing_rows: DB error; returning True (conservative)", exc_info=True)
        return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_orchestrator_alive() -> bool:
    """Return True if any process matching 'bob[0-9]+ run' (or 'bob run') is alive.

    Scans /proc for live processes whose cmdline matches the pattern.
    Excludes:
    - current process (os.getpid())
    - the entire process ancestry of the current process (parent, grandparent, ...)
      — shells / wrappers whose argv mentions the bobN run command we are
      ABOUT to execute are not separate orchestrators.
    - processes whose argv[0] is a shell binary (bash/sh/dash/zsh/ksh) — the
      shell is invoking the command, not running it as a long-lived orchestrator.

    F-R7-580 (bob version 17 r1): substring-match on cmdline was too loose;
    the parent bash whose eval string contained "bob17 run" tripped the guard
    on every launch, blocking the bob version 17 boot indefinitely.

    This is signal #1 of the three-signal liveness check.
    """
    own_pid = os.getpid()
    ancestry = collect_ancestor_pids(own_pid)

    for pid, cmdline in _iter_candidate_pids():
        if pid <= 1 or pid in ancestry:
            continue
        if not cmdline:
            continue
        if is_shell_wrapper(cmdline):
            continue
        if _ORCHESTRATOR_PATTERN.search(cmdline):
            logger.debug("is_orchestrator_alive: found PID %d matching %r", pid, cmdline[:80])
            return True
    return False


def lock_holder_pid_alive(lock_path: str | pathlib.Path) -> bool:
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

    This is signal #2 of the three-signal liveness check.
    """
    if not isinstance(lock_path, (str, bytes, os.PathLike)):
        raise ValueError(
            f"lock_path must be a str, bytes, or path-like object, got {type(lock_path).__name__!r}"
        )
    lock_path = pathlib.Path(lock_path)
    try:
        contents = lock_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return False
    if not contents:
        return False
    try:
        pid = int(contents.split()[0])
    except (ValueError, IndexError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Be conservative on unexpected errors: assume alive.
        return True
    return True


def safe_to_remove_lock(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Return True ONLY when ALL three signals agree no orchestrator is running.

    The three signals that must ALL be False for this to return True:

    1. is_orchestrator_alive() — pgrep-style check for bob[0-9]+ run
    2. lock_holder_pid_alive(lock_path) — kill -0 on the PID in the lock file
    3. _has_recent_executing_rows() — DB check for executing rows in last 60 s

    If any signal indicates liveness (or raises an exception), returns False
    (conservative: prefer a false-negative over a false-positive that allows
    two orchestrators to race on the same DB).

    This is the three-signal gate used before removing .bob.lock.
    """
    lock_path = pathlib.Path(lock_path)

    if is_orchestrator_alive():
        logger.debug("safe_to_remove_lock: pgrep signal shows alive")
        return False

    if lock_holder_pid_alive(lock_path):
        logger.debug("safe_to_remove_lock: lock PID signal shows alive")
        return False

    try:
        if _has_recent_executing_rows(db_path=db_path):
            logger.debug("safe_to_remove_lock: DB executing-rows signal shows alive")
            return False
    except Exception:
        logger.debug("safe_to_remove_lock: DB error → conservative False", exc_info=True)
        return False

    return True


def remove_stale_lock(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Remove lock_path when ALL three signals agree no orchestrator is running.

    The lock file MUST NOT be removed unless ALL three signals agree:
      1. No process matching ``bob[0-9]+ run`` (pgrep signal)
      2. The PID in .bob.lock is no longer alive (kill -0)
      3. No feature row has status='executing' updated in last 60 s (DB signal)

    Returns True if the lock file was successfully removed.
    Returns False if any signal indicates liveness, the lock file does not
    exist, or the removal fails.

    This is the AC-mandated function (feature ce8a7658) that combines the
    three-signal gate with actual lock file removal.

    AC: Function defined: bob.orchestrator.remove_stale_lock
    """
    lock_path = pathlib.Path(lock_path)
    if not safe_to_remove_lock(lock_path, db_path=db_path):
        logger.debug("remove_stale_lock: three-signal gate says not safe; lock not removed")
        return False
    try:
        lock_path.unlink()
        logger.info("remove_stale_lock: removed stale lock %s", lock_path)
        return True
    except FileNotFoundError:
        logger.debug("remove_stale_lock: lock file already gone: %s", lock_path)
        return False
    except OSError:
        logger.warning("remove_stale_lock: failed to remove %s", lock_path, exc_info=True)
        return False
