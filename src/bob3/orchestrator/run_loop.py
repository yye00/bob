"""Continuous orchestration loop for Bob3 (F069 + F109 + F072).

Implements the core build loop that continuously picks ready features
from the database, spawns Claude sub-agents to implement them, and
tracks progress until all features are completed or no more progress
can be made.

Execution model — SEQUENTIAL at the orchestrator level
-------------------------------------------------------
Bob3's orchestration loop runs features SEQUENTIALLY: at most one
top-level feature is in flight at any time. The main loop in ``run()``
picks a single ready feature, awaits ``execute_feature``, then loops.
There is no ``asyncio.gather`` or task fan-out across sibling features.

This is intentional, not a TODO:

1. SQLite WAL with a single writer — concurrent feature writers
   would serialize on the DB anyway, and we'd inherit lock-contention
   debugging on top.
2. Cost tracking and budget enforcement assume sequential cost
   accumulation. The single ``OrchestrationLoop._increment_cost`` method
   and ``budget_exceeded`` are checked once per iteration; concurrent
   features would race on the running total and could overshoot
   ``max_cost`` by N feature-budgets at once.
3. Failure isolation — a failed sibling shouldn't poison parallel
   peers. With features running one at a time, a failure cleanly
   updates state, possibly cascades, and the next iteration replans
   against the new state.

What IS supported is *recursive* sub-agent parallelism: a sub-agent
spawned by ``execute_feature`` may, via ``claude_executor.spawn_sub_agent``
and the Superpowers "subagent-driven-development" skill (F113), spawn
its own sub-agents to decompose internal work. That recursion is bounded
by the Claude Code SDK and is unrelated to the orchestrator-level loop,
which still dispatches exactly one top-level feature at a time.

If you are reading this expecting concurrent feature execution: it is
not implemented and not currently planned. Updating prose to claim
otherwise creates a false expectation; please don't.

F109 adds research mode integration:
- Before execution, checks if a feature needs research
- Spawns a research sub-agent via Perplexity MCP when needed
- Stores research results and increments research_iterations
- Then proceeds to normal implementation

F072 adds feature decomposition handling:
- Before execution, checks if a feature exceeds_size_limits
- Spawns a decomposer sub-agent to split the feature
- Creates child features from the decomposition result
- Links dependencies between child features
- Sets the parent feature status to pending_decomposition

Research triggers:
1. Feature description contains research_required=True (and research_iterations == 0)
2. Feature has failed 3+ times (and research_iterations == 0)

The loop runs until one of these termination conditions:
- All features are completed
- All remaining features are blocked/failed
- Budget is exceeded
- Graceful shutdown is requested (SIGINT/SIGTERM)

Shutdown handling — where it lives
----------------------------------
``OrchestrationLoop._install_signal_handlers`` installs an inline
flag-setting handler that simply sets ``self.shutdown_requested = True``.
The flag is then checked between feature iterations at the top of
``run()``; once observed, the loop stops the MCP server and returns
``LoopTermination.SHUTDOWN_REQUESTED``. The actual shutdown sequence
(checkpoint creation, marking features 'interrupted', MCP cleanup) lives
HERE in the loop, NOT in ``bob3.signal_handler.GracefulShutdownHandler``.

That handler class is currently retained only for its async-signal-safe
flag-setting primitive and the tests that pin that contract; its earlier
``_perform_shutdown`` method was unwired in production and has been
removed. If a future refactor wants to centralize the shutdown sequence
into a reusable handler, do it via dependency injection rather than the
previous hidden coupling.

KNOWN LIMITATION — Ctrl-C latency during sub-agent execution
------------------------------------------------------------
``self.shutdown_requested`` is only checked between feature iterations
in ``run()``. While ``await spawn_sub_agent(...)`` is in flight (which
can take 10-20 minutes for a real implementation sub-agent), the flag
is set by the signal handler but not acted on until the sub-agent
returns. Pressing Ctrl-C during a long sub-agent will set the flag
immediately and log a warning, but the loop will not actually stop
until the current sub-agent finishes (or the second Ctrl-C raises
SystemExit via the signal handler).

TODO: plumb a shutdown-requested callable into ``spawn_sub_agent`` so
the SDK message-consumption loop can cancel the client between message
events. That requires changes in ``claude_executor.py`` and is not done
here. As a stopgap, the loop logs a clear warning when shutdown is
observed, telling the user roughly how long they might have to wait.

Defense in depth — budget tampering by sub-agents (R5-003)
----------------------------------------------------------
Sub-agents are spawned by the Claude Code SDK with
``permission_mode=bypassPermissions`` and ``cwd=<workspace>``, which gives
them write access to anything in the workspace — including ``bob3.db`` if
it lives there. A malicious sub-agent could ``UPDATE projects SET
total_cost_usd = 0`` to reset the running cost and effectively disable
budget enforcement on the next iteration of the loop.

The orchestrator can't prevent the write (the trust model accepts that
sub-agents have FS access), but it can DETECT the tampering and refuse
to honor the lower value. The loop maintains an in-memory ``_expected_total_cost``
that is incremented on every ``db.update_project_cost`` call (routed
exclusively through ``_increment_cost``). When
``_refresh_project_cost_cache`` reloads the canonical DB total, it
compares to the expected total; if the DB total has DECREASED beyond a
small floating-point slack, the loop:

1. Logs a ``SECURITY:`` warning naming both totals and the suspected
   tampering.
2. Refuses to lower the in-memory cache: it clamps to the expected
   total instead.

This means a sub-agent zeroing out the DB cannot extend its own runtime
budget. As a hardened deployment, place ``bob3.db`` outside the workspace
via ``BOB3_DATABASE_PATH=/secure/path/bob3.db`` so sub-agents cannot
reach it at all — see the README "Security considerations" section.
"""

from __future__ import annotations

import asyncio
import collections
import enum
import errno
import fcntl
import json
import logging
import os
import pathlib
import re
import signal
import stat
import time
from typing import Any

from bob3 import db
from bob3.mcp_lifecycle import stop_mcp_server
from bob3.git_ops import (
    GitCommitError,
    GitHookFailedError,
    GitRepoError,
    commit_feature as git_commit_feature,
    get_status as git_get_status,
    revert_feature as git_revert_feature,
)
from bob3.models import Feature
from bob3.orchestrator.claude_executor import (
    ExecutionResult,
    SpawnResult,
    build_sub_agent_options,
    spawn_rca_agent,
    spawn_research_agent,
    spawn_sub_agent,
)
from bob3.orientation import update_progress_notes, wrap_prompt_with_orientation
from bob3.superpowers import (
    run_verification_checklist,
    should_use_subagents,
    should_use_tdd,
)

logger = logging.getLogger(__name__)


def _log_safe(s: str | None) -> str:
    """Sanitize a string for inclusion in a log line (R9-003).

    Feature names come from the spec YAML and ultimately from the user
    or from a sub-agent decomposition result. Both inputs are untrusted
    relative to the log stream: a name containing newline / carriage-return
    characters can spoof a fake log record by injecting a synthetic
    "feature completed" line into stdout / log files. Mitigated by
    escaping CR / LF before formatting.

    Returns ``""`` for ``None`` so callers don't have to special-case it.
    The escaping is reversible (``\\n`` / ``\\r`` literals) so the original
    name is still recoverable if the operator wants it, but it cannot
    forge a new log record.
    """
    return (s or "").replace("\n", "\\n").replace("\r", "\\r")


# Statuses that indicate a feature cannot make further progress
_TERMINAL_STATUSES = frozenset({
    "completed",
    "failed",
    "interrupted",
    "blocked_by_reviewer",
    "blocked_by_dependency",
    "needs_human",
    "resource_limited",
    "rolled_back",
    "regression",
    "pending_decomposition",
})

# Statuses that mean a feature is done (not just stuck)
_COMPLETED_STATUSES = frozenset({"completed", "pending_decomposition"})

# Statuses that mean a feature is blocked or failed (no more automatic progress)
_BLOCKED_STATUSES = frozenset({
    "failed",
    "interrupted",
    "blocked_by_reviewer",
    "blocked_by_dependency",
    "needs_human",
    "resource_limited",
    "rolled_back",
    "regression",
})


class LoopTermination(enum.Enum):
    """Reason the orchestration loop terminated."""

    ALL_COMPLETED = "all_completed"
    ALL_BLOCKED = "all_blocked"
    BUDGET_EXCEEDED = "budget_exceeded"
    SHUTDOWN_REQUESTED = "shutdown_requested"


# R10-015: Maximum number of free retries granted to a feature whose
# sub-agent died at process spawn time (duration_ms < 100, num_turns == 0).
# These transient failures should not consume the feature's
# refinement-attempt budget, but we still cap them to avoid an infinite
# loop when the local environment is permanently broken.
_MAX_SPAWN_RETRIES = 3

# R10-015: Threshold (in milliseconds) below which a result with
# num_turns == 0 is treated as a process-spawn-time failure rather than
# a substantive sub-agent error. The F013 incident showed
# duration_ms == 0; we allow a small margin (100 ms) for clock jitter
# and SDK setup overhead before classifying as "really ran".
_SPAWN_FAILURE_DURATION_MS = 100


def _looks_like_spawn_failure(result: "ExecutionResult") -> bool:
    """Return True when ``result`` looks like a process-spawn-time failure.

    A sub-agent that died before the message loop started has
    ``num_turns == 0`` and a sub-100ms ``duration_ms`` (typically 0).
    A sub-agent that ran 25 turns and errored has both fields populated.
    The two cases must be distinguished so the orchestrator only grants
    a free retry to the former (R10-015).
    """
    if not getattr(result, "is_error", False):
        return False
    duration = result.duration_ms or 0
    turns = result.num_turns or 0
    return turns == 0 and duration < _SPAWN_FAILURE_DURATION_MS


# ---------------------------------------------------------------
# Per-project advisory file lock
# ---------------------------------------------------------------
#
# Two concurrent ``bob3 run --all`` invocations from the same project
# would race on the database. ``busy_timeout`` keeps them from crashing,
# but the resulting interleaving is unpredictable: both processes would
# pick "ready" features, both would write status='executing', both would
# spawn sub-agents, and the eventual cascade order is whatever the OS
# scheduler decides. To prevent that we acquire an exclusive advisory
# lock on ``<workspace>/.bob3.lock`` at startup. If another process
# already holds the lock the second invocation prints a clear error and
# exits with code 1.

_BOB3_LOCK_FILENAME = ".bob3.lock"


class AlreadyRunningError(RuntimeError):
    """Raised when another ``bob3 run`` is already in progress.

    The CLI catches this and prints a friendly message before exiting
    with status 1. The exception message is suitable for direct display
    to the user.
    """


def _read_lock_pid(lock_path: pathlib.Path) -> int | None:
    """Read the holder PID from a lock file, or None if unreadable.

    R10-006: We write our PID into the lock file after acquiring it so
    a subsequent contended attempt can probe the holder with
    ``kill(pid, 0)`` and produce an actionable error message (or, with
    ``force_unlock=True``, recover automatically from a truly stale lock).
    """
    try:
        contents = lock_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not contents:
        return None
    try:
        return int(contents.split()[0])
    except (ValueError, IndexError):
        return None


