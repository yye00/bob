"""MCP Server Lifecycle Management for Bob.

Manages the bob-memory MCP server lifecycle - starting it as a subprocess,
monitoring health, and ensuring graceful shutdown. Only bob-memory is managed
by Bob; Perplexity and Puppeteer are available via the Claude Code environment.

CRITICAL: bob-memory is required for Bob operation. If the MCP server
fails to start, Bob must stop immediately with a clear error message.
"""

from __future__ import annotations

import atexit
import errno
import json
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from bob.orchestrator.mcp_config import BOB_MEMORY_MCP, MCPServerConfig

logger = logging.getLogger(__name__)

_STARTUP_WAIT_SECONDS = 1.0
_SHUTDOWN_TIMEOUT_SECONDS = 5

# Module-level lock + shared process registry. Direct construction of
# MCPLifecycleManager() (e.g. in tests or external code) creates a fresh
# instance whose atexit/start would otherwise spawn an independent
# subprocess. Sharing _active_processes (keyed by config name) means a
# second manager with the same config attaches to the existing process
# instead of double-spawning.
_registry_lock = threading.Lock()
_active_processes: dict[str, subprocess.Popen] = {}


class MCPStartupError(Exception):
    """Raised when the MCP server fails to start.

    This is a fatal error - Bob cannot operate without bob-memory.
    """


