"""MCP Server Lifecycle Management for Bob3.

Manages the bob3-memory MCP server lifecycle - starting it as a subprocess,
monitoring health, and ensuring graceful shutdown. Only bob3-memory is managed
by Bob3; Perplexity and Puppeteer are available via the Claude Code environment.

CRITICAL: bob3-memory is required for Bob3 operation. If the MCP server
fails to start, Bob3 must stop immediately with a clear error message.
"""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
import threading
import time

from bob3.orchestrator.mcp_config import BOB3_MEMORY_MCP, MCPServerConfig

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

    This is a fatal error - Bob3 cannot operate without bob3-memory.
    """


class MCPLifecycleManager:
    """Manages the lifecycle of a single MCP server subprocess.

    Handles starting, health checking, and stopping the bob3-memory
    MCP server. Registers an atexit handler to ensure cleanup on exit.
    """

    def __init__(self, config: MCPServerConfig | None = None) -> None:
        self.config = config or BOB3_MEMORY_MCP
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
        # (e.g. `bob3 init` then `bob3 run` within one process).
        if self._process is not None and self._process.poll() is None:
            logger.debug(
                "bob3-memory MCP server already running (pid=%d); skipping start",
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
                "bob3-memory MCP server started (pid=%d)", self._process.pid
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
        logger.info("Stopping bob3-memory MCP server (pid=%d)...", pid)

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
        logger.info("bob3-memory MCP server stopped (pid=%d)", pid)

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
    """Start the bob3-memory MCP server using the singleton manager.

    Returns:
        The MCPLifecycleManager instance managing the server.

    Raises:
        MCPStartupError: If the server fails to start.
    """
    manager = get_mcp_manager()
    manager.start()
    return manager


def stop_mcp_server() -> None:
    """Stop the bob3-memory MCP server if running."""
    global _manager
    if _manager is not None:
        _manager.stop()