def _pid_is_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` is alive (signal 0 probe).

    R10-006: ``os.kill(pid, 0)`` raises ProcessLookupError when the PID
    is not in the kernel's task table, PermissionError when the process
    exists but is owned by another user (still alive), and succeeds
    silently if the PID is alive and signalable.
    """
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


def acquire_run_lock(
    workspace: str | pathlib.Path,
    force_unlock: bool = False,
) -> Any:
    """Acquire a non-blocking exclusive advisory lock for ``bob3 run``.

    Opens (creates if necessary) ``<workspace>/.bob3.lock`` and tries to
    place an exclusive flock on it. On success, returns the open file
    handle — the caller MUST keep this handle alive for the duration of
    the run; closing it (or letting it be garbage collected) releases
    the lock. On contention raises ``AlreadyRunningError``.

    POSIX-only (uses ``fcntl.flock``). Bob3 explicitly does not support
    Windows in production, so we don't bother with an msvcrt fallback.

    Symlink-attack hardening (R5-002)
    ---------------------------------
    A sub-agent with workspace write access could replace ``.bob3.lock``
    with a symlink to ``/dev/null`` (or any other non-regular file) before
    the next ``bob3 run``. ``flock`` on a non-regular file's fd succeeds
    trivially because the kernel doesn't track exclusive locks on devices
    or unrelated paths the way it does on regular files — two concurrent
    ``bob3 run`` processes would then both pass the lock check and race
    on the database.

    Two defenses applied here:

    1. ``os.open(..., O_NOFOLLOW)`` refuses at open time if the path
       already exists as a symlink. The kernel returns ``ELOOP``; we
       translate that into ``AlreadyRunningError`` so the user gets a
       coherent message.
    2. After opening, we ``fstat`` the descriptor and check
       ``stat.S_ISREG(st.st_mode)``. If it isn't a regular file (e.g. a
       sub-agent replaced the lock with a fifo, a directory, or a device
       node before we got there), we refuse to use it.

    Both checks fire before any flock attempt, so no caller ever holds a
    lock against ``/dev/null``.

    Args:
        workspace: The project workspace directory (where ``.bob3.lock``
            lives). The directory must already exist; we don't try to
            create the workspace itself here, only the lock file inside
            it.

    Returns:
        The open file object holding the lock. Keep it alive — when the
        file is closed (explicitly or via GC) the lock is released.

    Raises:
        AlreadyRunningError: another process holds the lock, or the lock
            path was found to be a symlink / non-regular file (suggesting
            tampering by a sub-agent).
        OSError: any other I/O failure opening the lock file.
    """
    workspace_path = pathlib.Path(workspace) if workspace else pathlib.Path.cwd()
    # If the workspace directory doesn't exist, fall back to cwd so we
    # never crash with FileNotFoundError just because the project's
    # recorded workspace_path is bogus or hasn't been created yet
    # (common in tests and on the first ``bob3 run`` after a manual
    # workspace_path edit). The lock is still scoped per-process via the
    # filesystem, just rooted at cwd instead of an unreachable path.
    if not workspace_path.is_dir():
        logger.debug(
            "Lock workspace %s does not exist; falling back to cwd for .bob3.lock",
            workspace_path,
        )
        workspace_path = pathlib.Path.cwd()
    lock_path = workspace_path / _BOB3_LOCK_FILENAME

    # R5-002: open with O_NOFOLLOW so a symlink at ``.bob3.lock`` (e.g.
    # pointing at /dev/null) raises ELOOP instead of giving us a usable
    # fd we'd then flock-against-a-non-regular-file. We use os.open to
    # get the flag wired in, then wrap the fd with os.fdopen so the rest
    # of the function (and callers / release_run_lock) sees a normal
    # file object as before.
    open_flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, open_flags, 0o600)
    except OSError as exc:
        # ELOOP comes from O_NOFOLLOW hitting a symlink. Surface that as
        # an AlreadyRunningError with a tampering hint — letting it
        # propagate as a bare OSError would crash the CLI with no
        # actionable message.
        if getattr(exc, "errno", None) == errno.ELOOP:
            raise AlreadyRunningError(
                f"Lock path {lock_path} is a symlink — refusing to use it. "
                f"This usually means a sub-agent or external process "
                f"tampered with the lock; remove the symlink and try "
                f"again. (Possible tampering)"
            ) from exc
        raise

    # R5-002: verify the open fd refers to a regular file. A pre-existing
    # fifo / device / directory would have skipped the symlink check but
    # is still not a sound flock anchor.
    try:
        st = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise AlreadyRunningError(
            f"Lock path {lock_path} is not a regular file (st_mode={oct(st.st_mode)}). "
            f"Refusing to use it; remove it and try again. (Possible tampering)"
        )

    # Wrap the fd with a Python file object so the existing
    # release_run_lock() path (close-the-file-object) keeps working. The
    # mode "ab" matches the previous behaviour (no truncation, binary).
    try:
        fh = os.fdopen(fd, "ab")
    except OSError:
        os.close(fd)
        raise

    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        # R10-006: On contention, peek at the PID we wrote into the
        # lock file the last time it was acquired and check whether
        # that holder is still alive. ``flock`` is supposed to be
        # released on process exit by the kernel, but a still-running
        # grandchild that inherited the lock FD can keep it alive past
        # the original ``bob3 run`` — and on systemd-managed sessions
        # we have observed cases where this happens. Surface a more
        # actionable error in that case (and recover automatically if
        # the operator passed ``--force-unlock``).
        holder_pid = _read_lock_pid(lock_path)
        holder_alive = _pid_is_alive(holder_pid) if holder_pid is not None else True
        if not holder_alive:
            if force_unlock:
                # Truly stale — close our fd, remove the lock file, and
                # recurse once. If we still can't acquire it after that,
                # something's seriously wrong; don't loop.
                fh.close()
                try:
                    lock_path.unlink()
                except OSError:
                    logger.debug(
                        "Could not unlink stale lock file %s",
                        lock_path,
                        exc_info=True,
                    )
                logger.warning(
                    "Removed stale .bob3.lock (holder PID %s was dead)",
                    holder_pid,
                )
                # Recurse with force_unlock=False so a real concurrent
                # run still raises cleanly.
                return acquire_run_lock(workspace, force_unlock=False)
            fh.close()
            raise AlreadyRunningError(
                f"`.bob3.lock` exists but its holder PID {holder_pid} is "
                f"not running. The lock is stale (likely from a previous "
                f"run that was SIGKILLed or OOM-killed). To recover, "
                f"either re-run with `bob3 run --force-unlock ...` or "
                f"remove the lock file manually: rm {lock_path}"
            ) from exc
        fh.close()
        # Real concurrent run. Tell the user which PID is holding it
        # and how to recover if they're sure no other run is active.
        pid_hint = (
            f" (holder PID {holder_pid})" if holder_pid is not None else ""
        )
        raise AlreadyRunningError(
            f"Another `bob3 run` is already in progress for this project. "
            f"Refusing to start. (lock: {lock_path}){pid_hint} — "
            f"if no other bob3 run is actually running, remove the lock "
            f"file: rm {lock_path}"
        ) from exc
    except OSError:
        fh.close()
        raise

    # R10-006: Record our PID inside the lock file so a future
    # contended attempt can identify a stale lock. We truncate first
    # because the file was opened append-only ("ab") above; rewriting
    # the same fd avoids opening a second descriptor.
    try:
        os.lseek(fh.fileno(), 0, os.SEEK_SET)
        os.ftruncate(fh.fileno(), 0)
        fh.write(f"{os.getpid()}\n".encode("utf-8"))
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            # fsync may fail on some FS types — not worth aborting the
            # whole run for.
            logger.debug("fsync on .bob3.lock failed", exc_info=True)
    except OSError:
        # Best-effort. If we can't write the PID, the flock still
        # protects against concurrent runs; we just lose the
        # stale-lock detection nicety.
        logger.debug("Could not write PID to .bob3.lock", exc_info=True)

    return fh


def release_run_lock(lock_handle: Any) -> None:
    """Release a lock acquired by :func:`acquire_run_lock`.

    Best-effort: any errors are swallowed since by the time we are
    releasing the lock the run is over. Closing the file is what
    actually drops the flock; the explicit ``LOCK_UN`` is just a
    courtesy for clarity.
    """
    if lock_handle is None:
        return
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        logger.debug("flock LOCK_UN failed during release", exc_info=True)
    try:
        lock_handle.close()
    except Exception:
        logger.debug("lock file close failed during release", exc_info=True)


# ---------------------------------------------------------------
# Cost normalization (Max Pro / OAuth subscription handling)
# ---------------------------------------------------------------
#
# Claude Code Max Pro is a flat-fee OAuth subscription, so the SDK reports
# total_cost_usd=None for every result. If we silently pass None through to
# update_project_cost(), accumulated cost stays at 0.0 forever and budget
# enforcement becomes a no-op. To keep budgets meaningful, we fall back to
# a turn-count proxy: a small per-turn estimate that lets a runaway
# sub-agent still trip the budget guard.
#
# The proxy rate ($0.05/turn) is deliberately approximate; users can tune
# it via the BOB3_COST_PER_TURN_PROXY environment variable.

_DEFAULT_COST_PER_TURN_PROXY = 0.05


# ---------------------------------------------------------------
# Sub-agent execution wall-clock timeout
# ---------------------------------------------------------------
#
# ``max_turns=25`` bounds how many model turns a sub-agent will take, but
# does not bound wall-clock time: a single turn that hangs in a tool call
# (e.g. a stuck Puppeteer / browser MCP, an unresponsive subprocess) will
# park the orchestration loop indefinitely. We wrap the ``await
# spawn_sub_agent(...)`` call in ``execute_feature`` with
# ``asyncio.wait_for`` using this timeout so the loop can recover. On
# timeout the feature is marked ``interrupted`` and dependents are NOT
# cascaded; the next ``bob3 run`` resumes through the normal interrupted-
# work path.

_DEFAULT_FEATURE_TIMEOUT_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------
# Regression-detection toggle (R7-001)
# ---------------------------------------------------------------
#
# capture_pytest_snapshot is invoked twice per feature (before and after
# the sub-agent) and uses synchronous subprocess.run with a ~300s timeout.
# In environments where the workspace test suite is large, slow, or simply
# uninteresting from a regression-tracking standpoint, this overhead is
# unwanted. Operators can disable both snapshots (and therefore the entire
# regression-detection path) via BOB3_REGRESSION_DETECTION_ENABLED=0.
#
# The default is "enabled" because regression detection is wired into
# show-regressions / rollback (F051 / F052) and most operators want it on.

_REGRESSION_DETECTION_DEFAULT = True


def _regression_detection_enabled() -> bool:
    """Return True when regression-detection snapshots should run.

    Honours the ``BOB3_REGRESSION_DETECTION_ENABLED`` env var. Truthy
    values: ``1``, ``true``, ``yes``, ``on`` (case-insensitive). Falsy
    values: ``0``, ``false``, ``no``, ``off``. Anything unrecognised is
    treated as truthy with a warning so misconfigurations don't silently
    disable regression detection.
    """
    raw = os.environ.get("BOB3_REGRESSION_DETECTION_ENABLED")
    if raw is None:
        return _REGRESSION_DETECTION_DEFAULT
    normalized = raw.strip().lower()
    if normalized in ("0", "false", "no", "off"):
        return False
    if normalized in ("1", "true", "yes", "on"):
        return True
    logger.warning(
        "Unrecognised BOB3_REGRESSION_DETECTION_ENABLED=%r; treating as enabled",
        raw,
    )
    return _REGRESSION_DETECTION_DEFAULT


def _resolve_feature_timeout_seconds() -> float:
    """Read ``BOB3_FEATURE_TIMEOUT_SECONDS`` from the environment.

    Returns the configured timeout in seconds, falling back to
    ``_DEFAULT_FEATURE_TIMEOUT_SECONDS`` (3600) on any parse error or
    non-positive value. Kept as a small helper so tests can monkeypatch
    the env var per-test without poking at module-level constants.
    """
    raw = os.environ.get("BOB3_FEATURE_TIMEOUT_SECONDS")
    if raw is None:
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB3_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_FEATURE_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    if value <= 0:
        logger.warning(
            "Non-positive BOB3_FEATURE_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_FEATURE_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_FEATURE_TIMEOUT_SECONDS)
    return value


def _normalize_cost(cost_usd: float | None, num_turns: int | None = None) -> tuple[float, str]:
    """Normalize a possibly-missing cost into a budget-safe value.

    Claude Max Pro often returns cost_usd=None. To keep budget enforcement
    meaningful in that mode, fall back to a turn-count proxy: each turn
    is approximated as $0.05 (configurable via BOB3_COST_PER_TURN_PROXY).

    Returns (cost_to_record, source_label) where source_label is one of
    'sdk', 'turn_proxy', or 'zero'.
    """
    if cost_usd is not None and cost_usd >= 0:
        return float(cost_usd), "sdk"
    if num_turns is not None and num_turns > 0:
        try:
            proxy_per_turn = float(
                os.environ.get(
                    "BOB3_COST_PER_TURN_PROXY",
                    str(_DEFAULT_COST_PER_TURN_PROXY),
                )
            )
        except (TypeError, ValueError):
            proxy_per_turn = _DEFAULT_COST_PER_TURN_PROXY
        return num_turns * proxy_per_turn, "turn_proxy"
    return 0.0, "zero"


# Per-feature de-duplication for proxy log lines (avoid spam during a run).
#
# This used to be an unbounded module-level ``set[str]`` that grew for every
# feature ever logged across the lifetime of the process. In long-running
# orchestrator processes (or test suites that share the module) it would
# slowly leak memory. We now back it with a bounded FIFO so the membership
# check is still O(1) but the population is capped — when we hit the cap,
# the oldest entry is evicted, and that feature would simply re-log its
# proxy line if it appears again.
_PROXY_LOG_DEDUP_MAX_ENTRIES = 10000


class _BoundedFeatureIdSet:
    """A bounded ``set``-like container with FIFO eviction.

    Supports ``.add``, ``.discard``, ``__contains__``, ``__len__``, and
    ``clear``, which are all the operations the proxy-log dedup path and
    its tests rely on. Insertion order is tracked via a ``deque`` so that
    when capacity is exceeded the oldest entry is dropped from both the
    deque and the membership set in O(1).
    """

    __slots__ = ("_set", "_order", "_max_entries")

    def __init__(self, max_entries: int = _PROXY_LOG_DEDUP_MAX_ENTRIES) -> None:
        self._set: set[str] = set()
        self._order: collections.deque[str] = collections.deque()
        self._max_entries = max_entries

    def __contains__(self, item: object) -> bool:
        return item in self._set

    def __len__(self) -> int:
        return len(self._set)

    def __iter__(self):
        return iter(self._set)

    def add(self, feature_id: str) -> None:
        if feature_id in self._set:
            return
        self._set.add(feature_id)
        self._order.append(feature_id)
        # Evict oldest entries until we are back within capacity.
        while len(self._order) > self._max_entries:
            oldest = self._order.popleft()
            self._set.discard(oldest)

    def discard(self, feature_id: str) -> None:
        if feature_id not in self._set:
            return
        self._set.discard(feature_id)
        # Lazy-remove from order: cheap because eviction tolerates misses.
        try:
            self._order.remove(feature_id)
        except ValueError:
            pass

    def clear(self) -> None:
        self._set.clear()
        self._order.clear()


_PROXY_LOGGED_FEATURE_IDS: _BoundedFeatureIdSet = _BoundedFeatureIdSet()


# ---------------------------------------------------------------
# Pytest snapshot helpers (for regression detection — F051)
# ---------------------------------------------------------------
#
# A "snapshot" is a mapping ``test_nodeid -> bool`` (True == passed). We
# capture one snapshot BEFORE a feature's implementation lands and
# another AFTER verification passes; comparing the two via
# ``db.detect_regression`` reveals tests that used to pass and now fail.
#
# Implementation notes:
# - Uses ``-v --tb=no -q`` and parses per-test verdict lines from
#   pytest's verbose output. When pytest is unavailable, the workspace
#   is missing, or no verdict lines parse, we return ``None`` — callers
#   must treat None as "snapshot not available; skip regression detection".
# - We deliberately do NOT use ``--collect-only`` separately because it
#   doubles the runtime; we already learn the test list from the run.
# - Pytest verbose output looks like:
#       tests/test_foo.py::test_bar PASSED
#       tests/test_foo.py::test_baz FAILED
#   We parse those.
_PYTEST_VERDICT_RE = re.compile(
    r"^(?P<nodeid>\S+::[^\s]+)\s+(?P<verdict>PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\b"
)

_DEFAULT_SNAPSHOT_TIMEOUT_S = 300


def _snapshot_timeout_s() -> int:
    """Return the per-snapshot pytest timeout (seconds).

    Honors ``BOB3_SNAPSHOT_TIMEOUT`` if set; falls back to
    ``BOB3_TEST_RUN_TIMEOUT`` (the same env used by the verification
    pytest call), then to a 300s default.
    """
    for env_name in ("BOB3_SNAPSHOT_TIMEOUT", "BOB3_TEST_RUN_TIMEOUT"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            v = int(raw)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return _DEFAULT_SNAPSHOT_TIMEOUT_S


def capture_pytest_snapshot(
    workspace: str | None,
    *,
    test_dir: str = "tests",
) -> dict[str, bool] | None:
    """Run pytest in the workspace and return a per-test pass/fail snapshot.

    Args:
        workspace: Path to the project workspace. If empty / None, returns
            None (no snapshot possible).
        test_dir: Directory under workspace to test (defaults to "tests").

    Returns:
        ``dict[test_nodeid, passed_bool]`` on success, or ``None`` if the
        snapshot could not be captured (workspace missing, pytest absent,
        timeout, or no recognisable verdict lines).

    A test is "passed" when its verdict line is ``PASSED`` / ``XFAIL``
    / ``SKIPPED`` / ``XPASS``; only ``FAILED`` and ``ERROR`` count as
    failures (skips aren't regressions; xpass is unusual but not a
    regression).
    """
    if not workspace:
        return None
    import pathlib  # local import to avoid bringing pathlib into module top
    import subprocess

    ws = pathlib.Path(workspace)
    if not ws.exists() or not ws.is_dir():
        return None

    # Recursion guard: skip when workspace IS the bob3 repo itself, to
    # mirror the behaviour of superpowers._check_tests_pass.
    try:
        import bob3
        bob3_root = pathlib.Path(bob3.__file__).resolve().parents[2]
        ws_resolved = ws.resolve()
        if ws_resolved == bob3_root or bob3_root in ws_resolved.parents:
            logger.debug(
                "Skipping pytest snapshot: workspace is bob3 itself "
                "(self-test recursion guard)"
            )
            return None
    except Exception:
        logger.debug("snapshot recursion guard skipped", exc_info=True)

    target = ws / test_dir
    if not target.exists() or not target.is_dir():
        # No test directory — empty snapshot is not useful for
        # detect_regression. Return None so the caller skips.
        return None

    cmd = [
        "python",
        "-m",
        "pytest",
        target.relative_to(ws).as_posix(),
        "-v",
        "--tb=no",
        "--no-header",
        "--color=no",
        "-p",
        "no:cacheprovider",
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=_snapshot_timeout_s(),
            check=False,
        )
    except FileNotFoundError:
        logger.debug("pytest snapshot skipped: python interpreter missing")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(
            "pytest snapshot timed out in %s after %ss",
            ws, _snapshot_timeout_s(),
        )
        return None
    except (OSError, ValueError) as exc:
        logger.debug("pytest snapshot invocation failed: %s", exc)
        return None

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if (
        "No module named pytest" in stderr
        or "No module named 'pytest'" in stderr
    ):
        logger.debug("pytest snapshot skipped: pytest not installed")
        return None

    snapshot: dict[str, bool] = {}
    for line in stdout.splitlines():
        m = _PYTEST_VERDICT_RE.match(line)
        if not m:
            continue
        nodeid = m.group("nodeid")
        verdict = m.group("verdict")
        snapshot[nodeid] = verdict in ("PASSED", "XFAIL", "SKIPPED", "XPASS")

    if not snapshot:
        return None
    return snapshot


# ---------------------------------------------------------------
# Calibration tracking helpers (F019)
# ---------------------------------------------------------------
#
# Bob3 calibration tracks predicted confidence (pre-execution) vs actual
# outcome (passed verification or not) per ``task_class + confidence_bucket``.
# Issue R4-004 was that ``db.create_or_update_calibration`` was never
# called from the orchestrator — the ``calibration_data`` table stayed
# empty in production so ``show-calibration`` was vacuous and drift
# detection had no inputs.
#
# ``task_class`` assignment: feature-level execution doesn't carry an
# explicit task_class today (it is a per-task concept). We pick a stable
# coarse default of ``"implementation"`` since ``execute_feature`` spawns
# an implementation sub-agent. The function ``_feature_task_class`` is
# the seam where richer classification (e.g. "refactor" / "bug_fix" /
# "greenfield_impl" derived from the feature description) can be wired
# in later. Returning a single value today is intentional: the important
# property is that ``calibration_data`` starts getting rows so drift
# detection has data to work with.
_DEFAULT_TASK_CLASS_FEATURE = "implementation"


def _feature_task_class(feature: Feature) -> str:
    """Derive a calibration task_class label from a feature.

    Currently a stable coarse bucket: ``"implementation"``. See the module
    block-comment above for rationale. TODO(F019+): plug in a real
    classifier here.
    """
    return _DEFAULT_TASK_CLASS_FEATURE


def _record_feature_calibration(
    *,
    project_id: str,
    feature: Feature,
    passed: bool,
) -> None:
    """Record a calibration data point for a feature execution.

    Wraps :func:`db.create_or_update_calibration` so a single failure
    here cannot abort the loop. The ``expected_pass_rate`` is the
    feature's ``conf_impl_correctness`` at the time of execution.
    """
    try:
        confidence = float(feature.conf_impl_correctness or 0.0)
        bucket = db._confidence_to_bucket(confidence)
        db.create_or_update_calibration(
            project_id=project_id,
            task_class=_feature_task_class(feature),
            confidence_bucket=bucket,
            passed=passed,
            expected_pass_rate=confidence,
        )
    except Exception:
        logger.warning(
            "Failed to record calibration data for feature %s",
            feature.id,
            exc_info=True,
        )


def cascade_update_dependents(feature_id: str) -> list[str]:
    """Update dependent features when a feature is completed.

    Delegates to db.cascade_update_dependents (F123) which:
    1. Finds all features depending on the completed feature
    2. Checks if ALL their dependencies are completed
    3. Checks readiness_score >= threshold for their risk_category
    4. Transitions qualifying features from 'pending' to 'ready'

    Args:
        feature_id: The ID of the just-completed feature.

    Returns:
        List of feature IDs that were transitioned to 'ready'.
    """
    return db.cascade_update_dependents(feature_id)


# ---------------------------------------------------------------
# F072: Feature decomposition handling
# ---------------------------------------------------------------

DECOMPOSER_SYSTEM_PROMPT = (
    "You are a feature decomposition agent. Your job is to break down a "
    "large feature into smaller, independently implementable child features.\n\n"
    "You MUST respond with a JSON block (inside ```json fences) containing:\n"
    '  - "children": array of child feature objects, each with:\n'
    '    - "name": short feature name\n'
    '    - "description": what this child implements\n'
    '    - "acceptance_criteria": JSON string of acceptance criteria array\n'
    '    - "priority": integer (lower = higher priority)\n'
    '    - "risk_category": "low", "medium", or "high"\n'
    '  - "dependencies": array of dependency objects, each with:\n'
    '    - "from": index of the child that depends (0-based)\n'
    '    - "to": index of the child it depends on (0-based)\n\n'
    "Keep each child small enough to be implemented in a single session "
    "(< 500 lines, < 5 files, complexity < 8)."
)


