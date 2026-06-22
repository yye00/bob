"""Feature 4338fc09: orchestrator-liveness probe MUST match bob[0-9]+ regex AND honor .bob3.lock holder PID.

Operational defect fix: pgrep bob3 run missed gen-N binary aliases (e.g. bob14).
Three-signal gate — ALL signals must agree no orchestrator is alive before the
.bob3.lock file may be safely removed:

  Signal 1 — regex pgrep: no process matching bob[0-9]+ run in argv
  Signal 2 — kill-0:      .bob3.lock holder PID is no longer alive
  Signal 3 — DB-recency:  no feature row has status='executing' updated within 60s

The lock MUST NOT be removed unless ALL three signals agree.
"""

from __future__ import annotations

import pathlib

from bob3.orchestrator.liveness_probe import safe_to_remove_lock

__all__ = [
    "orchestrator_liveness_probe_must_match_bob_0_9_regex_honor",
]


def orchestrator_liveness_probe_must_match_bob_0_9_regex_honor(
    lock_path: str | pathlib.Path,
    db_path: pathlib.Path | None = None,
) -> bool:
    """Return True ONLY when ALL three signals agree no orchestrator is running.

    Three-signal liveness gate contract:

      1. Regex pgrep: scans /proc for processes matching bob[0-9]+ run —
         covers gen-N aliases (bob14, bob59, …) that pgrep bob3 run misses.
      2. Lock PID: probes the holder PID from .bob3.lock with kill(pid, 0).
         The lock MUST NOT be removed unless this PID is confirmed dead.
      3. DB recency: checks whether any feature has status='executing' updated
         within the last 60 seconds.

    Returns True (safe to remove lock) only when all three signals are False.
    Returns False (conservative; do NOT remove lock) when any signal indicates
    liveness or is ambiguous.
    """
    return safe_to_remove_lock(lock_path=lock_path, db_path=db_path)
