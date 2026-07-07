"""Orchestrator-liveness probe (feature 788eabf2).

Public entry points for deciding whether an orchestrator is already running
and whether a stale ``.bob.lock`` may be removed.

Background
----------
Bob gen-N installs its CLI as ``bobN`` (e.g. ``bob14``) via the editable
install entry_points. The operator/watchdog previously used
``pgrep -fa "bob run"`` which did NOT match a running ``bob14 run --all``
process. The operator-loop mis-diagnosed a false-stall, removed the
``.bob.lock`` file (which legitimately named a live holder PID), and launched
a second orchestrator — two orchestrators briefly raced on the same SQLite DB.

Fix contract
------------
1. The process probe MUST use the ``bob[0-9]*`` regex so gen-N aliases
   (``bob14``, ``bob59``) as well as the legacy ``bob run`` form all match.
2. ``.bob.lock`` MUST NOT be removed unless ALL THREE signals agree that no
   orchestrator is alive:
     a. no process matching ``bob[0-9]* run`` (pgrep/regex signal)
     b. the PID recorded in ``.bob.lock`` is not alive (``kill -0``)
     c. the DB has no ``executing`` feature rows updated within the last 60 s
"""

from __future__ import annotations

import pathlib

from bob.orchestrator.liveness_probe import is_orchestrator_alive, safe_to_remove_lock


def is_orchestrator_running() -> bool:
    """Return True if any ``bob[0-9]* run`` (incl. gen-N alias) process is alive.

    Scans /proc for live processes whose cmdline matches the orchestrator
    pattern, covering both the legacy ``bob run`` form and gen-N binary aliases
    such as ``bob14 run --all``. Excludes the current process, its ancestry,
    and shell/timeout wrappers that merely quote a ``bobN run`` command.

    This is signal #1 of the three-signal liveness gate.
    """
    return is_orchestrator_alive()


def should_remove_lock(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Return True ONLY when ALL three signals agree no orchestrator is running.

    The ``.bob.lock`` file MUST NOT be removed unless ALL of the following hold:
      1. is_orchestrator_running() is False (no ``bob[0-9]* run`` process)
      2. the PID in ``.bob.lock`` is not alive (``kill -0``)
      3. the DB has no ``executing`` rows updated within the last 60 s

    Any signal indicating liveness — or any DB error — yields False
    (conservative: a false-negative is far safer than allowing two
    orchestrators to race on the same DB).
    """
    return safe_to_remove_lock(lock_path, db_path=db_path)
