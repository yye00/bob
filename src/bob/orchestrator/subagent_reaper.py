"""Subagent reaper — feature terminal-state process cleanup (01b15b47).

Provides three public functions:

find_subagent_pid_for_feature(feature_id)
    Scans live processes for ``claude.*--print`` invocations tagged with
    ``feature <feature_id>`` in the prompt argv and returns the PID list.

reap_subagent_for_feature(feature_id)
    Sends SIGTERM to each matching PID, waits up to 15 seconds for clean
    exit, then sends SIGKILL if the process is still alive. Appends the
    sentinel ``subagent_reaped_on_terminal=<feature_id>`` to the feature
    audit log and returns the list of reaped PIDs.

sweep_orphan_subagents()
    Queries features in terminal states whose updated_at dwell exceeds
    5 minutes, calls reap_subagent_for_feature for each, and returns
    the list of (feature_id, pid) pairs reaped. Idempotent; safe to
    run concurrently with other reapers.

Safety contract
---------------
* Neither find_ nor reap_ will ever return or signal os.getpid() or
  PID ≤ 1 (system processes).
* Matching parses the real argv array (NUL-separated /proc/<pid>/cmdline),
  requires basename(argv[0]) == 'claude', and requires an argv element
  that exactly equals feature_id — preventing false positives against
  unrelated claude invocations.
* Re-validates cmdline immediately before each os.kill call to defend
  against TOCTOU / PID-reuse races: if the PID has been recycled or the
  cmdline no longer matches, the signal is aborted.
* Audit sentinel is only emitted when at least one PID was successfully
  confirmed dead after signalling. Failed reaps log a distinct sentinel.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from typing import Any

from bob import db
from bob_orchestrator.stale_bytecode_guard import check_stale_bytecode

logger = logging.getLogger(__name__)

# Terminal states whose subagents should be reaped.
_TERMINAL_STATUSES = ("completed", "needs_human", "regression", "failed")

# Grace window in seconds between SIGTERM and SIGKILL.
_SIGTERM_GRACE_SECONDS = 15

# Staleness threshold in minutes for the orphan sweeper.
_ORPHAN_STALE_MINUTES = 5


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_proc_argv(pid: int) -> list[str] | None:
    """Return the parsed argv list for ``pid``, or None on any error.

    Reads /proc/<pid>/cmdline and splits on NUL bytes so each element is
    an exact argv token (no whitespace ambiguity).
    """
    try:
        cmdline_path = os.path.join("/proc", str(pid), "cmdline")
        with open(cmdline_path, "rb") as fh:
            raw = fh.read()
        if not raw:
            return None
        # Strip trailing NUL then split — avoids a spurious empty element at end.
        parts = raw.rstrip(b"\x00").split(b"\x00")
        return [p.decode("utf-8", errors="replace") for p in parts]
    except (OSError, ValueError):
        return None


def _argv_matches(argv: list[str], feature_id: str) -> bool:
    """Return True iff argv is a claude subagent for ``feature_id``.

    Requirements (both must hold):
      1. basename(argv[0]) == 'claude'
      2. Some argv element (index ≥ 1) equals feature_id exactly.
    """
    if not argv:
        return False
    if os.path.basename(argv[0]) != "claude":
        return False
    return feature_id in argv[1:]


def _iter_candidate_pids() -> list[tuple[int, list[str]]]:
    """Return (pid, argv) pairs for every live process that might be a subagent.

    Reads /proc/<pid>/cmdline for each numeric /proc entry.  Returns an
    empty list when /proc is unavailable.  Per-PID errors are silently
    skipped (the process may have exited during the scan).

    Returns argv as a parsed list (NUL-split) so callers can do element-wise
    matching without whitespace-splitting ambiguity.
    """
    results: list[tuple[int, list[str]]] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return results

    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            pid = int(entry)
        except ValueError:
            continue
        argv = _read_proc_argv(pid)
        if argv:
            results.append((pid, argv))

    return results


def _send_signal(pid: int, sig: signal.Signals) -> None:
    """Send ``sig`` to ``pid``, ignoring ProcessLookupError (already gone)."""
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        logger.warning("Permission denied sending %s to PID %d", sig.name, pid)


def _pid_is_alive(pid: int) -> bool:
    """Return True if ``pid`` is alive (signal 0 probe)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — treat as alive.
        return True


def _wait_for_exit(pid: int, timeout_s: float) -> bool:
    """Poll until ``pid`` exits or ``timeout_s`` elapses.

    Returns True if the process exited within the window, False otherwise.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_is_alive(pid):
            return True
        time.sleep(0.25)
    return not _pid_is_alive(pid)


def _append_audit_sentinel(feature_id: str) -> None:
    """Append the reap sentinel to the feature's audit log in the DB."""
    sentinel = f"subagent_reaped_on_terminal={feature_id}"
    try:
        import json
        db.create_evidence(
            feature_id=feature_id,
            type="subagent_reap",
            content=json.dumps({"sentinel": sentinel}),
        )
    except Exception:
        pass
    logger.info("SENTINEL %s", sentinel)