class MCPLifecycleManager:
    """Manages the lifecycle of a single MCP server subprocess.

    Handles starting, health checking, and stopping the bob-memory
    MCP server. Registers an atexit handler to ensure cleanup on exit.
    """

    def __init__(self, config: MCPServerConfig | None = None) -> None:
        self.config = config or BOB_MEMORY_MCP
        self._process: subprocess.Popen | None = None
        self._atexit_registered: bool = False

    @property
    def pid(self) -> int | None:
        """Return the PID of the managed process, or None if not running."""
        if self._process is not None:
            return self._process.pid
        return None

    def start(self) -> None:
        """Start the MCP server subprocess.

        Validates required environment variables, launches the subprocess,
        and waits briefly to confirm it didn't exit immediately.

        Raises:
            MCPStartupError: If the server fails to start for any reason
                (missing env vars, command not found, immediate exit, etc).
        """
        # Idempotent: if the managed subprocess is already running, don't
        # spawn a second one (which would orphan the first). The singleton
        # start_mcp_server() relies on this to be safe across repeated calls
        # (e.g. `bob init` then `bob run` within one process).
        if self._process is not None and self._process.poll() is None:
            logger.debug(
                "bob-memory MCP server already running (pid=%d); skipping start",
                self._process.pid,
            )
            return

        # Cross-instance guard: if another MCPLifecycleManager already
        # spawned a process for this config, attach to it instead of
        # spawning a second subprocess. Direct construction of
        # MCPLifecycleManager() (outside the singleton) would otherwise
        # silently double-spawn.
        with _registry_lock:
            existing = _active_processes.get(self.config.name)
            if existing is not None and existing.poll() is None:
                logger.debug(
                    "%s MCP server already running (pid=%d) under another "
                    "manager; attaching to existing process",
                    self.config.name,
                    existing.pid,
                )
                self._process = existing
                # Still register our own atexit so cleanup happens; stop()
                # is idempotent and will only act if the process is alive.
                if not self._atexit_registered:
                    atexit.register(self.stop)
                    self._atexit_registered = True
                return

            # Validate required environment variables
            for var in self.config.env_vars:
                if not os.environ.get(var):
                    raise MCPStartupError(
                        f"Required environment variable {var} is not set. "
                        f"{self.config.name} MCP server cannot start without it."
                    )

            # Launch the subprocess
            try:
                self._process = subprocess.Popen(
                    self.config.command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise MCPStartupError(
                    f"Failed to start MCP server: command not found - {exc}"
                ) from exc
            except PermissionError as exc:
                raise MCPStartupError(
                    f"Failed to start MCP server: permission denied - {exc}"
                ) from exc
            except OSError as exc:
                raise MCPStartupError(
                    f"Failed to start MCP server: {exc}"
                ) from exc

            # Wait briefly and check if process exited immediately
            time.sleep(_STARTUP_WAIT_SECONDS)

            exit_code = self._process.poll()
            if exit_code is not None:
                stderr_output = ""
                if self._process.stderr:
                    stderr_bytes = self._process.stderr.read()
                    stderr_output = stderr_bytes.decode("utf-8", errors="replace")
                self._process = None
                raise MCPStartupError(
                    f"MCP server exited immediately with code {exit_code}. "
                    f"stderr: {stderr_output}"
                )

            # Publish to the shared registry so other managers attach
            # rather than double-spawn.
            _active_processes[self.config.name] = self._process

            # Register atexit handler to ensure cleanup (once per manager
            # instance to avoid accumulating duplicate handlers on
            # repeated start() calls).
            if not self._atexit_registered:
                atexit.register(self.stop)
                self._atexit_registered = True

            logger.info(
                "bob-memory MCP server started (pid=%d)", self._process.pid
            )

    def health_check(self) -> bool:
        """Check if the MCP server process is still running.

        Returns:
            True if the process is alive, False otherwise.
        """
        if self._process is None:
            return False
        return self._process.poll() is None

    def stop(self) -> None:
        """Stop the MCP server subprocess gracefully.

        Sends SIGTERM first, then SIGKILL if the process doesn't exit
        within the timeout. Safe to call multiple times or when no
        process is running.

        Uses ``communicate(timeout=...)`` rather than ``wait(timeout=...)``
        so the OS pipe buffers for stdout/stderr are drained while waiting.
        With ``stderr=subprocess.PIPE`` and a misbehaving child that writes
        a large stack trace on SIGTERM, ``wait`` would deadlock once the
        pipe (~64KB) filled, blocking the child's write() call until our
        timeout expired (and then again on the SIGKILL path).
        """
        if self._process is None:
            return

        pid = self._process.pid
        logger.info("Stopping bob-memory MCP server (pid=%d)...", pid)

        # Only the manager that "owns" the registry entry should actually
        # terminate the process. Other managers that attached share the
        # reference but should detach quietly to avoid double-stop races.
        with _registry_lock:
            owned = _active_processes.get(self.config.name) is self._process
            if owned:
                _active_processes.pop(self.config.name, None)

        if not owned:
            self._process = None
            return

        self._process.terminate()
        try:
            self._process.communicate(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning(
                "MCP server did not stop gracefully, killing (pid=%d)", pid
            )
            self._process.kill()
            try:
                self._process.communicate(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                logger.error(
                    "MCP server did not respond to SIGKILL - orphaned (pid=%d)",
                    pid,
                )

        self._process = None
        logger.info("bob-memory MCP server stopped (pid=%d)", pid)

    def __enter__(self) -> MCPLifecycleManager:
        """Start the MCP server when entering context."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop the MCP server when exiting context."""
        self.stop()


# ---------------------------------------------------------------------------
# Module-level singleton and convenience functions
# ---------------------------------------------------------------------------

_manager: MCPLifecycleManager | None = None


def get_mcp_manager() -> MCPLifecycleManager:
    """Return the singleton MCPLifecycleManager instance."""
    global _manager
    if _manager is None:
        _manager = MCPLifecycleManager()
    return _manager


def start_mcp_server() -> MCPLifecycleManager:
    """Start the bob-memory MCP server using the singleton manager.

    Returns:
        The MCPLifecycleManager instance managing the server.

    Raises:
        MCPStartupError: If the server fails to start.
    """
    manager = get_mcp_manager()
    manager.start()
    return manager


def stop_mcp_server() -> None:
    """Stop the bob-memory MCP server if running."""
    global _manager
    if _manager is not None:
        _manager.stop()


# ---------------------------------------------------------------------------
# F-R6-302: Per-sub-agent MCP registry + orphan sweep
# ---------------------------------------------------------------------------
#
# Background: in Round 5 the orchestrator accumulated 59 orphan
# ``bob.memory_mcp`` server processes. Each sub-agent spawn produces its
# own MCP subprocess (via the Claude SDK's ``mcp_servers`` mapping), but
# nothing tracked them, so a sub-agent that died abnormally (timeout,
# OOM, segfault) left its MCP behind. The processes pile up until file
# descriptors / RAM run out.
#
# The functions below maintain a small JSON registry mapping
# ``sub_agent_id -> [mcp_pid, ...]`` so the orchestrator can:
#   1. ``register_mcp`` right after spawning an MCP for a sub-agent;
#   2. ``unregister_mcp`` in the sub-agent's ``try/finally`` exit path;
#   3. ``sweep_orphans`` periodically to reap any MCPs whose parent
#      sub-agent is no longer alive (covers crash / kill -9 paths
#      where the finally never ran).

_REGISTRY_DIR = Path.home() / ".bob"
_REGISTRY_PATH = _REGISTRY_DIR / "mcp_registry.json"
_REGISTRY_FILE_LOCK = threading.Lock()
_TERM_WAIT_SECONDS = 1.0
_PID_PROBE_INTERVAL = 0.05


def _registry_path() -> Path:
    """Return the registry file path (env-overridable for tests)."""
    override = os.environ.get("BOB_MCP_REGISTRY_PATH")
    if override:
        return Path(override)
    return _REGISTRY_PATH


def _load_registry() -> dict[str, list[int]]:
    """Read the on-disk registry, returning {} if missing/unparseable."""
    path = _registry_path()
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "MCP registry at %s is unparseable; treating as empty.", path
        )
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, list[int]] = {}
    for k, v in data.items():
        if not isinstance(v, list):
            continue
        pids = [int(p) for p in v if isinstance(p, (int, float)) and int(p) > 0]
        if pids:
            cleaned[str(k)] = pids
    return cleaned


def _save_registry(reg: dict[str, list[int]]) -> None:
    """Atomically write the registry to disk."""
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(reg, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _pid_alive(pid: int) -> bool:
    """Return True iff ``pid`` is a running, non-zombie process.

    Uses ``os.kill(pid, 0)`` for the existence check and then reads
    ``/proc/<pid>/status`` State line to filter out zombies. A zombie
    has been reaped at the kernel level (its memory and fds are gone)
    but its PID is held alive until the parent calls ``waitpid``. For
    our purposes a zombie IS dead — it's not consuming the resources
    the sweep was designed to recover.

    EPERM is treated as alive (some other user owns the pid).
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        return False
    # PID exists; check if it's a zombie.
    status_path = Path(f"/proc/{pid}/status")
    try:
        text = status_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # Race: pid disappeared between kill(0) and the read.
        return False
    for line in text.splitlines():
        if line.startswith("State:"):
            # State line is e.g. "State:	Z (zombie)" or "State:	S (sleeping)".
            rest = line.split(":", 1)[1].strip()
            if rest.startswith("Z") or rest.startswith("X"):
                return False
            break
    return True


def _read_ppid(pid: int) -> int | None:
    """Return the parent PID of ``pid`` via ``/proc/<pid>/status``.

    Returns None if the file cannot be read (process is gone, or the
    OS is not Linux). The ``PPid:`` line is preferred over ``stat``
    because the comm field in ``stat`` can contain spaces / parens.
    """
    status_path = Path(f"/proc/{pid}/status")
    try:
        text = status_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("PPid:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                return None
    return None


def _reap_pid(pid: int) -> bool:
    """Send SIGTERM, wait briefly, then SIGKILL. Return True iff dead.

    Idempotent: a PID that is already dead is reported as reaped.
    """
    if not _pid_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return True
        logger.debug("SIGTERM to pid=%d failed: %s", pid, exc)

    deadline = time.monotonic() + _TERM_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(_PID_PROBE_INTERVAL)

    # Still alive — escalate to SIGKILL.
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return True
        logger.warning("SIGKILL to pid=%d failed: %s", pid, exc)

    deadline = time.monotonic() + _TERM_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(_PID_PROBE_INTERVAL)

    return not _pid_alive(pid)


def _is_memory_mcp_pid(pid: int) -> bool:
    """Heuristic check that ``pid`` is a bob.memory_mcp process.

    Reads ``/proc/<pid>/cmdline`` and looks for the ``bob.memory_mcp``
    token. Returns False if the file cannot be read or the token is
    absent. Used by ``sweep_orphans`` to avoid reaping unrelated PIDs.
    """
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        raw = cmdline_path.read_bytes()
    except OSError:
        return False
    # /proc/<pid>/cmdline is NUL-separated.
    cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")
    return "bob.memory_mcp" in cmdline


def _iter_memory_mcp_pids() -> list[int]:
    """Return all currently-running ``bob.memory_mcp`` PIDs by scanning /proc.

    We deliberately do NOT shell out to ``pgrep`` here: the tests run in
    the same interpreter and shelling out is brittle on minimal CI
    images. Walking ``/proc`` directly is portable across Linux.
    """
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    pids: list[int] = []
    for entry in proc_root.iterdir():
        name = entry.name
        if not name.isdigit():
            continue
        pid = int(name)
        if _is_memory_mcp_pid(pid):
            pids.append(pid)
    return pids


def register_mcp_server(sub_agent_id: str, mcp_pid: int) -> None:
    """Record that ``mcp_pid`` belongs to sub-agent ``sub_agent_id``.

    Alias for ``register_mcp`` — the canonical name expected by the
    acceptance criteria for F-b606f148 (MCP server lifecycle + orphan sweep).
    Multiple PIDs per sub-agent are supported. Idempotent.
    """
    register_mcp(sub_agent_id, mcp_pid)


def register_mcp(sub_agent_id: str, mcp_pid: int) -> None:
    """Record that ``mcp_pid`` belongs to sub-agent ``sub_agent_id``.

    Multiple PIDs per sub-agent are supported (a sub-agent may spawn
    several MCPs). Idempotent: re-registering the same PID is a no-op.
    """
    if not sub_agent_id:
        raise ValueError("sub_agent_id must be non-empty")
    if not isinstance(mcp_pid, int) or mcp_pid <= 0:
        raise ValueError(f"mcp_pid must be a positive int, got {mcp_pid!r}")
    with _REGISTRY_FILE_LOCK:
        reg = _load_registry()
        existing = reg.get(sub_agent_id, [])
        if mcp_pid not in existing:
            existing.append(mcp_pid)
        reg[sub_agent_id] = existing
        _save_registry(reg)


def unregister_mcp(sub_agent_id: str) -> list[int]:
    """Reap every MCP registered for ``sub_agent_id``.

    Sends SIGTERM, waits briefly, then SIGKILL if the process is still
    alive. Removes the entry from the registry on the way out. Returns
    the list of PIDs that were confirmed dead (which equals the
    registered set on a successful reap).
    """
    if not sub_agent_id:
        return []
    with _REGISTRY_FILE_LOCK:
        reg = _load_registry()
        pids = list(reg.get(sub_agent_id, []))
        # Drop the entry first so a crash during reap doesn't leave a
        # stale row pointing at PIDs we already killed (which the next
        # OS might recycle).
        if sub_agent_id in reg:
            del reg[sub_agent_id]
            _save_registry(reg)

    reaped: list[int] = []
    for pid in pids:
        if _reap_pid(pid):
            reaped.append(pid)
        else:
            logger.warning(
                "Failed to reap MCP pid=%d for sub_agent=%s; still alive after "
                "SIGTERM+SIGKILL.",
                pid,
                sub_agent_id,
            )
    return reaped


def sweep_orphans() -> list[int]:
    """Reap every ``bob.memory_mcp`` process whose parent is gone.

    Walks ``/proc`` for live ``bob.memory_mcp`` PIDs, reads the
    parent PID from ``/proc/<pid>/status``, and if the parent is no
    longer alive, reaps the child. Returns the list of orphan PIDs
    that were confirmed dead.

    Also purges registry entries that point to dead PIDs so the file
    does not grow unbounded.
    """
    candidates = _iter_memory_mcp_pids()
    orphan_pids: list[int] = []
    for pid in candidates:
        ppid = _read_ppid(pid)
        if ppid is None:
            # Couldn't read /proc/<pid>/status — the process might have
            # exited between our scan and the read. Skip; nothing to do.
            continue
        # PPid==1 means re-parented to init (orphaned). PPid pointing at
        # a dead PID also counts. Either way the parent sub-agent is gone.
        if ppid == 1 or not _pid_alive(ppid):
            if _reap_pid(pid):
                orphan_pids.append(pid)
            else:
                logger.warning("Failed to reap orphan MCP pid=%d", pid)

    # Garbage-collect registry entries whose PIDs are all dead now.
    with _REGISTRY_FILE_LOCK:
        reg = _load_registry()
        dirty = False
        for sub_id in list(reg.keys()):
            live = [p for p in reg[sub_id] if _pid_alive(p)]
            if live != reg[sub_id]:
                dirty = True
                if live:
                    reg[sub_id] = live
                else:
                    del reg[sub_id]
        if dirty:
            _save_registry(reg)

    return orphan_pids
