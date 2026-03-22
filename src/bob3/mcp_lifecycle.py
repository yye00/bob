"""MCP Server Lifecycle Management for Bob3.

Manages the TITANS Memory MCP server lifecycle - starting it as a subprocess,
monitoring health, and ensuring graceful shutdown. Only TITANS Memory is managed
by Bob3; Perplexity and Puppeteer are available via the Claude Code environment.

CRITICAL: TITANS Memory is required for Bob3 operation. If the MCP server
fails to start, Bob3 must stop immediately with a clear error message.
"""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
import time

from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP, MCPServerConfig

logger = logging.getLogger(__name__)

_STARTUP_WAIT_SECONDS = 1.0
_SHUTDOWN_TIMEOUT_SECONDS = 5


class MCPStartupError(Exception):
    """Raised when the MCP server fails to start.

    This is a fatal error - Bob3 cannot operate without TITANS Memory.
    """


class MCPLifecycleManager:
    """Manages the lifecycle of a single MCP server subprocess.

    Handles starting, health checking, and stopping the TITANS Memory
    MCP server. Registers an atexit handler to ensure cleanup on exit.
    """

    def __init__(self, config: MCPServerConfig | None = None) -> None:
        self.config = config or TITANS_MEMORY_MCP
        self._process: subprocess.Popen | None = None

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
        # Validate required environment variables
        for var in self.config.env_vars:
            if not os.environ.get(var):
                raise MCPStartupError(
                    f"Required environment variable {var} is not set. "
                    f"TITANS Memory MCP server cannot start without it."
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

        # Register atexit handler to ensure cleanup
        atexit.register(self.stop)

        logger.info(
            "TITANS Memory MCP server started (pid=%d)", self._process.pid
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
        """
        if self._process is None:
            return

        pid = self._process.pid
        logger.info("Stopping TITANS Memory MCP server (pid=%d)...", pid)

        self._process.terminate()
        try:
            self._process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning(
                "MCP server did not stop gracefully, killing (pid=%d)", pid
            )
            self._process.kill()
            self._process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)

        self._process = None
        logger.info("TITANS Memory MCP server stopped (pid=%d)", pid)

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
    """Start the TITANS Memory MCP server using the singleton manager.

    Returns:
        The MCPLifecycleManager instance managing the server.

    Raises:
        MCPStartupError: If the server fails to start.
    """
    manager = get_mcp_manager()
    manager.start()
    return manager


def stop_mcp_server() -> None:
    """Stop the TITANS Memory MCP server if running."""
    global _manager
    if _manager is not None:
        _manager.stop()
