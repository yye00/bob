"""SpawnWatchdog: timeout + heartbeat wrapper for long-running sub-agent processes.

Wraps a subprocess.Popen-compatible process. While the process runs:
- Emits a heartbeat event to .bob3/progress.jsonl every ``heartbeat_interval_s`` seconds.
- On wall-clock timeout, sends SIGTERM, waits ``sigkill_grace_s`` seconds, then SIGKILL.
- Records a ``spawn_timeout`` event in the progress log.
- On POSIX, uses killpg to kill the whole process group.

The default timeout is read from BOB3_CRITERION_EXEC_TIMEOUT (same env var used by
enhanced_verification), falling back to _DEFAULT_TIMEOUT_S.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bob3.convergence_checker import check_convergence, compare_by_name  # noqa: F401

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 3600          # 1 hour
_DEFAULT_HEARTBEAT_INTERVAL_S = 300  # 5 minutes
_DEFAULT_SIGKILL_GRACE_S = 30
_DEFAULT_PROGRESS_PATH = Path(".bob3") / "progress.jsonl"


def _read_timeout_from_env() -> int:
    """Return BOB3_CRITERION_EXEC_TIMEOUT as int, or _DEFAULT_TIMEOUT_S."""
    raw = os.environ.get("BOB3_CRITERION_EXEC_TIMEOUT")
    if not raw:
        return _DEFAULT_TIMEOUT_S
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_S
    return value if value > 0 else _DEFAULT_TIMEOUT_S


def _write_event(path: Path, event_type: str, feature_id: str, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event_type": event_type,
        "feature_id": feature_id,
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _kill_process_group(proc: Any) -> None:
    """Send SIGKILL to the process group on POSIX, fall back to proc.kill()."""
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except Exception:
        pass


class SpawnWatchdog:
    """Context manager that supervises a long-running subprocess.

    Usage::

        proc = subprocess.Popen(cmd, start_new_session=True)
        with SpawnWatchdog(proc=proc, feature_id="feat-xyz") as wdog:
            proc.wait()
        if wdog.timed_out:
            ...  # handle timeout

    Parameters
    ----------
    proc:
        A ``subprocess.Popen``-compatible object (must have ``.pid``,
        ``.terminate()``, ``.kill()``, ``.wait(timeout)``, ``.poll()``).
    timeout_s:
        Wall-clock timeout in seconds. ``None`` reads from
        ``BOB3_CRITERION_EXEC_TIMEOUT`` env var, defaulting to 3600s.
    feature_id:
        Feature identifier written into every progress event.
    progress_path:
        Path to the JSONL progress file. Defaults to ``.bob3/progress.jsonl``.
    heartbeat_interval_s:
        How often (seconds) to emit a heartbeat event.
    sigkill_grace_s:
        Seconds to wait after SIGTERM before sending SIGKILL.
    """

    def __init__(
        self,
        proc: Any,
        *,
        timeout_s: int | None = None,
        feature_id: str,
        progress_path: Path | None = None,
        heartbeat_interval_s: float = _DEFAULT_HEARTBEAT_INTERVAL_S,
        sigkill_grace_s: float = _DEFAULT_SIGKILL_GRACE_S,
    ) -> None:
        self._proc = proc
        self.timeout_s: int = timeout_s if timeout_s is not None else _read_timeout_from_env()
        self._feature_id = feature_id
        self._progress_path = progress_path if progress_path is not None else _DEFAULT_PROGRESS_PATH
        self._heartbeat_interval_s = heartbeat_interval_s
        self._sigkill_grace_s = sigkill_grace_s

        self.timed_out: bool = False
        self._stop_event = threading.Event()
        self._watchdog_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "SpawnWatchdog":
        self._stop_event.clear()
        self.timed_out = False
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            daemon=True,
            name=f"spawn-watchdog-{self._feature_id}",
        )
        self._watchdog_thread.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._stop_event.set()
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=max(self._sigkill_grace_s + 2, 5))
        return None  # do not suppress exceptions

    # ------------------------------------------------------------------
    # Internal watchdog loop (runs in a daemon thread)
    # ------------------------------------------------------------------

    def _watchdog_loop(self) -> None:
        deadline = _monotonic() + self.timeout_s
        next_heartbeat = _monotonic() + self._heartbeat_interval_s

        while not self._stop_event.is_set():
            now = _monotonic()

            # Emit heartbeat if due
            if now >= next_heartbeat:
                self._emit_heartbeat()
                next_heartbeat = now + self._heartbeat_interval_s

            # Check wall-clock timeout
            if now >= deadline:
                self._handle_timeout()
                return

            # Sleep until the next relevant event (heartbeat or deadline)
            sleep_until = min(next_heartbeat, deadline)
            remaining = sleep_until - _monotonic()
            if remaining > 0:
                self._stop_event.wait(timeout=min(remaining, 1.0))

    def _emit_heartbeat(self) -> None:
        logger.debug("SpawnWatchdog heartbeat for feature %s", self._feature_id)
        _write_event(
            self._progress_path,
            "heartbeat",
            self._feature_id,
            {"pid": self._proc.pid},
        )

    def _handle_timeout(self) -> None:
        logger.warning(
            "SpawnWatchdog: timeout (%ds) reached for feature %s (pid=%d); sending SIGTERM",
            self.timeout_s,
            self._feature_id,
            self._proc.pid,
        )
        self.timed_out = True

        # Record the timeout event before killing
        _write_event(
            self._progress_path,
            "spawn_timeout",
            self._feature_id,
            {
                "pid": self._proc.pid,
                "timeout_s": self.timeout_s,
            },
        )

        # SIGTERM first
        try:
            self._proc.terminate()
        except Exception:
            pass

        # Wait for graceful exit
        try:
            self._proc.wait(timeout=self._sigkill_grace_s)
            return  # process exited on SIGTERM — done
        except (TimeoutError, Exception):
            pass

        # SIGKILL if still alive
        logger.warning(
            "SpawnWatchdog: process %d did not exit after SIGTERM; sending SIGKILL",
            self._proc.pid,
        )
        _kill_process_group(self._proc)


# ---------------------------------------------------------------------------
# Monotonic clock helper (injectable in tests via monkeypatching)
# ---------------------------------------------------------------------------

def _monotonic() -> float:
    import time
    return time.monotonic()