def parse_decomposition_result(text: str) -> dict | None:
    """Parse decomposition agent response to extract children and dependencies.

    Looks for a JSON block (inside ```json fences or inline) containing
    a "children" array and optional "dependencies" array.

    Returns a dict with keys "children" and "dependencies", or None if
    parsing fails or children is empty.
    """
    # Try fenced JSON first: ```json ... ```
    fenced = re.search(r"```json\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    json_str = fenced.group(1) if fenced else None

    # Fall back to inline JSON: { ... "children" ... }
    if json_str is None:
        inline = re.search(r"\{[^{}]*\"children\"\s*:", text, re.DOTALL)
        if inline:
            # Try to find the full JSON object
            start = inline.start()
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        json_str = text[start : i + 1]
                        break

    if json_str is None:
        return None

    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    children = parsed.get("children")
    if not children or not isinstance(children, list) or len(children) == 0:
        return None

    dependencies = parsed.get("dependencies", [])
    if not isinstance(dependencies, list):
        dependencies = []

    return {
        "children": children,
        "dependencies": dependencies,
    }


async def handle_decomposition(
    *,
    project_id: str,
    feature: Feature,
    workspace: str | None = None,
) -> dict:
    """Decompose an oversized feature into smaller child features.

    Spawns a decomposer sub-agent to analyze the feature and produce
    a plan for splitting it into independently implementable children.
    Then creates the child features and links dependencies.

    Args:
        project_id: The project ID.
        feature: The oversized feature to decompose.
        workspace: Optional path to the project workspace. When supplied,
            ``build_sub_agent_options`` runs ``install_skills_to_workspace``
            and ``verify_skills_integrity`` against this directory before
            spawning the decomposer. This closes the R9-007 skill-poisoning
            window for the decomposer path.

            SECURITY TRADE-OFF: passing ``cwd`` also gives the decomposer
            sub-agent filesystem access to ``workspace`` (with the default
            ``bypassPermissions`` mode it can read/write any file under
            it). The decomposer is purely a planning agent — its prompt
            asks for a JSON output, not file edits — so the practical
            blast radius is small. The integrity check is what closes
            the chained-attack window where a prior malicious agent
            replaced a skill symlink in ``.claude/skills``.

    Returns:
        Dict with keys: success, children_created, cost_usd, error_message.
    """
    prompt = (
        f"Decompose this oversized feature into smaller, independently "
        f"implementable child features.\n\n"
        f"Feature: {feature.name}\n"
        f"Description: {feature.description or 'No description'}\n"
        f"Acceptance Criteria: {feature.acceptance_criteria or 'None specified'}\n"
        f"Size Justification: {feature.size_limit_justification or 'Exceeds size limits'}\n\n"
        f"Break this into 2-5 smaller features, each under 500 lines of code, "
        f"touching fewer than 5 files, and with complexity under 8.\n\n"
        f"Respond with a JSON block containing the children and their dependencies."
    )

    options = build_sub_agent_options(
        cwd=workspace or None,
        model="sonnet",
        max_turns=10,
        system_prompt=DECOMPOSER_SYSTEM_PROMPT,
    )

    spawn_result = await spawn_sub_agent(
        project_id=project_id,
        purpose="decompose_feature",
        prompt=prompt,
        target_type="feature",
        target_id=feature.id,
        options=options,
    )

    result = spawn_result.execution_result
    outcome = {
        "success": False,
        "children_created": 0,
        "cost_usd": result.total_cost_usd,
        # Surface num_turns so the caller can run cost normalization (the
        # turn-count proxy is needed when total_cost_usd is None on Max Pro
        # / OAuth subscriptions).
        "num_turns": result.num_turns,
        "error_message": None,
    }

    if result.is_error:
        outcome["error_message"] = result.error_message
        return outcome

    # Parse the decomposition result
    decomposition = parse_decomposition_result(result.text)
    if decomposition is None:
        outcome["error_message"] = "Failed to parse decomposition result"
        return outcome

    children_specs = decomposition["children"]
    dependencies = decomposition["dependencies"]

    # Create child features
    created_children = []
    for spec in children_specs:
        child = db.create_child_feature(
            parent_feature_id=feature.id,
            project_id=project_id,
            name=spec.get("name", f"Child of {feature.name}"),
            description=spec.get("description"),
            acceptance_criteria=spec.get("acceptance_criteria"),
            status="ready",
            priority=spec.get("priority", feature.priority),
            risk_category=spec.get("risk_category", feature.risk_category),
        )
        # Set readiness high so children are immediately ready
        db.update_feature(
            child.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
            readiness_score=0.85,
        )
        created_children.append(child)

    # Link dependencies between children
    for dep in dependencies:
        from_idx = dep.get("from")
        to_idx = dep.get("to")
        if (
            isinstance(from_idx, int)
            and isinstance(to_idx, int)
            and 0 <= from_idx < len(created_children)
            and 0 <= to_idx < len(created_children)
            and from_idx != to_idx
        ):
            db.add_feature_dependency(
                feature_id=created_children[from_idx].id,
                depends_on_feature_id=created_children[to_idx].id,
            )

    # Update parent status
    db.update_feature(feature.id, status="pending_decomposition")

    outcome["success"] = True
    outcome["children_created"] = len(created_children)

    logger.info(
        "Decomposed feature %s into %d children",
        feature.id,
        len(created_children),
    )

    return outcome


# ---------------------------------------------------------------
# F109: Research mode helpers
# ---------------------------------------------------------------

_RESEARCH_REQUIRED_MARKER = "research_required=True"

# R10-010: Lowered from 3 → 2 after an examples/04_swedish_circle e2e run
# spent two consecutive 1-hour feature timeouts on F009 before the
# previous threshold of 3 would have fired research. After 2 failures
# (vs 3), research becomes more responsive — by failure 2 we've already
# burned ~2× the feature's expected cost; an expensive V&V feature needs
# research sooner than a cheap one. Configurable via
# ``BOB3_FAILURE_THRESHOLD_FOR_RESEARCH`` for operators who want the
# old behaviour back (or a more aggressive 1).
_DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH = 2
_FAILURE_THRESHOLD_FOR_RESEARCH = _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH


def _resolve_failure_threshold_for_research() -> int:
    """Read ``BOB3_FAILURE_THRESHOLD_FOR_RESEARCH`` from the environment.

    Returns the configured threshold, falling back to
    ``_DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH`` (2) on any parse error or
    non-positive value. Kept as a small helper so tests can monkeypatch
    the env var per-test without poking at module-level constants.
    """
    raw = os.environ.get("BOB3_FAILURE_THRESHOLD_FOR_RESEARCH")
    if raw is None:
        return _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB3_FAILURE_THRESHOLD_FOR_RESEARCH=%r; using default %d",
            raw,
            _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH,
        )
        return _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH
    if value < 1:
        logger.warning(
            "Non-positive BOB3_FAILURE_THRESHOLD_FOR_RESEARCH=%r; using default %d",
            raw,
            _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH,
        )
        return _DEFAULT_FAILURE_THRESHOLD_FOR_RESEARCH
    return value


# R10-011: How much to drop confidence scores after each failed feature
# attempt. After 2 failures with the default of 0.15, a feature that
# started at 0.7 conf falls to 0.40 — below the 0.5 needs_research
# threshold — so Trigger 3 in ``needs_research`` re-fires on the third
# attempt regardless of the failure-count threshold. Configurable via
# ``BOB3_CONFIDENCE_DECAY_PER_FAILURE``.
_DEFAULT_CONFIDENCE_DECAY_PER_FAILURE = 0.15


def _resolve_confidence_decay_per_failure() -> float:
    """Read ``BOB3_CONFIDENCE_DECAY_PER_FAILURE`` from the environment.

    Returns the configured decay, falling back to
    ``_DEFAULT_CONFIDENCE_DECAY_PER_FAILURE`` (0.15) on any parse error
    or negative value. A decay of 0.0 disables confidence decay entirely.
    """
    raw = os.environ.get("BOB3_CONFIDENCE_DECAY_PER_FAILURE")
    if raw is None:
        return _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB3_CONFIDENCE_DECAY_PER_FAILURE=%r; using default %.2f",
            raw,
            _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE,
        )
        return _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE
    if value < 0:
        logger.warning(
            "Negative BOB3_CONFIDENCE_DECAY_PER_FAILURE=%r; using default %.2f",
            raw,
            _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE,
        )
        return _DEFAULT_CONFIDENCE_DECAY_PER_FAILURE
    return value


# R10-009: bound RCA wall-clock so a stuck RCA sub-agent cannot park
# the orchestration loop. Default 600s (10 minutes) is plenty for the
# hypothesis-only Phase 1-4 work the RCA prompt asks for; production
# deployments that want a longer window can raise this. Set very low
# (e.g., 1) in tests to short-circuit the SDK spawn entirely.
_DEFAULT_RCA_TIMEOUT_SECONDS = 600


def _rca_enabled() -> bool:
    """Whether the RCA wiring (R10-009) is active.

    Defaults to True in production. Tests that don't explicitly mock
    ``spawn_rca_agent`` should set ``BOB3_RCA_ENABLED=0`` to opt out
    rather than gate every assertion on a real SDK invocation. The
    autouse fixture in tests/conftest.py wires the default to "0" so
    pre-existing failure-path tests don't try to launch a real Claude
    sub-agent.
    """
    raw = os.environ.get("BOB3_RCA_ENABLED")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _resolve_rca_timeout_seconds() -> float:
    """Read ``BOB3_RCA_TIMEOUT_SECONDS`` from the environment.

    Returns the configured timeout, falling back to
    ``_DEFAULT_RCA_TIMEOUT_SECONDS`` (600) on any parse error or
    non-positive value.
    """
    raw = os.environ.get("BOB3_RCA_TIMEOUT_SECONDS")
    if raw is None:
        return float(_DEFAULT_RCA_TIMEOUT_SECONDS)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid BOB3_RCA_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_RCA_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_RCA_TIMEOUT_SECONDS)
    if value <= 0:
        logger.warning(
            "Non-positive BOB3_RCA_TIMEOUT_SECONDS=%r; using default %ss",
            raw,
            _DEFAULT_RCA_TIMEOUT_SECONDS,
        )
        return float(_DEFAULT_RCA_TIMEOUT_SECONDS)
    return value


def _decay_confidence_after_failure(feature_id: str) -> Feature | None:
    """Decrement confidence scores after a failed feature attempt.

    R10-011 fix: confidence scores never dropped between attempts, so
    the low-confidence ``needs_research`` trigger (Trigger 3) was
    effectively a one-shot. Lowering the scores after each failure
    means the next retry is more likely to trigger research even when
    the failure-count threshold (R10-010) hasn't fired yet.

    The decay amount is read from ``BOB3_CONFIDENCE_DECAY_PER_FAILURE``
    (default 0.15). Each of ``conf_impl_correctness``,
    ``conf_spec_understanding``, and ``readiness_score`` is decremented
    independently with a floor of 0.0.

    Returns the updated Feature, or None if the feature was not found
    or decay is disabled.
    """
    decay = _resolve_confidence_decay_per_failure()
    if decay <= 0.0:
        return None
    current = db.get_feature(feature_id)
    if current is None:
        return None
    new_impl = max(0.0, float(current.conf_impl_correctness) - decay)
    new_spec = max(0.0, float(current.conf_spec_understanding) - decay)
    new_ready = max(0.0, float(current.readiness_score) - decay)
    return db.update_feature(
        feature_id,
        conf_impl_correctness=new_impl,
        conf_spec_understanding=new_spec,
        readiness_score=new_ready,
    )


def count_feature_failures(feature_id: str, project_id: str) -> int:
    """Count failed implementation attempts for a feature."""
    return db.count_agent_runs(
        project_id=project_id,
        target_id=feature_id,
        purpose="implement_feature",
        status="failed",
    )


def needs_research(feature: Feature, project_id: str) -> bool:
    """Determine if a feature needs research before implementation.

    Research is triggered when:
    1. Feature description contains 'research_required=True' AND
       research_iterations is 0 (hasn't been researched yet)
    2. Feature has failed >= ``BOB3_FAILURE_THRESHOLD_FOR_RESEARCH``
       times (default 2; R10-010) AND research_iterations is 0
    3. Feature has low confidence (< 0.5) AND research_iterations is 0
       — confidence decays after each failed attempt (R10-011) so this
       trigger CAN re-fire on a retry.

    Returns False if the feature has already been researched
    (research_iterations >= 1).
    """
    # Already researched — don't re-research
    if feature.research_iterations >= 1:
        return False

    # Trigger 1: Explicit research_required marker in description
    if feature.description and _RESEARCH_REQUIRED_MARKER in feature.description:
        return True

    # Trigger 2: Feature has failed >= configured threshold (default 2)
    failure_count = count_feature_failures(feature.id, project_id)
    threshold = _resolve_failure_threshold_for_research()
    if failure_count >= threshold:
        return True

    # Trigger 3: Low confidence (< 0.5) indicating missing information
    # This proactively triggers research BEFORE attempting implementation
    if (feature.conf_impl_correctness < 0.5 or
        feature.conf_spec_understanding < 0.5 or
        feature.readiness_score < 0.5):
        logger.info(
            "Feature %s has low confidence (spec=%.2f, impl=%.2f, ready=%.2f), triggering research",
            feature.id[:8],
            feature.conf_spec_understanding,
            feature.conf_impl_correctness,
            feature.readiness_score,
        )
        return True

    return False


