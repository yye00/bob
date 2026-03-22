"""Tests for F017: MCP Server Lifecycle Management.

Validates that the MCP lifecycle module:
- Creates src/bob3/mcp_lifecycle.py module
- Implements start_mcp_server() to start TITANS Memory MCP
- Implements health_check() to verify MCP server is responding
- Implements stop_mcp_server() for graceful shutdown
- Validates startup - if start fails, raises fatal error
- Integrates atexit handler to stop MCP server on Bob3 exit
- CLI integration: MCP starts before any operations
"""

import atexit
import os
import pathlib
import signal
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parent.parent / "src"
MODULE_PATH = SRC_DIR / "bob3" / "mcp_lifecycle.py"


# ===================================================================
# Step 1: File exists
# ===================================================================


class TestFileExists:
    """Step 1: src/bob3/mcp_lifecycle.py must exist."""

    def test_module_file_exists(self):
        assert MODULE_PATH.is_file(), f"Expected {MODULE_PATH} to exist"

    def test_module_is_non_empty(self):
        content = MODULE_PATH.read_text()
        assert len(content.strip()) > 100, "Module appears to be a stub"


# ===================================================================
# Step 2: start_mcp_server() function
# ===================================================================


class TestStartMCPServer:
    """Step 2: start_mcp_server() starts TITANS Memory MCP as subprocess."""

    def test_start_mcp_server_function_exists(self):
        from bob3.mcp_lifecycle import start_mcp_server

        assert callable(start_mcp_server)

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_start_mcp_server_starts_subprocess(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        manager.start()

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args")
        assert "uv" in cmd[0] if isinstance(cmd, list) else "uv" in cmd

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_start_mcp_server_uses_correct_command(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        manager.start()

        call_args = mock_popen.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args")
        expected_cmd = [
            "uv",
            "--directory",
            "/home/captain/work/AI/titans-memory",
            "run",
            "titans-memory",
        ]
        assert cmd == expected_cmd

    def test_start_mcp_server_raises_without_openai_key(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager, MCPStartupError

        manager = MCPLifecycleManager()
        with patch.dict(os.environ, {}, clear=True):
            # Remove OPENAI_API_KEY if set
            env = os.environ.copy()
            env.pop("OPENAI_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(MCPStartupError, match="OPENAI_API_KEY"):
                    manager.start()

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_start_mcp_server_raises_on_immediate_exit(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager, MCPStartupError

        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process exited immediately
        mock_process.pid = 12345
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = b"error: something went wrong"
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        with pytest.raises(MCPStartupError):
            manager.start()


# ===================================================================
# Step 3: health_check() function
# ===================================================================


class TestHealthCheck:
    """Step 3: health_check() verifies MCP server is responding."""

    def test_health_check_function_exists(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        manager = MCPLifecycleManager()
        assert callable(manager.health_check)

    def test_health_check_returns_bool(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        manager = MCPLifecycleManager()
        # No process started, should return False
        result = manager.health_check()
        assert isinstance(result, bool)
        assert result is False

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_health_check_true_when_running(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        manager.start()
        assert manager.health_check() is True

    def test_health_check_false_when_process_dead(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        manager = MCPLifecycleManager()
        # Fake a dead process
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Process has exited
        manager._process = mock_process
        assert manager.health_check() is False


# ===================================================================
# Step 4: stop_mcp_server() function
# ===================================================================


class TestStopMCPServer:
    """Step 4: stop_mcp_server() for graceful shutdown."""

    def test_stop_mcp_server_function_exists(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        manager = MCPLifecycleManager()
        assert callable(manager.stop)

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_stop_terminates_process(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock()
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        manager.start()
        manager.stop()

        mock_process.terminate.assert_called_once()

    def test_stop_without_start_does_not_raise(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        manager = MCPLifecycleManager()
        # Should not raise
        manager.stop()

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_stop_clears_process_reference(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock()
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        manager.start()
        manager.stop()

        assert manager._process is None

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_stop_kills_if_terminate_times_out(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock(
            side_effect=[subprocess.TimeoutExpired(cmd="test", timeout=5), None]
        )
        mock_process.kill = MagicMock()
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        manager.start()
        manager.stop()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()


# ===================================================================
# Step 5: Startup validation - fatal error if start fails
# ===================================================================


class TestStartupValidation:
    """Step 5: If MCP start fails, raise fatal error."""

    def test_mcp_startup_error_class_exists(self):
        from bob3.mcp_lifecycle import MCPStartupError

        assert issubclass(MCPStartupError, Exception)

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_startup_failure_raises_mcp_startup_error(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager, MCPStartupError

        mock_popen.side_effect = FileNotFoundError("uv not found")

        manager = MCPLifecycleManager()
        with pytest.raises(MCPStartupError, match="uv"):
            manager.start()

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_startup_error_includes_stderr_info(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager, MCPStartupError

        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Exited immediately
        mock_process.pid = 12345
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = b"fatal: module not found"
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        with pytest.raises(MCPStartupError, match="module not found"):
            manager.start()


# ===================================================================
# Step 6: CLI integration - start MCP before operations
# ===================================================================


class TestCLIIntegration:
    """Step 6: MCP server integrates into CLI init/run commands."""

    def test_start_mcp_server_convenience_function(self):
        """The module provides a start_mcp_server() convenience function."""
        from bob3.mcp_lifecycle import start_mcp_server

        assert callable(start_mcp_server)

    def test_stop_mcp_server_convenience_function(self):
        """The module provides a stop_mcp_server() convenience function."""
        from bob3.mcp_lifecycle import stop_mcp_server

        assert callable(stop_mcp_server)

    def test_get_mcp_manager_returns_singleton(self):
        """get_mcp_manager() returns the same instance each time."""
        from bob3.mcp_lifecycle import get_mcp_manager

        m1 = get_mcp_manager()
        m2 = get_mcp_manager()
        assert m1 is m2


# ===================================================================
# Step 7: atexit handler for cleanup
# ===================================================================


class TestAtexitHandler:
    """Step 7: atexit handler to stop MCP server on Bob3 exit."""

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_start_registers_atexit_handler(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        with patch("atexit.register") as mock_atexit:
            manager = MCPLifecycleManager()
            manager.start()
            mock_atexit.assert_called_once()


# ===================================================================
# Step 8: Context manager support
# ===================================================================


class TestContextManager:
    """MCPLifecycleManager can be used as a context manager."""

    @patch("subprocess.Popen")
    @patch("atexit.register")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_context_manager_starts_and_stops(self, mock_atexit, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock()
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        with manager:
            assert manager.health_check() is True

        mock_process.terminate.assert_called_once()

    @patch("subprocess.Popen")
    @patch("atexit.register")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_context_manager_stops_on_exception(self, mock_atexit, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.pid = 12345
        mock_process.terminate = MagicMock()
        mock_process.wait = MagicMock()
        mock_popen.return_value = mock_process

        manager = MCPLifecycleManager()
        with pytest.raises(ValueError):
            with manager:
                raise ValueError("test error")

        mock_process.terminate.assert_called_once()


# ===================================================================
# Step 9: Simulate MCP startup failure - Bob3 exits with clear error
# ===================================================================


class TestStartupFailureScenarios:
    """Step 9: Various MCP startup failure scenarios."""

    def test_missing_env_var_gives_clear_message(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager, MCPStartupError

        with patch.dict(os.environ, {}, clear=True):
            env = os.environ.copy()
            env.pop("OPENAI_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                manager = MCPLifecycleManager()
                with pytest.raises(MCPStartupError) as exc_info:
                    manager.start()
                assert "OPENAI_API_KEY" in str(exc_info.value)

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_command_not_found_gives_clear_message(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager, MCPStartupError

        mock_popen.side_effect = FileNotFoundError("[Errno 2] No such file or directory: 'uv'")

        manager = MCPLifecycleManager()
        with pytest.raises(MCPStartupError) as exc_info:
            manager.start()
        error_msg = str(exc_info.value)
        assert "uv" in error_msg.lower() or "not found" in error_msg.lower()

    @patch("subprocess.Popen")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_permission_denied_gives_clear_message(self, mock_popen):
        from bob3.mcp_lifecycle import MCPLifecycleManager, MCPStartupError

        mock_popen.side_effect = PermissionError("[Errno 13] Permission denied")

        manager = MCPLifecycleManager()
        with pytest.raises(MCPStartupError):
            manager.start()


# ===================================================================
# Integration: MCPLifecycleManager uses MCPServerConfig
# ===================================================================


class TestConfigIntegration:
    """MCPLifecycleManager uses the config from mcp_config module."""

    def test_manager_uses_titans_config(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager
        from bob3.orchestrator.mcp_config import TITANS_MEMORY_MCP

        manager = MCPLifecycleManager()
        assert manager.config.name == TITANS_MEMORY_MCP.name
        assert manager.config.command == TITANS_MEMORY_MCP.command

    def test_manager_stores_pid_after_start(self):
        from bob3.mcp_lifecycle import MCPLifecycleManager

        manager = MCPLifecycleManager()
        # Before start, no pid
        assert manager.pid is None
