"""Feature 53afc69e: orchestrator-liveness probe MUST match bob[0-9]+ regex AND honor .bob3.lock holder PID.

Operational defect: pgrep bob3 run missed gen-N binary aliases (e.g. bob14),
causing false-stall detection and two orchestrators racing on the same DB.

Three-signal gate — ALL signals must agree no orchestrator is alive before
the .bob3.lock file may be safely removed:

  Signal 1 — pgrep-style: no process matching ``bob[0-9]+ run`` in argv
  Signal 2 — kill-0:      .bob3.lock holder PID is no longer alive
  Signal 3 — DB-recency:  no feature row has status='executing' updated
                           within the last 60 seconds

This module exposes the AC-mandated function name that wraps safe_to_remove_lock
from bob3.orchestrator.liveness_probe.
"""

from __future__ import annotations

import pathlib

from bob3.orchestrator.liveness_probe import (
    _has_recent_executing_rows,
    is_orchestrator_alive,
    lock_holder_pid_alive,
    safe_to_remove_lock,
)

__all__ = [
    "orchestrator_liveness_probe_must_match_bob_0_9_regex_honor_bob3_lock_holder_pid_current_operator_watchdog_pgrep_bob3_run_misses_gen_n_binary_alias_bobn_false_stalls_races_second_orchestrator_same_db",
]


def orchestrator_liveness_probe_must_match_bob_0_9_regex_honor_bob3_lock_holder_pid_current_operator_watchdog_pgrep_bob3_run_misses_gen_n_binary_alias_bobn_false_stalls_races_second_orchestrator_same_db(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Return True ONLY when ALL three signals agree no orchestrator is running.

    Implements the three-signal liveness gate contract:

      1. Regex pgrep: scans /proc for processes matching ``bob[0-9]+ run``
         — covers gen-N aliases (bob14, bob59, …) that ``pgrep bob3 run`` misses.
      2. Lock PID: probes the holder PID from .bob3.lock with kill(pid, 0).
         The lock MUST NOT be removed unless this PID is confirmed dead.
      3. DB recency: checks whether any feature has status='executing' updated
         within the last 60 seconds.

    Returns True (safe to remove lock) only when:
      - is_orchestrator_alive() is False
      - lock_holder_pid_alive(lock_path) is False
      - _has_recent_executing_rows() is False

    Returns False (conservative; do NOT remove lock) when any signal is
    ambiguous or indicates liveness.
    """
    return safe_to_remove_lock(lock_path=lock_path, db_path=db_path)