def handle_execution_result(
    *,
    project_id: str,
    feature: Feature,
    spawn_result: SpawnResult,
    shutdown_requested: bool = False,
    verification_passed: bool = True,
    verification_summary: str | None = None,
) -> dict[str, Any]:
    """Handle the result of executing a feature sub-agent.

    Performs all post-execution bookkeeping EXCEPT cost accounting:
    1. Parses the execution result (success/failure)
    2. Updates the feature status (completed/failed/interrupted/needs_human)
    3. Creates evidence artifacts from the execution output
    4. Returns the normalized cost so the caller can route it through
       ``OrchestrationLoop._increment_cost`` — the single canonical
       writer for project cost. This function NO LONGER calls
       ``db.update_project_cost`` itself (recurring pattern
       ``non-atomic-counter``).

    A feature is only marked 'completed' and dependents cascaded to 'ready'
    when BOTH the sub-agent succeeded AND verification passed. If the
    sub-agent succeeded but verification failed, the feature is marked
    'needs_human' and no cascade is performed.

    Args:
        project_id: The project ID.
        feature: The feature that was executed.
        spawn_result: The SpawnResult from the sub-agent.
        shutdown_requested: If True, errors result in 'interrupted' status.
        verification_passed: If False and the sub-agent succeeded, the
            feature is marked 'needs_human' and no cascade is performed.
        verification_summary: Optional human-readable summary of the
            verification result (recorded in the evidence payload).

    Returns:
        Dict with keys: success, cost_usd, cost_source, duration_ms,
        error_message, evidence_id, verification_passed. The caller is
        responsible for incrementing project cost via
        ``OrchestrationLoop._increment_cost(cost_usd, cost_source)``
        when ``cost_usd > 0``.
    """
    result = spawn_result.execution_result
    agent_run_id = getattr(spawn_result.agent_run, "id", None)

    # Normalize cost up front so budget tracking sees a real number even
    # when the SDK returns None (typical on Claude Max Pro / OAuth subs).
    normalized_cost, cost_source = _normalize_cost(
        result.total_cost_usd, result.num_turns
    )

    # Log proxy / zero-cost diagnostics once per feature to avoid spam.
    if cost_source == "turn_proxy" and feature.id not in _PROXY_LOGGED_FEATURE_IDS:
        logger.warning(
            "Using turn-count cost proxy for feature %s: $%.2f from %d turns",
            feature.id,
            normalized_cost,
            result.num_turns or 0,
        )
        _PROXY_LOGGED_FEATURE_IDS.add(feature.id)
    elif cost_source == "zero" and feature.id not in _PROXY_LOGGED_FEATURE_IDS:
        logger.warning(
            "Cost is zero for feature %s — budget enforcement disabled for this feature",
            feature.id,
        )
        _PROXY_LOGGED_FEATURE_IDS.add(feature.id)

    # Success is only "true success" when execution succeeded AND verification
    # passed; a verification failure on a successful sub-agent run should NOT
    # be reported as success (callers rely on this to avoid cascading).
    is_success = (not result.is_error) and verification_passed

    outcome: dict[str, Any] = {
        "success": is_success,
        "cost_usd": normalized_cost,
        "cost_source": cost_source,
        "duration_ms": result.duration_ms,
        "error_message": result.error_message if result.is_error else (
            f"Verification failed: {verification_summary}"
            if not verification_passed else None
        ),
        "evidence_id": None,
        "verification_passed": verification_passed,
    }

    # Step 2: Update feature status
    if result.is_error:
        if shutdown_requested:
            db.update_feature(feature.id, status="interrupted")
        else:
            db.update_feature(feature.id, status="failed")
    elif not verification_passed:
        # Sub-agent reported success but verification failed — do NOT mark
        # as completed and do NOT cascade dependents. This prevents
        # downstream features from being unlocked on unverified work.
        db.update_feature(feature.id, status="needs_human")
    else:
        # F123 + atomicity fix: combine the status flip and the dependent
        # cascade into a SINGLE DB transaction. Splitting them across two
        # connections opened a window where a crash between them would
        # leave the feature 'completed' but dependents stuck on 'pending'
        # forever (the resume scan only handled 'executing'/'interrupted').
        try:
            updated_features = db.complete_feature_and_cascade(feature.id)
            if updated_features:
                logger.info(
                    "Feature %s completion unlocked %d dependent feature(s): %s",
                    feature.id[:8],
                    len(updated_features),
                    ", ".join([f[:8] for f in updated_features])
                )

            # R9-006: When this feature is a child of a decomposed parent,
            # check whether its completion finishes the parent. The parent
            # was previously left at ``pending_decomposition`` forever
            # because nothing in the orchestration loop called
            # ``check_parent_completion`` — even though that helper exists
            # in db.py specifically for this purpose. If the parent
            # transitions to completed, we ALSO need to cascade ITS
            # dependents (siblings-of-the-parent that were waiting on it),
            # and walk further up in case of multi-level decomposition.
            child_id_for_parent_check = feature.id
            parent_id = feature.parent_feature_id
            while parent_id:
                if not db.check_parent_completion(child_id_for_parent_check):
                    break
                # Parent was just transitioned to 'completed' by
                # check_parent_completion; cascade ITS dependents and
                # continue walking up. We re-fetch from the DB so the
                # ``parent_feature_id`` field reflects the latest state.
                parent_feat = db.get_feature(parent_id)
                if parent_feat is None:
                    break
                parent_updates = db.complete_feature_and_cascade(parent_id)
                if parent_updates:
                    logger.info(
                        "Parent feature %s auto-completion unlocked %d "
                        "dependent feature(s): %s",
                        parent_id[:8],
                        len(parent_updates),
                        ", ".join([f[:8] for f in parent_updates]),
                    )
                # Walk up: the just-completed parent now plays the role
                # of "child" for the grandparent check.
                child_id_for_parent_check = parent_feat.id
                parent_id = parent_feat.parent_feature_id
        except Exception:
            # The atomic complete+cascade rolled back, so the feature is
            # NOT marked completed and dependents are still pending. The
            # recovery scan in OrchestrationLoop._resume_interrupted_work
            # will detect orphaned 'pending' features whose deps are all
            # completed on the next run; meanwhile, surface this clearly
            # in the outcome so the loop doesn't pretend success.
            logger.error(
                "Atomic complete+cascade failed for feature %s; "
                "feature was NOT marked completed (transaction rolled back)",
                feature.id,
                exc_info=True,
            )
            outcome["success"] = False
            outcome["error_message"] = (
                "Atomic complete+cascade transaction rolled back"
            )

    # Step 3: Create evidence artifact
    if result.is_error:
        evidence_type = "execution_error"
        evidence_content = json.dumps({
            "status": "interrupted" if shutdown_requested else "failed",
            "error_message": result.error_message,
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "agent_run_id": agent_run_id,
        })
    elif not verification_passed:
        evidence_type = "execution_error"
        evidence_content = json.dumps({
            "status": "needs_human",
            "error_message": f"Verification failed: {verification_summary}",
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "agent_run_id": agent_run_id,
        })
    else:
        evidence_type = "execution_output"
        evidence_content = json.dumps({
            "status": "completed",
            "output_text": result.text[:2000] if result.text else "",
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "cost_usd": result.total_cost_usd,
            "tool_uses": result.tool_uses,
            "agent_run_id": agent_run_id,
        })

    try:
        evidence = db.create_evidence(
            project_id=project_id,
            feature_id=feature.id,
            type=evidence_type,
            content=evidence_content,
        )
        outcome["evidence_id"] = evidence.id
    except Exception:
        logger.warning(
            "Failed to create evidence artifact for feature %s",
            feature.id,
            exc_info=True,
        )

    # Step 4: NOTE — project cost is NOT written here.
    #
    # The single canonical writer is ``OrchestrationLoop._increment_cost``,
    # called by the orchestration loop after this function returns. Routing
    # every cost write through one method retires the recurring
    # ``non-atomic-counter`` pattern (R1-003 / R2-001 / R5-010 / R6-001 /
    # R6-002 / R9-006): when this function used to issue the DB write
    # itself, the loop ALSO had to remember to mirror the delta into the
    # tamper-detection ``_expected_total_cost`` and refresh the cache —
    # and every new cost-bearing path was one ``forgot to do that`` away
    # from drift. Returning the normalized cost back to the caller and
    # letting ``_increment_cost`` perform write + mirror + refresh
    # together makes the next occurrence structurally impossible.
    return outcome


