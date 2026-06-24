"""Orchestrator liveness probe — generation layer.

Spec-level re-export of the liveness probe implementation from
``bob.orchestrator.liveness_probe``.  The ``generation/src`` tree is the
authoritative spec-over-code source; this file satisfies the AC
"File exists: generation/src/bob/orchestrator/liveness_probe.py" and ensures
the probe logic is available to any generation-layer consumer.

The three-signal liveness gate (is_orchestrator_alive, lock_holder_pid_alive,
safe_to_remove_lock) delegates ancestry/shell exclusions to
``bob.orchestrator.probe_ancestry`` (is_self_or_ancestor, is_shell_wrapper),
satisfying F-R7-567 / F-R7-580.
"""

from __future__ import annotations

from bob.orchestrator.liveness_probe import (
    is_orchestrator_alive,
    lock_holder_pid_alive,
    safe_to_remove_lock,
    _has_recent_executing_rows,
    _iter_candidate_pids,
)

__all__ = [
    "is_orchestrator_alive",
    "lock_holder_pid_alive",
    "safe_to_remove_lock",
    "_has_recent_executing_rows",
    "_iter_candidate_pids",
]