def _append_audit_reap_failed(feature_id: str, pid: int, reason: str) -> None:
    """Append a reap-failure sentinel when a signal did not successfully kill the process."""
    sentinel = f"subagent_reap_failed={feature_id} pid={pid} reason={reason}"
    try:
        import json
        db.create_evidence(
            feature_id=feature_id,
            type="subagent_reap_failed",
            content=json.dumps({"sentinel": sentinel, "pid": pid, "reason": reason}),
        )
    except Exception:
        pass
    logger.warning("SENTINEL %s", sentinel)


def _query_stale_terminal_features() -> list[str]:
    """Return feature IDs in terminal states with dwell > 5 minutes."""
    sql = (
        "SELECT id FROM features "
        "WHERE status IN ('completed', 'needs_human', 'regression', 'failed') "
        "AND (julianday('now') - julianday(updated_at)) * 1440 > ? "
        "ORDER BY updated_at ASC"
    )
    with db.connect() as conn:
        cursor = conn.execute(sql, (_ORPHAN_STALE_MINUTES,))
        rows = cursor.fetchall()
    return [row[0] for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_subagent_pid_for_feature(feature_id: str) -> list[int]:
    """Return PIDs of live claude subagents tagged with ``feature_id``.

    Parses /proc/<pid>/cmdline as a NUL-split argv list and requires:
      - basename(argv[0]) == 'claude'
      - Some argv element (index ≥ 1) equals feature_id exactly

    PIDs ≤ 1 and os.getpid() are always excluded (safety contract).

    Args:
        feature_id: UUID string of the feature whose subagents to locate.

    Returns:
        List of integer PIDs (may be empty).
    """
    own_pid = os.getpid()
    matches: list[int] = []

    for pid, argv in _iter_candidate_pids():
        if pid <= 1 or pid == own_pid:
            continue
        if _argv_matches(argv, feature_id):
            matches.append(pid)

    return matches


def reap_subagent_for_feature(feature_id: str) -> list[int]:
    """Reap claude subagents associated with ``feature_id``.

    For each matching PID:
      1. Re-validates the cmdline immediately before signalling (TOCTOU defence).
      2. Sends SIGTERM.
      3. Waits up to 15 seconds for the process to exit.
      4. Sends SIGKILL if still alive, then re-validates the process is gone.
      5. Only counts the PID as reaped (and emits the audit sentinel) when
         the process is confirmed dead. Failures emit a distinct sentinel.

    Args:
        feature_id: UUID string of the just-terminated feature.

    Returns:
        List of integer PIDs confirmed dead. Empty when nothing matched.
    """
    pids = find_subagent_pid_for_feature(feature_id)
    if not pids:
        return []

    own_pid = os.getpid()
    reaped: list[int] = []

    for pid in pids:
        # --- TOCTOU guard: re-validate before SIGTERM ---
        argv_at_term = _read_proc_argv(pid)
        if argv_at_term is None or not _argv_matches(argv_at_term, feature_id):
            logger.debug(
                "PID %d no longer matches feature %s before SIGTERM; skipping",
                pid, feature_id[:8],
            )
            continue
        if pid <= 1 or pid == own_pid:
            continue

        logger.info(
            "Reaping subagent PID %d for terminal feature %s (SIGTERM)",
            pid, feature_id[:8],
        )
        _send_signal(pid, signal.SIGTERM)

        exited = _wait_for_exit(pid, _SIGTERM_GRACE_SECONDS)

        if not exited:
            # --- TOCTOU guard: re-validate before SIGKILL ---
            argv_at_kill = _read_proc_argv(pid)
            if argv_at_kill is None or not _argv_matches(argv_at_kill, feature_id):
                logger.debug(
                    "PID %d no longer matches feature %s before SIGKILL; skipping",
                    pid, feature_id[:8],
                )
                continue

            logger.warning(
                "PID %d did not exit after %ds grace; sending SIGKILL for feature %s",
                pid, _SIGTERM_GRACE_SECONDS, feature_id[:8],
            )
            _send_signal(pid, signal.SIGKILL)

            # Verify the process is actually dead after SIGKILL.
            actually_gone = _wait_for_exit(pid, 2.0)
            if not actually_gone:
                _append_audit_reap_failed(feature_id, pid, "still_alive_after_sigkill")
                continue

        reaped.append(pid)

    if reaped:
        _append_audit_sentinel(feature_id)
    return reaped


def sweep_orphan_subagents() -> list[tuple[str, int]]:
    """Backstop sweep: reap subagents for features in terminal states > 5min.

    Catches handler-bypass paths (e.g. SIGKILL'd orchestrator restart
    mid-completion) where the completion handler never ran.

    Idempotent and safe to run concurrently with other reapers.

    Returns:
        List of (feature_id, pid) pairs that were reaped.
    """
    stale_features = _query_stale_terminal_features()
    if not stale_features:
        return []

    result: list[tuple[str, int]] = []
    for feature_id in stale_features:
        try:
            reaped_pids = reap_subagent_for_feature(feature_id)
            for pid in reaped_pids:
                result.append((feature_id, pid))
                logger.info(
                    "Orphan sweep reaped PID %d for stale terminal feature %s",
                    pid, feature_id[:8],
                )
        except Exception:
            logger.debug(
                "Orphan sweep failed for feature %s; skipping",
                feature_id[:8],
                exc_info=True,
            )

    return result
