"""Tests for bob3.brownfield.repo_mapper.run_repomapper_mcp (F-R7-611 / BF-1).

Verifies:
  - Module and function exist and are importable
  - run_repomapper_mcp returns a RepoMapperHandle
  - Delegates correctly to survey.run_repomapper_mcp
  - Accepts workspace and optional repomapper_cmd
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestRepoMapperModuleExists(unittest.TestCase):
    """Verify the module and function are importable."""

    def test_module_importable(self):
        import bob3.brownfield.repo_mapper  # noqa: F401

    def test_function_run_repomapper_mcp_defined(self):
        from bob3.brownfield import repo_mapper
        self.assertTrue(hasattr(repo_mapper, "run_repomapper_mcp"))
        self.assertTrue(callable(repo_mapper.run_repomapper_mcp))

    def test_repomapper_handle_importable(self):
        from bob3.brownfield.repo_mapper import RepoMapperHandle
        self.assertIsNotNone(RepoMapperHandle)


class TestRunRepomapperMcpReturnsHandle(unittest.TestCase):
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
        from bob3.brownfield.repo_mapper import run_repomapper_mcp, RepoMapperHandle
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/test_workspace")
        result = run_repomapper_mcp(workspace, repomapper_cmd=["echo"])
        self.assertIsInstance(result, RepoMapperHandle)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_handle_has_workspace(self, mock_popen):
        from bob3.brownfield.repo_mapper import run_repomapper_mcp
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/test_workspace")
        handle = run_repomapper_mcp(workspace, repomapper_cmd=["echo"])
        self.assertEqual(handle.workspace, workspace)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_handle_close_does_not_raise(self, mock_popen):
        from bob3.brownfield.repo_mapper import run_repomapper_mcp
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/test_workspace")
        handle = run_repomapper_mcp(workspace, repomapper_cmd=["echo"])
        handle.close()  # should not raise


class TestRunRepomapperMcpDelegates(unittest.TestCase):
    """run_repomapper_mcp in repo_mapper delegates to survey.run_repomapper_mcp."""

    def _make_mock_proc(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.poll.return_value = None
        return proc

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_custom_cmd_is_passed_through(self, mock_popen):
        from bob3.brownfield.repo_mapper import run_repomapper_mcp
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/workspace")
        custom_cmd = ["repomapper-custom", "--verbose"]
        run_repomapper_mcp(workspace, repomapper_cmd=custom_cmd)
        called_cmd = mock_popen.call_args[0][0]
        self.assertEqual(called_cmd[:2], custom_cmd)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_workspace_appears_in_popen_args(self, mock_popen):
        from bob3.brownfield.repo_mapper import run_repomapper_mcp
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/my_workspace")
        run_repomapper_mcp(workspace, repomapper_cmd=["repomapper-mcp"])
        called_cmd = mock_popen.call_args[0][0]
        self.assertIn(str(workspace), called_cmd)

    @patch("bob3.brownfield.survey.subprocess.Popen")
    def test_default_cmd_used_when_none(self, mock_popen):
        from bob3.brownfield.repo_mapper import run_repomapper_mcp
        mock_popen.return_value = self._make_mock_proc()
        workspace = Path("/tmp/workspace")
        run_repomapper_mcp(workspace)
        called_cmd = mock_popen.call_args[0][0]
        self.assertIn("repomapper-mcp", called_cmd[0])


class TestRunRepomapperMcpSignature(unittest.TestCase):
    """Verify function signature."""

    def test_accepts_workspace_positional(self):
        import inspect
        from bob3.brownfield.repo_mapper import run_repomapper_mcp
        sig = inspect.signature(run_repomapper_mcp)
        params = list(sig.parameters.keys())
        self.assertIn("workspace", params)

    def test_accepts_repomapper_cmd_optional(self):
        import inspect
        from bob3.brownfield.repo_mapper import run_repomapper_mcp
        sig = inspect.signature(run_repomapper_mcp)
        self.assertIn("repomapper_cmd", sig.parameters)
        param = sig.parameters["repomapper_cmd"]
        self.assertIsNone(param.default)


if __name__ == "__main__":
    unittest.main()
