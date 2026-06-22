"""Tests for bob3.brownfield.survey.run_repomapper_mcp (F-R7-611 / BF-1 scope reduction).

ACs verified:
  - Function defined: bob3.brownfield.survey.run_repomapper_mcp
  - run_repomapper_mcp launches the MCP server and returns a RepoMapperHandle
  - run_repomapper_mcp accepts workspace and optional repomapper_cmd overrides
  - run_repomapper_mcp delegates to launch_repomapper_mcp (thin wrapper)
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bob3.brownfield.survey import (
    RepoMapperHandle,
    launch_repomapper_mcp,
    run_repomapper_mcp,
)


class TestRunRepoMapperMCPExists(unittest.TestCase):
    """Verify the function is importable and callable."""

    def test_function_is_importable(self):
        from bob3.brownfield import survey
        self.assertTrue(hasattr(survey, "run_repomapper_mcp"))

    def test_function_is_callable(self):
        self.assertTrue(callable(run_repomapper_mcp))


class TestRunRepoMapperMCPReturnsHandle(unittest.TestCase):
    """run_repomapper_mcp must return a RepoMapperHandle."""

    def _make_mock_proc(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.poll.return_value = None
        return proc

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_returns_repomapper_handle(self, mock_popen):
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/test_workspace")
        result = run_repomapper_mcp(workspace, repomapper_cmd=["echo"])
        self.assertIsInstance(result, RepoMapperHandle)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_handle_has_workspace(self, mock_popen):
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/test_workspace")
        handle = run_repomapper_mcp(workspace, repomapper_cmd=["echo"])
        self.assertEqual(handle.workspace, workspace)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_handle_has_proc(self, mock_popen):
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/test_workspace")
        handle = run_repomapper_mcp(workspace, repomapper_cmd=["echo"])
        self.assertIsNotNone(handle.proc)


class TestRunRepoMapperMCPDelegates(unittest.TestCase):
    """run_repomapper_mcp must delegate to launch_repomapper_mcp."""

    def _make_mock_proc(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.poll.return_value = None
        return proc

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_custom_cmd_is_passed_through(self, mock_popen):
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/workspace")
        custom_cmd = ["repomapper-custom", "--flag"]
        run_repomapper_mcp(workspace, repomapper_cmd=custom_cmd)
        called_cmd = mock_popen.call_args[0][0]
        self.assertEqual(called_cmd[:2], custom_cmd)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_workspace_appended_to_cmd(self, mock_popen):
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/my_workspace")
        run_repomapper_mcp(workspace, repomapper_cmd=["repomapper-mcp"])
        called_cmd = mock_popen.call_args[0][0]
        self.assertIn(str(workspace), called_cmd)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_default_cmd_used_when_none(self, mock_popen):
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/workspace")
        run_repomapper_mcp(workspace)
        called_cmd = mock_popen.call_args[0][0]
        self.assertIn("repomapper-mcp", called_cmd[0])


class TestRunRepoMapperMCPSignature(unittest.TestCase):
    """Verify function signature matches expectations."""

    def test_accepts_workspace_positional(self):
        import inspect
        sig = inspect.signature(run_repomapper_mcp)
        params = list(sig.parameters.keys())
        self.assertIn("workspace", params)

    def test_accepts_repomapper_cmd_optional(self):
        import inspect
        sig = inspect.signature(run_repomapper_mcp)
        self.assertIn("repomapper_cmd", sig.parameters)
        param = sig.parameters["repomapper_cmd"]
        self.assertIsNone(param.default)


if __name__ == "__main__":
    unittest.main()