class OrchestrationLoop:
    """Continuous orchestration loop for building a project.

    Picks the next ready feature, spawns a sub-agent to implement it,
    awaits completion, updates status, and repeats until done.

    Features are processed strictly one at a time (sequential execution);
    see the module docstring for why. Sub-agents may internally spawn
    their own sub-agents (recursive parallelism via the Claude Code SDK),
    but this loop never has more than one top-level feature in flight.
    """

    def __init__(
        self,
        *,
        project_id: str,
        max_cost: float | None = None,
        workspace: str | None = None,
        fresh: bool = False,
        target_feature_id: str | None = None,
        force_unlock: bool = False,
    ) -> None:
        self.project_id = project_id
        self.max_cost = max_cost
        self.workspace = workspace or ""
        self.fresh = fresh
        self.target_feature_id = target_feature_id
        # R10-006: forwarded to ``acquire_run_lock``; lets operators
        # recover from a SIGKILLed run that left a stale ``.bob3.lock``.
        self.force_unlock = force_unlock
        self.features_completed: int = 0
        self.features_failed: int = 0
        # R5-009: wall-clock start time for the run, captured at the top
        # of ``_run_locked``. Used by the loop-level termination summary
        # log so the operator sees how long the entire run took.
        self._run_start_time: float | None = None
        self.shutdown_requested: bool = False
        self._current_feature: Feature | None = None
        # Set to True the first time we see a result with total_cost_usd=None.
        # Indicates we're running against a Max Pro / OAuth subscription where
        # the SDK does not report cost; budget enforcement falls back to the
        # turn-count proxy.
        self._cost_proxy_active: bool = False
        self._cost_proxy_warning_emitted: bool = False
        # Cached project cost values, used by ``budget_exceeded`` to avoid
        # opening a fresh SQLite connection on every loop iteration just to
        # read ``total_cost_usd``. The values are populated from the DB once
        # at startup (see ``_refresh_project_cost_cache``) and refreshed
        # after every cost-mutating call so the budget check sees the
        # latest total. With 200+ features × N retries the per-iteration
        # ``db.get_project`` was the loop's hottest read; caching collapses
        # it to one connection per cost write.
        self._project_total_cost: float = 0.0
        self._project_max_cost_usd: float | None = None
        # R5-003: tamper-detection running total. Mirrors every
        # ``db.update_project_cost(... cost_usd=X)`` call this loop issues
        # so that ``_refresh_project_cost_cache`` can detect a sub-agent
        # zeroing out the DB to bypass the budget. Initialized from the
        # DB total on construction so a resumed run keeps a coherent
        # baseline; ``_increment_expected_total_cost`` updates it.
        self._expected_total_cost: float = 0.0
        self._refresh_project_cost_cache(_priming=True)
        self._expected_total_cost = self._project_total_cost
        # R10-015: per-feature counter of free retries granted for
        # process-spawn-time failures (duration_ms < 100ms, num_turns == 0).
        # Capped at ``_MAX_SPAWN_RETRIES`` so a permanently broken local
        # environment cannot trigger an infinite loop. Keys are feature.id.
        self._spawn_failure_counts: dict[str, int] = {}

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the loop."""
        self.shutdown_requested = True
        logger.info("Shutdown requested for orchestration loop")

    def _maybe_warn_cost_proxy_active(self) -> None:
        """Emit a one-time loop-level warning when the cost proxy is active.

        Once we observe ANY result with total_cost_usd=None we know the SDK
        is not reporting cost (typical on Claude Max Pro / OAuth subs). If
        the user passed a max_cost, surface a clear warning explaining that
        budget enforcement is using the turn-count proxy. Logged once per
        loop instance so we don't spam the operator.
        """
        if not self._cost_proxy_active or self._cost_proxy_warning_emitted:
            return
        if self.max_cost is None:
            # No budget specified — nothing to enforce, nothing to warn about.
            self._cost_proxy_warning_emitted = True
            return
        try:
            proxy = float(
                os.environ.get(
                    "BOB3_COST_PER_TURN_PROXY",
                    str(_DEFAULT_COST_PER_TURN_PROXY),
                )
            )
        except (TypeError, ValueError):
            proxy = _DEFAULT_COST_PER_TURN_PROXY
        logger.warning(
            "Claude SDK is not reporting cost (likely Max Pro subscription). "
            "Budget enforcement is using a turn-count proxy at $%.2f/turn.",
            proxy,
        )
        self._cost_proxy_warning_emitted = True

    def _increment_expected_total_cost(self, delta: float) -> None:
        """Mirror a ``db.update_project_cost(... cost_usd=delta)`` call.

        Caller MUST invoke this immediately after issuing the DB write,
        with the SAME ``delta`` it passed to the DB. The expected total
        is the floor below which ``_refresh_project_cost_cache`` will
        not let the cache drop — see the module docstring's "Defense in
        depth — budget tampering" section for the threat model.

        Negative deltas are rejected: cost is monotonic by contract.

        Internal helper: the only caller is ``_increment_cost``. Do NOT
        call this directly from new code; route every cost write through
        ``_increment_cost`` so the DB write, expected-total bump, and
        cache refresh stay in lockstep.
        """
        if delta < 0:
            logger.error(
                "SECURITY: refusing to apply negative cost delta %.6f to "
                "expected total (cost is monotonic by contract)",
                delta,
            )
            return
        self._expected_total_cost += float(delta)

    def _increment_cost(self, normalized_cost: float, source: str) -> None:
        """Single canonical entry point for recording loop-level cost.

        This is the ONLY method that writes cost into the project. Every
        path that previously did ``db.update_project_cost(...)`` (the
        feature execution path inside ``handle_execution_result``, the
        research path, the decomposition path, plus any future cost-
        bearing sub-agent the loop orchestrates) MUST go through here.

        The structural reason: the loop used to maintain TWO trackers —
        ``self.total_cost`` (in-memory) and ``db.update_project_cost``
        (atomic DB column) — and every new cost-bearing code path had
        to remember which one to use. Reviewers kept finding paths that
        used the wrong one (R1-003, R2-001, R5-010, R6-001, R6-002,
        R9-006). Collapsing both writes behind one method makes the
        seventh occurrence structurally impossible: there is no second-
        class field to forget about.

        Steps performed atomically from the caller's point of view:
        1. ``db.update_project_cost`` — the canonical, atomic column
           write. SQLite serialises this against any concurrent writer,
           so the project total stays monotonic.
        2. ``_increment_expected_total_cost`` — bumps the tamper-detection
           floor (see ``_refresh_project_cost_cache``). Must happen with
           the SAME delta we just sent to the DB so a sub-agent zeroing
           the column gets caught on the next refresh.
        3. ``_refresh_project_cost_cache`` — reloads the cached total so
           ``budget_exceeded()`` and any code reading
           ``self._project_total_cost`` sees the post-write value
           without paying for a fresh SQLite connection.

        ``normalized_cost`` MUST already have been through ``_normalize_cost``
        (so Max Pro / OAuth subscriptions, which return ``cost_usd=None``,
        are accounted for via the turn-count proxy). A non-positive value
        is a no-op against all three steps.

        ``source`` is one of: ``"sdk"``, ``"turn_proxy"``, ``"zero"``. It
        is used for the once-per-loop proxy warning and is otherwise
        free-form for diagnostics. When ``source == "turn_proxy"`` we
        also flip ``self._cost_proxy_active`` so ``_maybe_warn_cost_proxy_active``
        surfaces the warning at the next safe point.
        """
        # Flag the proxy state regardless of the magnitude — even a
        # zero-magnitude proxy reading still tells us the SDK is not
        # reporting cost on this subscription tier.
        if source == "turn_proxy":
            self._cost_proxy_active = True
        if normalized_cost <= 0:
            return
        db.update_project_cost(
            project_id=self.project_id,
            cost_usd=normalized_cost,
        )
        self._increment_expected_total_cost(normalized_cost)
        self._refresh_project_cost_cache()

    def _refresh_project_cost_cache(self, _priming: bool = False) -> None:
        """Reload cached project cost values from the DB.

        Call this exactly when something has, or might have, mutated the
        project's ``total_cost_usd``. Specifically: after every successful
        ``db.update_project_cost`` issued by ``handle_execution_result``,
        the research path, and the decomposition path. ``budget_exceeded``
        reads the cache rather than re-fetching the project, which keeps
        the per-iteration overhead at zero new SQLite connections.

        On a missing project the cache stays at the previous values; this
        is safe because the loop simply will not advance past the next
        ``find_next_ready_feature`` if the project has been deleted out
        from under it.

        R5-003 tamper detection
        -----------------------
        After each refresh, the loaded DB total is compared against
        ``self._expected_total_cost`` — the in-memory running total of
        every cost increment THIS loop has issued. If the DB total has
        gone DOWN beyond a tiny floating-point slack, that means
        something outside the orchestrator (almost always: a sub-agent
        with workspace write access) has mutated the projects table to
        reduce ``total_cost_usd``. We log a SECURITY warning and clamp
        the in-memory cache to ``_expected_total_cost`` instead of the
        attacker-supplied lower value, so the next ``budget_exceeded``
        check honors the original budget.

        ``_priming=True`` is used by ``__init__`` for the first call,
        before the expected total has been seeded — that path skips the
        comparison so we don't compare against a default-zero baseline.
        """
        project = db.get_project(self.project_id)
        if project is None:
            return
        total = project.total_cost_usd
        if total is None:
            logger.warning(
                "Project %s has total_cost_usd=None; treating as 0.0 for budget check",
                self.project_id,
            )
            total = 0.0
        db_total = float(total)

        # Tamper detection: a sub-agent with workspace FS access can
        # ``UPDATE projects SET total_cost_usd = 0`` directly in bob3.db
        # to disable the budget guard on the next iteration. Detect any
        # decrease beyond floating-point slack and refuse to honor it.
        if not _priming and db_total + 1e-6 < self._expected_total_cost:
            logger.warning(
                "SECURITY: Project cost in DB reduced unexpectedly "
                "(db=%.2f, expected=%.2f); possible tampering. "
                "Refusing to lower budget.",
                db_total,
                self._expected_total_cost,
            )
            self._project_total_cost = self._expected_total_cost
        else:
            self._project_total_cost = db_total
            # If the DB total moved UP relative to our expected (e.g. a
            # peer process legitimately recorded cost we didn't issue),
            # bring the expected total along so future comparisons stay
            # consistent.
            if db_total > self._expected_total_cost:
                self._expected_total_cost = db_total

        self._project_max_cost_usd = project.max_cost_usd

    def budget_exceeded(self) -> bool:
        """Check if the budget has been exceeded.

        Reads the cached project total (``self._project_total_cost``) and
        compares it to BOTH the loop-level ``self.max_cost`` and the
        project-level ``self._project_max_cost_usd`` ceiling. Cost is
        tracked atomically via ``_increment_cost`` (the single method
        through which every loop cost write flows) and the cache is
        refreshed on every write — so the cache is the single source of
        truth for the loop, without paying for a fresh SQLite connection
        every iteration.

        Defensively coerces a missing/None project total to 0.0 — if cost
        normalization is bypassed somewhere and None lands in the DB, the
        budget check should not silently treat it as "infinite room".
        """
        project_total = self._project_total_cost or 0.0

        # Check loop-level budget against the DB-tracked project total.
        # There is no second-class in-memory accumulator any more; tests
        # that want to drive a synthetic running cost should set
        # ``self._project_total_cost`` (the cached canonical value) or
        # write directly through ``db.update_project_cost`` before
        # invoking the budget check.
        if self.max_cost is not None:
            if project_total >= self.max_cost:
                return True

        # Check project-level budget against the project's own max.
        if self._project_max_cost_usd:
            if project_total >= self._project_max_cost_usd:
                return True

        return False

    def find_next_ready_feature(self) -> Feature | None:
        """Find the next feature ready for implementation.

        Queries the features_ready view which checks:
        - status = 'ready'
        - readiness_score >= risk-category threshold
        - no active reviewer vetoes
        - all dependencies completed

        Returns the highest priority ready feature, or None if none are ready.
        """
        ready = db.get_ready_features(self.project_id)
        if not ready:
            return None
        return ready[0]

    def all_features_completed(self) -> bool:
        """Check if all features in the project are completed."""
        features = db.list_features(project_id=self.project_id)
        if not features:
            return True
        return all(f.status in _COMPLETED_STATUSES for f in features)

    def all_remaining_blocked(self) -> bool:
        """Check if all non-completed features are blocked or failed.

        Returns True if every feature is either completed or in a
        blocked/failed state, meaning no more automatic progress is possible.
        """
        features = db.list_features(project_id=self.project_id)
        if not features:
            return False
        for f in features:
            if f.status in _COMPLETED_STATUSES:
                continue
            if f.status not in _BLOCKED_STATUSES:
                return False
        return True

    async def _run_research(self, feature: Feature) -> SpawnResult | None:
        """Run a research sub-agent for a feature if research is needed.

        Spawns a Perplexity-enabled research agent, stores the results
        in the research_results table, increments research_iterations,
        and tracks cost.

        Returns the SpawnResult if research was performed, None otherwise.
        """
        if not needs_research(feature, self.project_id):
            return None

        logger.info(
            "Feature %s needs research, spawning research agent", feature.id
        )

        # Build a research query from the feature's name and description
        query = (
            f"Research for implementing: {feature.name}\n\n"
            f"Description: {feature.description or 'No description'}\n\n"
            f"Find relevant documentation, libraries, patterns, and examples."
        )

        research_result = await spawn_research_agent(
            project_id=self.project_id,
            query=query,
            purpose="feature_research",
            target_type="feature",
            target_id=feature.id,
            workspace=self.workspace or None,
        )

        # Track research cost (normalize so Max Pro / OAuth subscriptions,
        # which return None, still consume budget via the turn-count proxy).
        research_exec = research_result.execution_result
        research_cost, research_cost_source = _normalize_cost(
            research_exec.total_cost_usd, research_exec.num_turns
        )
        if research_cost_source == "turn_proxy":
            logger.warning(
                "Using turn-count cost proxy for research on feature %s: $%.2f from %d turns",
                feature.id,
                research_cost,
                research_exec.num_turns or 0,
            )
        elif research_cost_source == "sdk" and research_exec.total_cost_usd is None:
            # Defensive — should never happen but keep flag detection consistent.
            self._cost_proxy_active = True
        if research_exec.total_cost_usd is None:
            # Even when num_turns==0 (zero source), surface that cost data is absent.
            self._cost_proxy_active = True
        # All cost writes route through the single ``_increment_cost``
        # entry point: it issues the atomic DB write, mirrors the delta
        # into the tamper-detection floor, refreshes the cached total,
        # and flips ``_cost_proxy_active`` when source=="turn_proxy".
        # See ``non-atomic-counter`` recurring pattern in reviews/findings.yaml
        # — this is the structural fix that retired ``self.total_cost``.
        self._increment_cost(research_cost, research_cost_source)

        # Store research results in DB (even if research failed, record the attempt)
        findings = research_exec.text if not research_exec.is_error else None
        # agent_run_id may not exist in DB (e.g. during tests with mocked agents)
        agent_run_id = getattr(research_result.agent_run, "id", None)
        # R7-002: The fallback ``db.create_research_result`` (without
        # agent_run_id) is itself a DB write and can fail for reasons
        # unrelated to FK violations (disk full, schema drift, transient
        # SQLite lock). If both calls raise, the unhandled exception used
        # to crash the orchestration loop. Wrap the whole block so any
        # failure is logged and the loop continues — the research
        # findings are advisory; losing one row must not stop the run.
        try:
            try:
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                    agent_run_id=agent_run_id,
                )
            except Exception:
                # FK constraint may fail if agent_run record doesn't exist;
                # store without the agent_run_id reference
                db.create_research_result(
                    feature_id=feature.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                )
        except Exception as exc:
            logger.warning(
                "Failed to record research result for feature %s: %s; continuing",
                feature.id,
                exc,
                exc_info=True,
            )

        # Increment research_iterations
        updated_feature = db.get_feature(feature.id)
        new_iterations = (updated_feature.research_iterations if updated_feature else 0) + 1

        # Boost readiness after successful research
        # Research provides the missing information needed for implementation
        updates = {"research_iterations": new_iterations}
        if not research_exec.is_error and updated_feature:
            # Successful research boosts confidence/readiness
            # Set to 0.85 which meets thresholds for medium/low risk features
            updates["conf_spec_understanding"] = max(updated_feature.conf_spec_understanding, 0.85)
            updates["conf_impl_correctness"] = max(updated_feature.conf_impl_correctness, 0.85)
            updates["readiness_score"] = max(updated_feature.readiness_score, 0.85)
            logger.info(
                "Research completed for feature %s, boosting readiness to 0.85",
                feature.id[:8]
            )

        db.update_feature(feature.id, **updates)

        if research_exec.is_error:
            logger.warning(
                "Research for feature %s failed: %s",
                feature.id,
                research_exec.error_message,
            )
        else:
            logger.info(
                "Research for feature %s completed successfully", feature.id
            )

        return research_result

    # -----------------------------------------------------------------
    # R10-009: RCA wiring
    # -----------------------------------------------------------------
    # ``spawn_rca_agent`` exists in claude_executor.py with a full system
    # prompt and a passing F058 test suite, but had ZERO production call
    # sites until this method was added. The orchestration loop now
    # invokes RCA after a feature fails (past the first attempt, with a
    # 24h per-feature cooldown so a flapping feature doesn't burn budget
    # on repeated RCA spawns) and routes the recommendation back into
    # the loop.

    _RCA_COOLDOWN_SECONDS = 24 * 60 * 60  # 24h

    def _last_rca_run_at(self, feature_id: str) -> float | None:
        """Return UNIX timestamp of the most recent RCA evidence for a feature.

        Looks up evidence_artifacts of type ``rca_analysis`` for the
        feature and returns the latest ``created_at`` as a UNIX
        timestamp. Returns ``None`` when no RCA has run yet, so callers
        can treat ``None`` as "never run".
        """
        try:
            rows = db.query_evidence(feature_id=feature_id)
        except Exception:
            logger.debug(
                "Could not query RCA evidence for feature %s",
                feature_id,
                exc_info=True,
            )
            return None
        latest: float | None = None
        for ev in rows:
            if ev.type != "rca_analysis":
                continue
            ts: float | None = None
            created = ev.created_at
            if created is not None:
                try:
                    ts = created.timestamp()
                except Exception:
                    ts = None
            if ts is None:
                continue
            if latest is None or ts > latest:
                latest = ts
        return latest

    def _rca_cooldown_active(self, feature_id: str) -> bool:
        """True when the last RCA for this feature was less than 24h ago."""
        last = self._last_rca_run_at(feature_id)
        if last is None:
            return False
        return (time.time() - last) < self._RCA_COOLDOWN_SECONDS

    async def _maybe_run_rca(
        self,
        *,
        feature: Feature,
        result: ExecutionResult,
    ) -> dict[str, Any] | None:
        """Spawn an RCA sub-agent for a failed feature when criteria are met.

        Criteria (per R10-009 task):
        - ``feature.refinement_attempts >= 2`` (i.e. at least one PRIOR
          failure has already happened — the very first failure is too
          early to invoke RCA, since one-shot failures are common and
          the loop's normal retry path handles them at lower cost).
          Caller is expected to pass the post-``increment_refinement_attempts``
          value, so a count of 2 means the current failure is the
          second attempt. This matches the e2e scenario in R10-009
          where F009 timed out on attempt 2 after a 55-minute attempt 1.
        - No RCA has run for this feature in the last 24 hours.
        - The orchestration loop is not in budget exhaustion.

        On success, stores the RCA result as an evidence artifact of
        type ``rca_analysis`` (so ``_last_rca_run_at`` can find it) and
        returns the parsed RCA dict (``blame_target``,
        ``recommended_action``, ``root_cause``, etc.). Returns ``None``
        when RCA was skipped or failed.
        """
        # Gate 0: feature flag, primarily for tests that don't mock
        # ``spawn_rca_agent`` (and would otherwise launch a real SDK
        # subprocess). Defaults to True in production.
        if not _rca_enabled():
            return None

        # Gate 1: at least one PRIOR failure on the books (so this is
        # the second-or-later attempt). The caller passes the
        # post-increment refinement_attempts value.
        if feature.refinement_attempts < 2:
            return None

        # Gate 2: don't spam RCA on a flapping feature.
        if self._rca_cooldown_active(feature.id):
            logger.debug(
                "Skipping RCA for feature %s: 24h cooldown still active",
                feature.id,
            )
            return None

        # Gate 3: never spend post-budget budget on RCA.
        try:
            if self.budget_exceeded():
                logger.info(
                    "Skipping RCA for feature %s: budget exhausted",
                    feature.id,
                )
                return None
        except Exception:
            # If budget check raises, err on the side of running RCA —
            # it's cheap relative to the feature retry it might prevent.
            logger.debug(
                "budget_exceeded() raised during RCA gating",
                exc_info=True,
            )

        # Build a failure-evidence blob. Cap the body so the RCA prompt
        # stays bounded — sub-agent stdout can be megabytes of
        # diagnostics; the first ~4 KB is plenty for hypothesis work.
        evidence_text = (
            (result.text or "")[:4000]
            + (
                f"\n\n---\nerror_message: {result.error_message}"
                if result.error_message
                else ""
            )
        )
        error_message = (
            result.error_message
            or "Sub-agent reported is_error=True with no error_message"
        )

        # Bound the RCA spawn with its own wall-clock timeout so a stuck
        # tool call inside the RCA sub-agent cannot park the
        # orchestration loop. Configurable via ``BOB3_RCA_TIMEOUT_SECONDS``
        # (default 600s = 10 minutes — RCA is meant to be a quick
        # hypothesis pass, not another implementation budget).
        rca_timeout = _resolve_rca_timeout_seconds()
        try:
            rca_spawn = await asyncio.wait_for(
                spawn_rca_agent(
                    project_id=self.project_id,
                    failure_evidence=evidence_text,
                    error_type="feature_implementation_failure",
                    error_message=error_message,
                    target_type="feature",
                    target_id=feature.id,
                ),
                timeout=rca_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "spawn_rca_agent for feature %s exceeded %ss; "
                "continuing without RCA recommendation",
                feature.id,
                rca_timeout,
            )
            return None
        except Exception:
            logger.warning(
                "spawn_rca_agent crashed for feature %s; continuing without RCA",
                feature.id,
                exc_info=True,
            )
            return None

        rca_exec = rca_spawn.execution_result
        # Extract the parsed RCA fields; fall back to a synthetic dict
        # when the SDK errored or the parser couldn't find a JSON block.
        if rca_exec.is_error:
            rca: dict[str, Any] = {
                "blame_target": "unknown",
                "recommended_action": "investigate",
                "root_cause": (
                    "RCA sub-agent itself errored: "
                    + str(rca_exec.error_message or "unknown")
                )[:500],
            }
        else:
            from bob3.orchestrator.claude_executor import parse_rca_result
            rca = dict(parse_rca_result(rca_exec.text))

        # Record the RCA result as an evidence artifact so it shows up
        # alongside the feature's other evidence and so the cooldown
        # check (``_last_rca_run_at``) can find it on the next failure.
        try:
            db.create_evidence(
                project_id=self.project_id,
                feature_id=feature.id,
                type="rca_analysis",
                content=json.dumps({
                    "rca": rca,
                    "refinement_attempts": feature.refinement_attempts,
                    "agent_run_id": getattr(rca_spawn.agent_run, "id", None),
                    "rca_text": (rca_exec.text or "")[:4000],
                    "rca_is_error": rca_exec.is_error,
                    "rca_error_message": rca_exec.error_message,
                }),
            )
        except Exception:
            logger.warning(
                "Failed to record rca_analysis evidence for feature %s; "
                "continuing with the recommendation in memory",
                feature.id,
                exc_info=True,
            )

        # Route RCA cost through the canonical writer.
        rca_cost, rca_cost_source = _normalize_cost(
            rca_exec.total_cost_usd, rca_exec.num_turns
        )
        self._increment_cost(rca_cost, rca_cost_source)

        logger.info(
            "RCA for feature %s: blame=%s action=%s",
            feature.id[:8],
            rca.get("blame_target"),
            rca.get("recommended_action"),
        )
        return rca

    async def _force_research_for_feature(self, feature: Feature) -> None:
        """Run research on a feature even when ``needs_research`` is False.

        Used by the RCA wiring (R10-009) when an RCA returns
        ``recommended_action == "research"``. The feature has already
        failed at least once and RCA explicitly asked for research, so
        the standard threshold gates don't apply. We achieve "force"
        by temporarily resetting ``research_iterations`` to 0 if it
        was already incremented by an earlier mid-run research.
        Implementation note: ``_run_research`` already increments
        ``research_iterations`` on completion, so a forced research
        still gets recorded as one iteration.
        """
        # The simplest "force" is to call _run_research's body
        # unconditionally. We re-fetch the feature so we work against
        # the latest DB state.
        latest = db.get_feature(feature.id) or feature

        # Build the same query _run_research uses.
        query = (
            f"Research for implementing: {latest.name}\n\n"
            f"Description: {latest.description or 'No description'}\n\n"
            f"Find relevant documentation, libraries, patterns, and examples."
        )
        try:
            research_result = await spawn_research_agent(
                project_id=self.project_id,
                query=query,
                purpose="feature_research",
                target_type="feature",
                target_id=latest.id,
                workspace=self.workspace or None,
            )
        except Exception:
            logger.warning(
                "Force-research spawn failed for feature %s; continuing",
                feature.id,
                exc_info=True,
            )
            return

        research_exec = research_result.execution_result
        research_cost, research_cost_source = _normalize_cost(
            research_exec.total_cost_usd, research_exec.num_turns
        )
        self._increment_cost(research_cost, research_cost_source)

        findings = research_exec.text if not research_exec.is_error else None
        agent_run_id = getattr(research_result.agent_run, "id", None)
        try:
            try:
                db.create_research_result(
                    feature_id=latest.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                    agent_run_id=agent_run_id,
                )
            except Exception:
                db.create_research_result(
                    feature_id=latest.id,
                    project_id=self.project_id,
                    query=query,
                    findings=findings,
                )
        except Exception:
            logger.warning(
                "Failed to record forced-research result for feature %s",
                latest.id,
                exc_info=True,
            )

        # Increment research_iterations and (on success) restore confidence.
        post = db.get_feature(latest.id) or latest
        new_iters = (post.research_iterations or 0) + 1
        updates: dict[str, Any] = {"research_iterations": new_iters}
        if not research_exec.is_error:
            updates["conf_spec_understanding"] = max(
                post.conf_spec_understanding, 0.85
            )
            updates["conf_impl_correctness"] = max(
                post.conf_impl_correctness, 0.85
            )
            updates["readiness_score"] = max(post.readiness_score, 0.85)
        db.update_feature(latest.id, **updates)

    async def execute_feature(self, feature: Feature) -> SpawnResult:
        """Spawn a sub-agent to implement a feature.

        If the feature exceeds size limits (F072), a decomposer sub-agent
        is spawned to break it into smaller child features.

        If the feature needs research (F109), a research sub-agent is
        spawned first via Perplexity MCP. Then the implementation
        sub-agent is spawned with orientation context.

        Args:
            feature: The feature to implement.

        Returns:
            The SpawnResult from the sub-agent execution.
        """
        # Set feature to executing and track as current
        self._current_feature = feature
        db.update_feature(feature.id, status="executing")
        logger.info("Executing feature %s: %s", feature.id, _log_safe(feature.name))

        # F072: Check if feature exceeds size limits and needs decomposition
        if feature.exceeds_size_limits:
            logger.info(
                "Feature %s exceeds size limits, triggering decomposition",
                feature.id,
            )
            decomp_result = await handle_decomposition(
                project_id=self.project_id,
                feature=feature,
                workspace=self.workspace or None,
            )

            # R4-002 fix: route decomposition cost to the canonical project
            # total via the loop's single ``_increment_cost`` entry point.
            # Normalize so Max Pro / OAuth subscriptions (which return
            # cost_usd=None) still consume budget via the turn-count proxy.
            decomp_cost_raw = decomp_result.get("cost_usd")
            decomp_num_turns = decomp_result.get("num_turns")
            decomp_normalized, decomp_cost_source = _normalize_cost(
                decomp_cost_raw, decomp_num_turns
            )
            if decomp_cost_source != "turn_proxy" and decomp_cost_raw is None:
                # SDK reported no cost AND no usable turn proxy — still flag
                # so downstream consumers (CLI status / budget warnings)
                # know cost data is absent on this path. ``_increment_cost``
                # also flips the flag when source=="turn_proxy".
                self._cost_proxy_active = True
            self._increment_cost(decomp_normalized, decomp_cost_source)

            if decomp_result["success"]:
                logger.info(
                    "Feature %s decomposed into %d children",
                    feature.id,
                    decomp_result["children_created"],
                )
            else:
                # Decomposition failed — mark as needs_human
                db.update_feature(feature.id, status="needs_human")
                logger.warning(
                    "Decomposition of feature %s failed: %s",
                    feature.id,
                    decomp_result.get("error_message"),
                )

            # Return a synthetic SpawnResult for decomposition
            self._current_feature = None
            exec_result = ExecutionResult(
                text=f"Feature decomposed into {decomp_result.get('children_created', 0)} children",
                is_error=not decomp_result["success"],
                error_message=decomp_result.get("error_message") or "",
                duration_ms=0,
                num_turns=0,
                total_cost_usd=decomp_result.get("cost_usd"),
            )
            agent_run = type("_FakeRun", (), {"id": None})()
            return SpawnResult(execution_result=exec_result, agent_run=agent_run)

        # F114: Capture pre-execution git state for rollback reference
        commit_before: str | None = None
        if self.workspace:
            try:
                pre_status = git_get_status(workspace=self.workspace)
                commit_before = pre_status.get("sha") or None
            except Exception:
                logger.debug("Could not capture pre-execution git state")

        # F051 / R4-003 / R5-006 / R7-001: Capture a pre-execution test
        # snapshot so that, after verification passes, we can compare the test
        # verdicts and detect newly-failing tests caused by THIS feature.
        # ``capture_pytest_snapshot`` returns None when pytest can't be run
        # (no workspace, no test dir, pytest not installed, timeout, etc.);
        # the post-execution code only calls ``db.detect_regression`` when
        # both before and after snapshots are available.
        #
        # R5-006: ``capture_pytest_snapshot`` uses synchronous subprocess.run
        # with a 300s timeout, which would block the asyncio event loop for
        # the entire pytest run. Offload to a worker thread so the loop
        # remains responsive (signals, cancellation).
        #
        # R7-001: The pre-execution snapshot is wasted work when the feature
        # is going to be decomposed (we returned early above) OR when the
        # operator has disabled regression detection entirely via
        # BOB3_REGRESSION_DETECTION_ENABLED=0. In both cases, skip both the
        # before and after snapshots so we don't spend several minutes per
        # feature on data nobody will read.
        regression_enabled = _regression_detection_enabled()
        before_snapshot: dict[str, bool] | None = None
        if regression_enabled:
            before_snapshot = await asyncio.to_thread(
                capture_pytest_snapshot, self.workspace or None
            )

        # F109: Run research phase if needed
        await self._run_research(feature)

        # F113: Determine which Superpowers skills to enable
        enable_tdd = should_use_tdd(
            acceptance_criteria=feature.acceptance_criteria,
            description=feature.description,
            tdd_mode_override=feature.tdd_mode,  # Respect explicit YAML setting
        )
        enable_subagent = should_use_subagents(
            acceptance_criteria=feature.acceptance_criteria,
            estimated_files_touched=feature.estimated_files_touched,
            estimated_complexity=feature.estimated_complexity,
            sub_agent_mode_override=feature.sub_agent_mode,  # Respect explicit YAML setting
        )

        if enable_tdd:
            logger.info("Feature %s: TDD mode enabled", feature.id)
        if enable_subagent:
            logger.info("Feature %s: Sub-agent mode enabled", feature.id)

        # Build the prompt with orientation context
        task_prompt = (
            f"You are a Bob3 sub-agent implementing a feature.\n\n"
            f"Feature ID: {feature.id}\n"
            f"Feature: {feature.name}\n"
            f"Description: {feature.description or 'No description'}\n"
            f"Acceptance Criteria: {feature.acceptance_criteria or 'None specified'}\n\n"
            f"Workspace: {self.workspace}\n\n"
            f"Instructions:\n"
            f"1. Read the existing codebase to understand the project structure\n"
            f"2. Implement the feature as described\n"
            f"3. Write tests for the feature\n"
            f"4. Ensure all existing tests still pass\n"
            f"5. Do NOT create stub implementations - write real, functional code\n\n"
            f"When complete, summarize what you implemented and any tests you added.\n"
        )

        prompt = wrap_prompt_with_orientation(
            prompt=task_prompt,
            feature_id=feature.id,
            workspace=self.workspace,
            feature_name=feature.name,
            feature_description=feature.description,
            enable_tdd=enable_tdd,
            enable_verification=True,
            enable_subagent=enable_subagent,
        )

        options = build_sub_agent_options(
            cwd=self.workspace or None,
            model="sonnet",
            max_turns=25,
        )

        # Spawn the sub-agent, bounded by a wall-clock timeout so a stuck
        # tool call (e.g. a hung Puppeteer browser session) cannot park
        # the orchestration loop forever. Configurable via
        # ``BOB3_FEATURE_TIMEOUT_SECONDS``; default 1 hour.
        feature_timeout = _resolve_feature_timeout_seconds()
        try:
            spawn_result = await asyncio.wait_for(
                spawn_sub_agent(
                    project_id=self.project_id,
                    purpose="implement_feature",
                    prompt=prompt,
                    target_type="feature",
                    target_id=feature.id,
                    options=options,
                ),
                timeout=feature_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Feature %s exceeded BOB3_FEATURE_TIMEOUT_SECONDS=%ss; "
                "marking 'interrupted' and NOT cascading dependents",
                feature.id,
                feature_timeout,
            )
            # R5-007: ``asyncio.wait_for`` cancels the underlying task,
            # but the claude_code_sdk subprocess may not always honour
            # cancellation cleanly (depends on which tool call was in
            # flight). ``spawn_sub_agent`` makes a best-effort to close
            # the SDK stream on cancellation, but if the underlying
            # Node.js process is wedged in a syscall it can survive.
            # Surface a clear SECURITY warning so the operator can
            # inspect / clean up if needed.
            logger.warning(
                "SECURITY: Sub-agent for feature %s timed out; underlying "
                "claude Node.js process may still be running. Check "
                "`pgrep -f claude` and kill any orphaned PIDs if needed.",
                feature.id,
            )
            # Persist a synthetic evidence artifact so the operator can
            # tell the difference between "sub-agent crashed" and
            # "sub-agent ran past the timeout". Best-effort — never let an
            # evidence-write failure derail the timeout handling itself.
            try:
                db.create_evidence(
                    project_id=self.project_id,
                    feature_id=feature.id,
                    type="execution_timeout",
                    content=json.dumps({
                        "status": "interrupted",
                        "reason": "feature_wall_clock_timeout",
                        "timeout_seconds": feature_timeout,
                        "feature_id": feature.id,
                    }),
                )
            except Exception:
                logger.warning(
                    "Failed to record execution_timeout evidence for feature %s",
                    feature.id,
                    exc_info=True,
                )
            # Mark the feature 'interrupted' (not 'failed') so the F116
            # auto-resume path picks it up cleanly on the next run rather
            # than burning a refinement attempt on what is almost
            # certainly an infrastructure-level hang. Do NOT cascade
            # dependents — a timed-out feature has not produced verified
            # work, so its downstream peers must stay 'pending'.
            db.update_feature(feature.id, status="interrupted")
            self.features_failed += 1
            self._current_feature = None
            timeout_exec = ExecutionResult(
                text="",
                is_error=True,
                error_message=(
                    f"Feature timed out after {feature_timeout}s "
                    f"(BOB3_FEATURE_TIMEOUT_SECONDS)"
                ),
                duration_ms=int(feature_timeout * 1000),
                num_turns=0,
                total_cost_usd=None,
            )
            # R5-009: Emit a per-feature summary on the timeout path too,
            # so wall-clock-timeout features show up in the same log
            # format as normal completions / failures. Refinement attempts
            # are NOT incremented on timeout (see comment above on F116).
            logger.info(
                "Feature %s (%s) done: status=%s duration=%.1fs "
                "cost=$%.4f attempts=%d",
                feature.id[:8],
                _log_safe(feature.name),
                "interrupted",
                float(feature_timeout),
                0.0,
                feature.refinement_attempts,
            )
            agent_run = type("_FakeRun", (), {"id": None})()
            return SpawnResult(execution_result=timeout_exec, agent_run=agent_run)

        # F113 + R10-014: Run verification BEFORE marking the feature
        # completed so that a verification failure does NOT cascade
        # 'ready' status to dependent features. Verification runs even
        # when the sub-agent reported is_error=True — the workspace may
        # already contain correct work from an earlier attempt, in which
        # case the feature is genuinely done despite the sub-agent crash
        # (the F013 / PyQt6 case). Verification, not the sub-agent exit
        # status, is the source of truth.
        result = spawn_result.execution_result
        verification_passed: bool = True
        verification_summary: str | None = None
        verification_result: dict | None = None
        # Track whether the sub-agent actually reported an error before
        # we possibly clear it via the R10-014 reverification path. This
        # is needed for the spawn-time-failure detection (R10-015) and
        # for accurate logging.
        sub_agent_reported_error = bool(result.is_error)
        # Set if a git hook rejected the post-verification commit. When True,
        # the feature is reverted to 'needs_human' and dependent features must
        # NOT be cascaded as if the feature had completed successfully.
        git_hook_failed: bool = False

        if self.workspace:
            try:
                verification_result = run_verification_checklist(
                    workspace=self.workspace,
                    acceptance_criteria=feature.acceptance_criteria,
                    feature_description=feature.description,
                )
                verification_passed = bool(verification_result.get("passed", True))
                verification_summary = verification_result.get("summary")
                # R10-014: a "passed" result with no acceptance-criteria
                # check is NOT positive evidence that the feature's work
                # is done. The base verification checklist passes vacuously
                # for an empty workspace (tests not required, no source
                # to scan, no acceptance criteria to fail). Only promote
                # an erroring sub-agent's feature to ``completed`` when
                # the ``acceptance_criteria_met`` check is present AND
                # passed — that's the one check that actually proves
                # the spec is satisfied.
                _ac_check = next(
                    (
                        c
                        for c in verification_result.get("checks") or ()
                        if c.get("name") == "acceptance_criteria_met"
                    ),
                    None,
                )
                verification_substantive = bool(
                    _ac_check and _ac_check.get("passed")
                )
                if verification_passed:
                    if sub_agent_reported_error and verification_substantive:
                        # R10-014: workspace already contains correct work
                        # despite the sub-agent crash (typical pattern: an
                        # earlier attempt produced the artefacts; the
                        # current spawn died at process startup before
                        # discovering they're already there). Clear the
                        # error flags so handle_execution_result marks
                        # the feature 'completed' and cascades dependents.
                        logger.info(
                            "Sub-agent for feature %s reported error "
                            "(error_message=%r) but verification passes "
                            "against the existing workspace — treating as "
                            "completed (R10-014).",
                            feature.id,
                            result.error_message,
                        )
                        result.is_error = False
                        result.error_message = ""
                    elif sub_agent_reported_error:
                        # Verification passed vacuously — no
                        # ``acceptance_criteria_met`` check was recorded
                        # OR the criteria check did not pass. Without a
                        # positive substantive check we don't have
                        # evidence the workspace really contains the
                        # feature's work. Leave ``is_error`` alone so the
                        # failure path applies — better to retry / mark
                        # needs_human than to silently promote a crashed
                        # run to completed.
                        logger.info(
                            "Sub-agent for feature %s errored; verification "
                            "returned passed=True but no substantive "
                            "acceptance-criteria check was recorded "
                            "(summary=%r). Treating as a real failure to "
                            "avoid silent completion (R10-014 guard).",
                            feature.id,
                            verification_summary,
                        )
                    else:
                        logger.info(
                            "Feature %s passed verification checklist",
                            feature.id,
                        )
                else:
                    if sub_agent_reported_error:
                        logger.warning(
                            "Feature %s: sub-agent errored AND verification "
                            "failed — treating as a real failure: %s",
                            feature.id,
                            verification_summary,
                        )
                    else:
                        logger.warning(
                            "Feature %s failed verification checklist: %s",
                            feature.id,
                            verification_summary,
                        )
                        logger.error(
                            "Feature %s will be marked needs_human due to failed verification",
                            feature.id,
                        )
            except Exception as exc:
                logger.error(
                    "Verification crashed for feature %s; treating as failure (severity: needs human review)",
                    feature.id,
                    exc_info=True,
                )
                # A crash in the verification harness must NOT silently
                # promote the feature to completed — that would let buggy
                # implementations through any time pytest crashes / OOMs /
                # times out / fails to import. Treat as a hard failure and
                # surface it for human review via 'needs_human'.
                verification_passed = False
                verification_summary = (
                    f"Verification crashed: {type(exc).__name__}"
                )
                verification_result = {
                    "passed": False,
                    "summary": verification_summary,
                    "checks": [],
                }

        # F070: Handle execution result (status, evidence, cost).
        # When verification_passed=False and the sub-agent succeeded,
        # handle_execution_result marks the feature 'needs_human' and
        # skips the dependent cascade.
        outcome = handle_execution_result(
            project_id=self.project_id,
            feature=feature,
            spawn_result=spawn_result,
            shutdown_requested=self.shutdown_requested,
            verification_passed=verification_passed,
            verification_summary=verification_summary,
        )
        # Single canonical cost write: ``_increment_cost`` performs the
        # atomic ``db.update_project_cost``, mirrors the delta into
        # ``_expected_total_cost`` for tamper detection, and refreshes
        # the cached project total — all in one place. ``handle_execution_result``
        # no longer touches the DB for cost (recurring pattern
        # ``non-atomic-counter``: every cost-bearing path that wrote the
        # DB on its own turned into a drift bug).
        cost_recorded = float(outcome.get("cost_usd") or 0.0)
        cost_source = str(outcome.get("cost_source") or "sdk")
        self._increment_cost(cost_recorded, cost_source)

        # Store verification_checklist evidence only when verification
        # actually ran (i.e. sub-agent succeeded and workspace is set).
        if verification_result is not None:
            try:
                db.create_evidence(
                    project_id=self.project_id,
                    feature_id=feature.id,
                    type="verification_checklist",
                    content=json.dumps(verification_result),
                )
            except Exception:
                logger.debug(
                    "Could not store verification evidence for feature %s",
                    feature.id,
                )

        # Update loop-level counters
        if result.is_error:
            if self.shutdown_requested:
                self._create_interruption_checkpoint(feature, result)
                logger.info(
                    "Feature %s interrupted during graceful shutdown",
                    feature.id,
                )
            elif _looks_like_spawn_failure(result) and (
                self._spawn_failure_counts.get(feature.id, 0) < _MAX_SPAWN_RETRIES
            ):
                # R10-015: Sub-agent died at process spawn time
                # (duration_ms < 100ms, num_turns == 0). This is almost
                # always a transient SDK / MCP startup issue and should
                # NOT consume a refinement attempt — the sub-agent never
                # got a chance to do real work. Skip
                # ``increment_refinement_attempts``, the confidence decay
                # (R10-011), and the proxy-cost log bump; just leave the
                # feature at ``ready`` so the loop picks it up again on
                # the next iteration. Capped at ``_MAX_SPAWN_RETRIES`` so
                # a permanently broken local environment cannot create an
                # infinite loop.
                self._spawn_failure_counts[feature.id] = (
                    self._spawn_failure_counts.get(feature.id, 0) + 1
                )
                db.update_feature(feature.id, status="ready")
                logger.warning(
                    "Sub-agent for feature %s appears to have failed at "
                    "process spawn (duration_ms=%s, num_turns=%s). "
                    "Treating as transient; retrying without charging "
                    "refinement_attempts (free retry %d/%d). "
                    "error_message=%r",
                    feature.id,
                    result.duration_ms,
                    result.num_turns,
                    self._spawn_failure_counts[feature.id],
                    _MAX_SPAWN_RETRIES,
                    result.error_message,
                )
                # Skip the rest of the failure-handling path (no RCA,
                # no decay, no refinement increment).
                updated_feature = None
            else:
                # F071: Retry logic — check refinement attempts before giving up
                if _looks_like_spawn_failure(result):
                    logger.warning(
                        "Feature %s exceeded the %d-spawn-failure cap; "
                        "treating subsequent spawn-time errors as a real "
                        "failure to avoid an infinite retry loop.",
                        feature.id,
                        _MAX_SPAWN_RETRIES,
                    )
                updated_feature = db.increment_refinement_attempts(feature.id)

                # R10-011: Decay confidence so the low-confidence research
                # trigger (Trigger 3 in ``needs_research``) can re-fire on
                # the next attempt, even when the failure-count threshold
                # (R10-010) hasn't been crossed yet. Decay happens AFTER
                # ``increment_refinement_attempts`` so a fresh DB read is
                # consistent. Refresh the in-memory ``updated_feature``
                # after decay so subsequent log messages and RCA gating
                # see the latest values.
                decayed = _decay_confidence_after_failure(feature.id)
                if decayed is not None:
                    updated_feature = decayed

                # R10-009: Spawn an RCA sub-agent on every failure past the
                # first (gated by 24h cooldown + budget). RCA recommendations
                # short-circuit the normal retry path: ``research`` triggers
                # a forced research pass, ``decompose`` flags the feature as
                # too large, ``mark_needs_human``/``skip`` retire the feature
                # immediately, and any other action falls through to the
                # default retry/needs_human logic below.
                rca_result = await self._maybe_run_rca(
                    feature=updated_feature or feature, result=result
                )
                rca_action = (
                    rca_result.get("recommended_action") if rca_result else None
                )

                # ---- RCA short-circuits ----
                if rca_action in ("mark_needs_human", "skip", "escalate"):
                    db.update_feature(feature.id, status="needs_human")
                    self.features_failed += 1
                    logger.warning(
                        "Feature %s marked needs_human by RCA "
                        "(action=%s, blame=%s): %s",
                        feature.id,
                        rca_action,
                        (rca_result or {}).get("blame_target"),
                        (rca_result or {}).get("root_cause"),
                    )
                elif rca_action == "decompose":
                    db.update_feature(
                        feature.id,
                        exceeds_size_limits=True,
                        size_limit_justification=(
                            "RCA recommendation after failure: "
                            + str(
                                (rca_result or {}).get("root_cause")
                                or "feature too large to implement in one pass"
                            )
                        )[:500],
                        status="ready",
                    )
                    logger.info(
                        "Feature %s flagged for decomposition by RCA "
                        "(blame=%s)",
                        feature.id,
                        (rca_result or {}).get("blame_target"),
                    )
                elif rca_action in ("research", "clarify_spec"):
                    # Force a research pass even if normal triggers wouldn't fire.
                    await self._force_research_for_feature(
                        updated_feature or feature
                    )
                    if updated_feature is not None and not db.check_refinement_limit(
                        feature.id
                    ):
                        db.update_feature(feature.id, status="ready")
                        logger.info(
                            "Feature %s: RCA forced research; resetting "
                            "to ready for retry (attempt %d/%d)",
                            feature.id,
                            updated_feature.refinement_attempts,
                            updated_feature.max_refinement_attempts,
                        )
                    else:
                        self.features_failed += 1
                        logger.warning(
                            "Feature %s: RCA recommended research but "
                            "retry limit exhausted (%s/%s)",
                            feature.id,
                            updated_feature.refinement_attempts
                            if updated_feature
                            else "?",
                            updated_feature.max_refinement_attempts
                            if updated_feature
                            else "?",
                        )
                # ---- Default retry / exhaustion path ----
                elif (
                    updated_feature is not None
                    and not db.check_refinement_limit(feature.id)
                ):
                    # Under limit: reset to 'ready' so the loop retries this feature
                    db.update_feature(feature.id, status="ready")
                    logger.info(
                        "Feature %s failed (attempt %d/%d), resetting to ready for retry: %s",
                        feature.id,
                        updated_feature.refinement_attempts,
                        updated_feature.max_refinement_attempts,
                        result.error_message,
                    )
                else:
                    # At or over limit: mark as needs_human (done by increment_refinement_attempts)
                    # and count as a permanent failure
                    self.features_failed += 1
                    logger.warning(
                        "Feature %s failed and exhausted retries (%d/%d): %s",
                        feature.id,
                        updated_feature.refinement_attempts if updated_feature else "?",
                        updated_feature.max_refinement_attempts if updated_feature else "?",
                        result.error_message,
                    )
        elif not verification_passed:
            # Sub-agent succeeded but verification failed. Do NOT commit,
            # do NOT cascade, do NOT count as completed.
            self.features_failed += 1
            logger.error(
                "Feature %s failed verification: %s",
                feature.id,
                verification_summary,
            )
        else:
            # F114: Commit feature changes to git (only once verification passed)
            commit_sha: str | None = None
            if self.workspace:
                try:
                    commit_sha = git_commit_feature(
                        feature_id=feature.id,
                        message=feature.name,
                        workspace=self.workspace,
                        stage_all=True,
                    )
                except GitHookFailedError as exc:
                    # A pre-commit / commit-msg hook rejected our commit. The
                    # implementation may be valid (verification passed!) but
                    # something the hook checks for objects to it. Surface
                    # this for human review rather than silently moving on
                    # as if the feature were committed and complete.
                    git_hook_failed = True
                    hook_output = (exc.stderr or exc.stdout or str(exc)).strip()
                    logger.warning(
                        "Git hook rejected commit for feature %s "
                        "(rc=%s); marking needs_human. Hook output:\n%s",
                        feature.id,
                        exc.returncode,
                        hook_output,
                    )
                    # Record evidence so the operator can see the hook output
                    # alongside the feature.
                    try:
                        db.create_evidence(
                            project_id=self.project_id,
                            feature_id=feature.id,
                            type="git_hook_failure",
                            content=json.dumps({
                                "feature_id": feature.id,
                                "returncode": exc.returncode,
                                "command": exc.command,
                                "stderr": exc.stderr,
                                "stdout": exc.stdout,
                            }),
                        )
                    except Exception:
                        logger.warning(
                            "Failed to record git_hook_failure evidence for "
                            "feature %s",
                            feature.id,
                            exc_info=True,
                        )
                    # Override the 'completed' status that
                    # handle_execution_result wrote earlier — verification
                    # passed but we couldn't get the change committed, so
                    # this needs human attention. handle_execution_result
                    # already ran the F123 cascade which may have flipped
                    # dependents from 'pending' to 'ready'; we need to roll
                    # those back too. Both writes happen atomically in a
                    # single transaction (db.rollback_feature_cascade) so a
                    # crash during rollback can never leave the project in
                    # a half-rolled-back state (some dependents back to
                    # 'pending', others stuck at 'ready').
                    try:
                        db.rollback_feature_cascade(
                            feature.id, target_status="needs_human"
                        )
                    except Exception:
                        logger.error(
                            "Failed to roll back cascade for feature %s "
                            "after git hook failure",
                            feature.id,
                            exc_info=True,
                        )
                except GitRepoError as exc:
                    # Workspace isn't a git repo. Not a build failure — just
                    # log cleanly and continue without committing.
                    logger.info(
                        "Skipping git commit for feature %s: workspace is "
                        "not a git repository (%s)",
                        feature.id,
                        exc,
                    )
                except GitCommitError as exc:
                    # Other git failure (e.g. git binary broken, IO error
                    # during add). Not a hook rejection — surface it loudly
                    # and record evidence, but don't unwind the 'completed'
                    # status the way a hook rejection does.
                    logger.error(
                        "Unexpected git error committing feature %s "
                        "(rc=%s): %s",
                        feature.id,
                        exc.returncode,
                        (exc.stderr or exc.stdout or str(exc)).strip(),
                    )
                    try:
                        db.create_evidence(
                            project_id=self.project_id,
                            feature_id=feature.id,
                            type="git_commit_error",
                            content=json.dumps({
                                "feature_id": feature.id,
                                "returncode": exc.returncode,
                                "command": exc.command,
                                "stderr": exc.stderr,
                                "stdout": exc.stdout,
                            }),
                        )
                    except Exception:
                        logger.warning(
                            "Failed to record git_commit_error evidence "
                            "for feature %s",
                            feature.id,
                            exc_info=True,
                        )
                except Exception:
                    # Truly unexpected (non-GitCommitError) — keep prior
                    # permissive behaviour so we don't crash the loop, but
                    # log loudly with full traceback.
                    logger.error(
                        "Unexpected non-git exception during commit for "
                        "feature %s",
                        feature.id,
                        exc_info=True,
                    )

            if git_hook_failed:
                # Hook rejection means the feature isn't really done.
                self.features_failed += 1
                logger.error(
                    "Feature %s blocked by git hook rejection; needs human review",
                    feature.id,
                )
            else:
                self.features_completed += 1
                logger.info("Feature %s completed successfully", feature.id)

        # Cost was written above via ``self._increment_cost(...)`` — the
        # single canonical writer. There is no longer any in-memory mirror
        # to bump here; ``budget_exceeded()`` reads ``self._project_total_cost``
        # which ``_increment_cost`` already refreshed. We still flip the
        # proxy flag so downstream consumers (CLI status, run() warning)
        # can surface that the SDK is not reporting cost.
        if result.total_cost_usd is None:
            self._cost_proxy_active = True

        # F108: Update progress notes after each sub-agent session
        if self.workspace:
            try:
                if result.is_error:
                    progress_outcome = (
                        "interrupted" if self.shutdown_requested else "failed"
                    )
                    blockers = result.error_message
                elif not verification_passed:
                    progress_outcome = "failed"
                    blockers = f"Verification failed: {verification_summary}"
                else:
                    progress_outcome = "completed"
                    blockers = None
                update_progress_notes(
                    workspace=self.workspace,
                    feature_id=feature.id,
                    feature_name=feature.name,
                    outcome=progress_outcome,
                    duration_ms=result.duration_ms,
                    num_turns=result.num_turns,
                    cost_usd=result.total_cost_usd,
                    blockers=blockers,
                )
            except Exception:
                logger.debug(
                    "Failed to update progress notes for feature %s",
                    feature.id,
                    exc_info=True,
                )

        # F051 / R4-003: Regression detection.
        #
        # If verification passed AND the feature was committed without a
        # hook rejection, capture an "after" pytest snapshot and compare it
        # to the pre-execution snapshot. Any test that was passing before
        # this feature ran but is failing now is, by definition, a regression
        # caused by THIS feature. ``db.detect_regression`` records the event
        # in the ``regression_events`` table so ``show-regressions`` and the
        # rollback path (F052) actually see something.
        #
        # We deliberately gate this on the success path (verification passed
        # AND no git hook rejection) — if the feature didn't really land,
        # there's no causing-feature to attribute regressions to.
        feature_landed = (
            (not result.is_error)
            and verification_passed
            and not git_hook_failed
        )
        if feature_landed and before_snapshot is not None and regression_enabled:
            # R5-006: offload the post-execution pytest run to a worker
            # thread so the event loop stays responsive during the snapshot.
            after_snapshot = await asyncio.to_thread(
                capture_pytest_snapshot, self.workspace or None
            )
            if after_snapshot is not None:
                try:
                    event = db.detect_regression(
                        project_id=self.project_id,
                        causing_feature_id=feature.id,
                        before_results=before_snapshot,
                        after_results=after_snapshot,
                    )
                    if event is not None:
                        logger.warning(
                            "Regression detected after feature %s: "
                            "affected_feature=%s, affected_tests=%s",
                            feature.id,
                            event.affected_feature_id,
                            event.affected_tests,
                        )
                        try:
                            db.create_evidence(
                                project_id=self.project_id,
                                feature_id=feature.id,
                                type="regression_detected",
                                content=json.dumps({
                                    "regression_event_id": event.id,
                                    "causing_feature_id": feature.id,
                                    "affected_feature_id": event.affected_feature_id,
                                    "affected_tests": event.affected_tests,
                                }),
                            )
                        except Exception:
                            logger.warning(
                                "Failed to record regression_detected evidence "
                                "for feature %s",
                                feature.id,
                                exc_info=True,
                            )
                except Exception:
                    # Detection / DB error must not abort the loop.
                    logger.warning(
                        "detect_regression raised for feature %s; "
                        "continuing without regression record",
                        feature.id,
                        exc_info=True,
                    )

        # F019 / R4-004: Record a calibration data point for this feature.
        #
        # We log predicted confidence (pre-execution ``conf_impl_correctness``)
        # vs actual outcome (passed verification or not). This populates the
        # ``calibration_data`` table that ``show-calibration`` reads and that
        # drift-detection (F050) consumes; previously the table was always
        # empty in production.
        #
        # ``passed`` for calibration purposes means "the feature actually
        # landed cleanly": sub-agent didn't error, verification passed, AND
        # no git hook rejection. Anything else is treated as a failed
        # prediction, regardless of which step blew up. This may
        # over-report failures (a git hook rejection isn't really a
        # confidence-calibration failure of the implementation), but
        # under-reporting them would let buggy work erode the calibration
        # signal silently. Choice intentional; revisit if it skews drift.
        _record_feature_calibration(
            project_id=self.project_id,
            feature=feature,
            passed=feature_landed,
        )

        # R5-009: Emit a structured per-feature summary so operators can
        # see the cost / duration / outcome of each feature in the log
        # without reconstructing it from individual lines. Re-fetch the
        # feature so ``status`` and ``refinement_attempts`` reflect any
        # mutations made by handle_execution_result, retry logic, or git
        # hook rollback above. Falls back to the in-memory feature if
        # the row vanished mid-run (deleted by a parallel admin tool).
        final_feature = db.get_feature(feature.id) or feature
        normalized_cost = float(outcome.get("cost_usd") or 0.0)
        duration_ms = result.duration_ms or 0
        logger.info(
            "Feature %s (%s) done: status=%s duration=%.1fs "
            "cost=$%.4f attempts=%d",
            feature.id[:8],
            _log_safe(feature.name),
            final_feature.status,
            duration_ms / 1000.0,
            normalized_cost,
            final_feature.refinement_attempts,
        )

        # Clear current feature tracking
        self._current_feature = None

        # Note: dependent cascade is NOT re-run here. ``handle_execution_result``
        # already invokes ``db.complete_feature_and_cascade`` atomically on the
        # success path (status flip + readiness cascade in a single SQLite
        # transaction). A second ``cascade_update_dependents`` here would be
        # idempotent but wastes DB round-trips, and on the git-hook-rejection
        # path the dependents have already been rolled back inline above. The
        # rollback path explicitly re-pins dependents to 'pending' there, so
        # no further cascade work is needed at this point.

        return spawn_result

    def rollback_feature(
        self,
        *,
        feature_id: str,
        trigger: str,
        commit_sha: str,
        commit_before: str,
        regression_event_id: str | None = None,
    ) -> None:
        """Roll back a feature with git revert and database recording.

        Performs the actual git revert and then records the rollback event
        in the database.

        Args:
            feature_id: ID of the feature to roll back.
            trigger: What triggered the rollback (regression|human_request|critical_bug).
            commit_sha: The SHA of the feature's commit to revert.
            commit_before: The SHA of HEAD before the feature was implemented.
            regression_event_id: Optional linked regression event ID.
        """
        # F114: Execute the actual git revert
        rollback_commit: str | None = None
        if self.workspace:
            try:
                rollback_commit = git_revert_feature(
                    feature_id=feature_id,
                    commit_sha=commit_sha,
                    workspace=self.workspace,
                )
            except Exception:
                logger.warning(
                    "Git revert failed for feature %s", feature_id,
                    exc_info=True,
                )

        # Get current HEAD as commit_after
        commit_after = commit_sha

        # Record the rollback in the database
        db.rollback_feature(
            project_id=self.project_id,
            feature_id=feature_id,
            trigger=trigger,
            commit_before=commit_before,
            commit_after=commit_after,
            rollback_commit=rollback_commit,
            regression_event_id=regression_event_id,
        )

        logger.info(
            "Rolled back feature %s (trigger=%s, revert_commit=%s)",
            feature_id, trigger, rollback_commit,
        )

    def _create_interruption_checkpoint(
        self, feature: Feature, result: ExecutionResult
    ) -> None:
        """Create a checkpoint when a feature is interrupted by graceful shutdown.

        Captures the feature state, accumulated cost, and reason for
        interruption so that the feature can be resumed later.

        Args:
            feature: The feature that was being executed.
            result: The execution result from the sub-agent.
        """
        # R5-010 / R7-004 / structural fix (``non-atomic-counter``):
        # the in-memory ``self.total_cost`` mirror was deleted; cost is
        # written exclusively through ``self._increment_cost`` which
        # updates the DB, mirrors the delta into the tamper-detection
        # floor, and refreshes ``self._project_total_cost`` atomically.
        # R9-002: by the time this helper runs, execute_feature has
        # ALREADY routed the just-finished feature's cost through
        # ``_increment_cost``, so ``self._project_total_cost`` already
        # includes it. Adding ``result.total_cost_usd`` again here would
        # double-count.
        project_total = float(self._project_total_cost or 0.0)
        state = {
            "feature_id": feature.id,
            "feature_name": feature.name,
            "feature_status": "interrupted",
            "reason": "graceful_shutdown",
            "total_cost_at_interrupt": project_total,
            "features_completed": self.features_completed,
            "features_failed": self.features_failed,
        }
        try:
            db.create_checkpoint(
                project_id=self.project_id,
                feature_id=feature.id,
                checkpoint_type="interruption",
                state_snapshot=json.dumps(state),
                cost_at_checkpoint=project_total,
                duration_at_checkpoint_ms=result.duration_ms,
            )
            logger.info(
                "Created interruption checkpoint for feature %s", feature.id
            )
        except Exception:
            logger.warning(
                "Failed to create interruption checkpoint for feature %s",
                feature.id,
                exc_info=True,
            )

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown.

        The handler is intentionally minimal: it only sets the
        ``shutdown_requested`` flag (async-signal-safe) and emits a
        warning. The flag is observed at the top of ``run()`` between
        feature iterations.

        KNOWN LIMITATION (mirrored in the module docstring): if the
        signal arrives while ``await spawn_sub_agent(...)`` is in
        flight, the loop will not actually stop until that sub-agent
        finishes. The warning below tells the user this so they know
        why Ctrl-C "doesn't work immediately" and that a second Ctrl-C
        will force-exit via :class:`SystemExit`.
        """
        def handler(signum, frame):
            sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
            if self.shutdown_requested:
                # Second signal: force immediate exit. Raising SystemExit
                # from a signal handler is permitted (the interpreter
                # unwinds via the regular exception path).
                logger.warning(
                    "Received %s again during shutdown — forcing immediate exit",
                    sig_name,
                )
                raise SystemExit(128 + signum)

            logger.warning(
                "Received %s — graceful shutdown requested. "
                "Shutdown will be honored after the current sub-agent finishes "
                "(this can take several minutes). Press Ctrl-C again to force exit.",
                sig_name,
            )
            self.request_shutdown()

        try:
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        except (OSError, ValueError):
            # Signal handling may fail in some contexts (e.g., threads)
            logger.debug("Could not install signal handlers")

    def _resume_interrupted_work(self) -> None:
        """Detect and resume interrupted work from a previous run.

        On startup, checks for:
        1. Features with status='executing' (crashed mid-execution)
        2. Features with status='interrupted' (gracefully stopped)
        3. Resumable checkpoints (can_resume=TRUE)
        4. Orphaned 'pending' features whose dependencies are ALL completed
           (left over from a crash mid-cascade-update — see
           ``db.complete_feature_and_cascade``)

        For each interrupted/executing feature:
        - If a resumable checkpoint exists, resume from it (restoring state)
        - If no checkpoint, reset the feature to 'ready' so it retries from scratch

        In fresh mode, all interrupted/executing features are simply reset to 'ready'
        without consuming any checkpoints.

        Orphaned-pending recovery always runs (independent of fresh mode) so
        that a mid-cascade crash never permanently strands dependents on
        'pending'.
        """
        # Find features stuck in 'executing' (process crashed)
        executing = db.list_features(project_id=self.project_id, status="executing")
        # Find features marked 'interrupted' (graceful shutdown)
        interrupted = db.list_features(project_id=self.project_id, status="interrupted")

        stale_features = executing + interrupted

        if stale_features:
            logger.info(
                "Found %d interrupted/stale features to resume",
                len(stale_features),
            )

            if self.fresh:
                # Fresh mode: reset all to 'ready' without consuming checkpoints
                for feat in stale_features:
                    db.update_feature(feat.id, status="ready")
                    logger.info(
                        "Fresh mode: reset feature %s (%s) to 'ready'",
                        feat.id,
                        feat.name,
                    )
            else:
                # Normal resume mode: try to resume from checkpoints
                resumable = db.find_resumable_checkpoints(project_id=self.project_id)
                # Build a map: feature_id -> most recent resumable checkpoint
                checkpoint_by_feature: dict[str, Any] = {}
                for cp in resumable:
                    if cp.feature_id not in checkpoint_by_feature:
                        checkpoint_by_feature[cp.feature_id] = cp

                for feat in stale_features:
                    cp = checkpoint_by_feature.get(feat.id)
                    if cp is not None:
                        # Resume from checkpoint (restores feature state then sets to 'ready')
                        logger.info(
                            "Resuming feature %s (%s) from checkpoint %s",
                            feat.id,
                            feat.name,
                            cp.id,
                        )
                        db.resume_from_checkpoint(cp.id)
                        # After state is restored, set to 'ready' so the loop picks it up
                        db.update_feature(feat.id, status="ready")
                    else:
                        # No checkpoint: reset to 'ready'
                        logger.info(
                            "No checkpoint for feature %s (%s), resetting to 'ready'",
                            feat.id,
                            feat.name,
                        )
                        db.update_feature(feat.id, status="ready")

        # Orphaned-pending recovery (atomicity safety-net):
        # Scan for 'pending' features whose dependencies are ALL completed.
        # These are the tell-tale sign of a crash between the feature
        # status update and the dependent cascade in a previous version
        # of this code (or any future regression). Promote them to
        # 'ready' so the loop can pick them up. Runs independently of
        # the 'executing'/'interrupted' branch because the orphan state
        # has nothing to do with checkpoints.
        self._recover_orphaned_pending_features()

    def _recover_orphaned_pending_features(self) -> None:
        """Promote pending features whose deps are all completed to 'ready'.

        Two cases are handled here, both with the same fix (bulk promote
        ``pending`` → ``ready``):

        1. **Mid-cascade crash recovery.** A crash between the feature
           status update and the dependent cascade in
           ``db.complete_feature_and_cascade`` would leave dependents in
           'pending' with all dependencies satisfied — a state the loop
           would otherwise never escape.
        2. **Fresh-spec root features (R10-003).** Features with no
           declared dependencies are created by ``bob3 plan --create``
           in ``status='pending'`` and were never promoted to ``ready``
           on first run, so a brand-new project would exit
           ``ALL_BLOCKED`` immediately. This is the most visible
           Quickstart regression: the literal README sequence ``init`` →
           ``plan --create`` → ``run --all`` did nothing useful.

        Implementation note: detection is two cheap indexed SQL queries
        (``db.find_orphaned_pending_features`` and
        ``db.find_pending_features_without_deps``), and the promotion is
        one bulk ``UPDATE ... WHERE id IN (...) AND status='pending'`` in
        ``db.bulk_promote_features_to_ready``. We dedupe before the
        promote so the log message reflects the actual unique work.
        """
        orphaned_ids = db.find_orphaned_pending_features(self.project_id)
        no_dep_ids = db.find_pending_features_without_deps(self.project_id)

        # Dedupe (the two queries are disjoint by construction — one
        # requires EXISTS deps, the other requires NOT EXISTS deps — but
        # be defensive in case a future schema change blurs the line).
        all_ids: list[str] = []
        seen: set[str] = set()
        for fid in (*orphaned_ids, *no_dep_ids):
            if fid not in seen:
                seen.add(fid)
                all_ids.append(fid)

        if not all_ids:
            return

        promoted = db.bulk_promote_features_to_ready(all_ids)

        if orphaned_ids:
            logger.info(
                "Mid-cascade crash recovery: promoted %d orphaned pending "
                "feature(s) to 'ready': %s",
                len(orphaned_ids),
                ", ".join(p[:8] for p in orphaned_ids),
            )
        if no_dep_ids:
            logger.info(
                "Promoted %d pending root feature(s) (no declared deps) "
                "to 'ready': %s",
                len(no_dep_ids),
                ", ".join(p[:8] for p in no_dep_ids),
            )
        # Sanity check: the bulk promote is idempotent and may report a
        # smaller count than ``len(all_ids)`` if a feature moved status
        # between the SELECT and the UPDATE. Log if so — it usually means
        # a concurrent path is also touching status.
        if promoted < len(all_ids):
            logger.debug(
                "Bulk promote raced: requested %d, applied %d",
                len(all_ids),
                promoted,
            )

    async def _run_single_feature(self) -> LoopTermination:
        """Run only the target feature (one iteration) then exit.

        Used when ``target_feature_id`` is set on the loop. Skips
        ``find_next_ready_feature`` so we never run unrelated features.

        Returns:
            ALL_COMPLETED if the feature finished with status='completed',
            ALL_BLOCKED if the feature is not runnable or ended in any
            non-completed status (``needs_human``, ``failed``, ``interrupted``).
            BUDGET_EXCEEDED if --max-cost was reached before execution.
            SHUTDOWN_REQUESTED if SIGINT/SIGTERM fired mid-run.
        """
        feature = db.get_feature(self.target_feature_id)
        if feature is None:
            logger.error(
                "Target feature %s not found; aborting single-feature run",
                self.target_feature_id,
            )
            return LoopTermination.ALL_BLOCKED

        if feature.project_id != self.project_id:
            logger.error(
                "Target feature %s belongs to a different project (%s); aborting",
                self.target_feature_id,
                feature.project_id,
            )
            return LoopTermination.ALL_BLOCKED

        # Validate that the feature is runnable. find_next_ready_feature uses
        # the features_ready view, which requires status='ready' AND that
        # readiness_score >= the risk-category threshold AND that all
        # dependencies are completed. Match that here by looking up the
        # feature in the same view.
        ready = {f.id: f for f in db.get_ready_features(self.project_id)}
        runnable = feature.id in ready

        # 'ready' / 'pending' may still need a real dependency check — a
        # 'pending' feature whose dependencies are NOT all completed must
        # not run, even though its status is in the allow-set. Anything
        # outside {ready, pending} is unconditionally blocked.
        if not runnable and feature.status not in {"ready", "pending"}:
            logger.info(
                "Target feature %s is not runnable (status=%s); exiting cleanly",
                feature.id,
                feature.status,
            )
            return LoopTermination.ALL_BLOCKED

        # Bug 5: Tighten the 'pending' allowance. If any declared dependency
        # is not yet 'completed', the feature is genuinely blocked — runnable
        # would be False here (it isn't in the features_ready view) so we
        # already know readiness/threshold may be low, but the dep gate is
        # the load-bearing one. Check it explicitly so a pending feature with
        # unmet deps never sneaks through.
        if not runnable:
            try:
                deps = db.get_feature_dependencies(feature.id)
            except Exception:
                logger.warning(
                    "Could not read dependencies for target feature %s; "
                    "treating as blocked",
                    feature.id,
                    exc_info=True,
                )
                return LoopTermination.ALL_BLOCKED
            for dep in deps:
                dep_feature = db.get_feature(dep.depends_on_feature_id)
                if dep_feature is None or dep_feature.status != "completed":
                    logger.info(
                        "Target feature %s has unmet dependency %s "
                        "(status=%s); exiting cleanly",
                        feature.id,
                        dep.depends_on_feature_id,
                        dep_feature.status if dep_feature else "missing",
                    )
                    return LoopTermination.ALL_BLOCKED

        # Assess confidence if not yet assessed (mirrors main loop behaviour).
        if feature.readiness_score == 0.0:
            logger.info(
                "Assessing confidence for target feature %s (%s)",
                feature.id[:8],
                _log_safe(feature.name),
            )
            confidence = db.assess_feature_confidence(feature.id)
            db.update_feature(feature.id, **confidence)
            feature = db.get_feature(feature.id)
            if feature is None:
                logger.error("Target feature disappeared after confidence assessment")
                return LoopTermination.ALL_BLOCKED

        # Bug 3: Honour --max-cost / project budget even in single-feature
        # mode. The main run() loop checks this every iteration, but the
        # single-feature path used to skip the check entirely.
        if self.budget_exceeded():
            logger.warning(
                "Budget exceeded for project %s; cannot run feature %s",
                self.project_id,
                feature.id,
            )
            return LoopTermination.BUDGET_EXCEEDED

        # Execute exactly one feature, then exit regardless of outcome.
        await self.execute_feature(feature)
        self._maybe_warn_cost_proxy_active()
        # R10-002: If the operator hit Ctrl-C / SIGTERM during the run, the
        # outer CLI used to print "Feature completed!" and exit 0 because the
        # single-feature path returned ALL_COMPLETED unconditionally. That
        # masked an interrupted run as success — concretely, this is exactly
        # how a CI pipeline that does `bob3 run --feature X && deploy.sh`
        # would push a half-built tree to production. Mirror the main loop:
        # if shutdown was requested, surface SHUTDOWN_REQUESTED so the CLI
        # prints "Shutdown requested." and exits 130.
        if self.shutdown_requested:
            return LoopTermination.SHUTDOWN_REQUESTED
        # R10-007: Reflect the feature's ACTUAL final status in the
        # termination reason. Previously this returned ALL_COMPLETED
        # unconditionally — even when the sub-agent failed verification,
        # was rejected by a hook, errored out, or otherwise ended
        # ``needs_human``. The summary log then said
        # ``termination=ALL_COMPLETED features_completed=0 features_failed=1``
        # which is internally inconsistent and (worse) made `bob3 run
        # --feature X` exit 0 on failure, so a CI pipeline doing `bob3
        # run --feature X && deploy.sh` would push a half-built tree to
        # production. Re-read the feature post-execution and map status
        # to the appropriate termination.
        try:
            final = db.get_feature(feature.id)
        except Exception:
            logger.debug(
                "Could not re-read feature %s after execution; "
                "falling back to ALL_BLOCKED",
                feature.id,
                exc_info=True,
            )
            return LoopTermination.ALL_BLOCKED
        if final is None:
            return LoopTermination.ALL_BLOCKED
        if final.status == "completed":
            return LoopTermination.ALL_COMPLETED
        # ``needs_human``, ``failed``, ``executing`` (interrupted),
        # ``interrupted``, ``ready``/``pending`` (somehow unchanged) all
        # mean: the feature did not finish cleanly. Surface that to the
        # CLI as ALL_BLOCKED so the exit code is non-zero.
        return LoopTermination.ALL_BLOCKED

    async def run(self) -> LoopTermination:
        """Run the continuous orchestration loop.

        Processes features strictly one at a time (sequential, not
        concurrent) until a termination condition is met. Each iteration
        picks the highest-priority ready feature, awaits its sub-agent
        to completion, then loops; there is no fan-out across sibling
        features. On startup, automatically detects and resumes
        interrupted work (F116).

        When ``target_feature_id`` is set, runs only that single feature and
        exits after one iteration regardless of outcome.

        Concurrency: this method acquires an exclusive advisory file lock
        on ``<workspace>/.bob3.lock`` for the duration of the run. A
        second concurrent ``bob3 run`` for the same project will fail
        fast with :class:`AlreadyRunningError`.

        Returns:
            The reason the loop terminated.
        """
        # Acquire the per-project run lock. If another bob3 run is in
        # flight we want to bail out BEFORE installing signal handlers
        # or doing any DB writes — the second invocation should be a
        # no-op from the project's point of view.
        lock_handle = acquire_run_lock(
            self.workspace or os.getcwd(), force_unlock=self.force_unlock
        )
        # R5-009: Capture the wall-clock start so the termination summary
        # log reflects the actual run time (not OrchestrationLoop init
        # time). Set inside ``run`` so re-running the same loop instance
        # gets a fresh window.
        self._run_start_time = time.monotonic()
        termination: LoopTermination | None = None
        try:
            termination = await self._run_locked()
            return termination
        finally:
            # Always emit the loop-level summary on the way out — even if
            # _run_locked raised — so operators see the cost / counts
            # for partial runs too. ``termination`` stays None on a raised
            # exception; surface that distinctly so the log doesn't claim
            # a completion reason that never happened.
            self._emit_run_summary(termination)
            release_run_lock(lock_handle)

    def _emit_run_summary(self, termination: LoopTermination | None) -> None:
        """Log a single structured line summarising the run.

        Intended to be called exactly once per ``run()`` invocation,
        from the ``finally`` block so that crashes / cancellations also
        get a summary line. The log line format is parsable by ops
        tooling: features_completed / features_failed / total_cost /
        total_duration are space-separated key=value pairs.
        """
        if self._run_start_time is None:
            run_duration = 0.0
        else:
            run_duration = max(0.0, time.monotonic() - self._run_start_time)
        # ``self._project_total_cost`` is the only project cost
        # accumulator now (the prior in-memory ``self.total_cost``
        # mirror was deleted as part of the ``non-atomic-counter``
        # structural fix). Refresh once here in case something exotic
        # touched the DB out of band — every cost write site already
        # refreshes via ``_increment_cost``.
        try:
            self._refresh_project_cost_cache()
        except Exception:
            logger.debug(
                "Could not refresh project cost cache for run summary",
                exc_info=True,
            )
        total_cost = float(self._project_total_cost or 0.0)
        termination_name = termination.name if termination is not None else "RAISED"
        logger.info(
            "Run finished: termination=%s features_completed=%d "
            "features_failed=%d total_cost=$%.2f total_duration=%.1fs",
            termination_name,
            self.features_completed,
            self.features_failed,
            total_cost,
            run_duration,
        )

    async def _run_locked(self) -> LoopTermination:
        """Body of :meth:`run` executed while the project lock is held."""
        self._install_signal_handlers()
        logger.info("Starting orchestration loop for project %s", self.project_id)

        # F116: Auto-resume interrupted work
        self._resume_interrupted_work()

        # Single-feature mode: run only the target feature and exit.
        if self.target_feature_id is not None:
            return await self._run_single_feature()

        while True:
            # Check shutdown
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping loop")
                # F117: Stop MCP server gracefully
                try:
                    stop_mcp_server()
                except Exception:
                    logger.debug("MCP server stop failed during shutdown", exc_info=True)
                logger.info("Interrupted. Run bob3 run to resume.")
                return LoopTermination.SHUTDOWN_REQUESTED

            # Check budget
            if self.budget_exceeded():
                logger.info("Budget exceeded, stopping loop")
                return LoopTermination.BUDGET_EXCEEDED

            # Find next ready feature
            feature = self.find_next_ready_feature()
            if feature is None:
                # No feature meets readiness threshold - check for features that need research
                features_in_ready_status = db.list_features(
                    project_id=self.project_id,
                    status='ready'
                )
                if features_in_ready_status:
                    # Pick the first one that's in 'ready' status but doesn't meet threshold
                    feature = features_in_ready_status[0]
                    # R7-003: If research has already run for this feature
                    # then ``needs_research`` will return False on the next
                    # ``execute_feature`` call. Without research, readiness
                    # cannot improve, but the loop would still spawn the
                    # implementation sub-agent — burning a refinement
                    # attempt every iteration until ``max_refinement_attempts``
                    # is exhausted. Mark it ``needs_human`` instead so the
                    # operator can intervene (raise readiness, lower risk
                    # category, or split the work).
                    if feature.research_iterations and feature.research_iterations > 0:
                        threshold = db.RISK_THRESHOLDS.get(
                            feature.risk_category, 0.80
                        )
                        logger.warning(
                            "Feature %s is below readiness threshold "
                            "(score=%.2f, threshold=%.2f) and research already "
                            "completed (iterations=%d); marking needs_human.",
                            feature.id,
                            feature.readiness_score,
                            threshold,
                            feature.research_iterations,
                        )
                        db.update_feature(feature.id, status="needs_human")
                        # Loop again — there may be other actionable work.
                        continue
                    logger.info(
                        "No features meet readiness threshold, but found feature %s in 'ready' status (readiness=%.2f). Will assess and potentially trigger research.",
                        feature.id[:8],
                        feature.readiness_score
                    )
                elif self.all_features_completed():
                    logger.info("All features completed")
                    return LoopTermination.ALL_COMPLETED
                elif self.all_remaining_blocked():
                    logger.info("All remaining features are blocked")
                    return LoopTermination.ALL_BLOCKED
                else:
                    # No ready feature but some are still pending — keep looping
                    # (this could happen if features are being reviewed or refined)
                    # To prevent busy-waiting, break if nothing is actionable
                    logger.info("No ready features, all remaining are blocked or pending")
                    return LoopTermination.ALL_BLOCKED

            # Assess confidence before execution (if not already assessed)
            # This ensures features with low confidence trigger research
            if feature.readiness_score == 0.0:
                logger.info(
                    "Assessing confidence for feature %s (%s)",
                    feature.id[:8],
                    _log_safe(feature.name)
                )
                confidence = db.assess_feature_confidence(feature.id)
                db.update_feature(feature.id, **confidence)
                # Refresh feature with updated confidence scores
                feature = db.get_feature(feature.id)
                if not feature:
                    logger.error("Feature disappeared after confidence assessment")
                    continue

            # Execute the feature
            await self.execute_feature(feature)
            self._maybe_warn_cost_proxy_active()
