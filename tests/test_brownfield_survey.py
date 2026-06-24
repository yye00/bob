"""Tests for brownfield survey module — BF-1 RepoMapper MCP launcher.

Covers:
  - launch_repomapper_mcp exists and is callable
  - Returns a RepoMapperHandle with the expected interface
  - MCP stdio communication (symbol_graph, pagerank, _call_tool)
  - RepoMapperHandle.close() terminates the process
  - get_cached_survey / store_cached_survey round-trip
  - survey() cache miss path launches RepoMapper and stores result
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob3.brownfield.survey import (
    RepoMapperHandle,
    get_cached_survey,
    launch_repomapper_mcp,
    store_cached_survey,
    survey,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_proc(stdout_lines: list[str] | None = None) -> MagicMock:
    proc = MagicMock(spec=subprocess.Popen)
    proc.stdin = MagicMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.poll.return_value = None
    if stdout_lines:
        proc.stdout.readline.side_effect = stdout_lines
    return proc


# ---------------------------------------------------------------------------
# launch_repomapper_mcp
# ---------------------------------------------------------------------------


class TestLaunchRepomapperMcp:
    def test_function_exists(self):
        assert callable(launch_repomapper_mcp)

    def test_returns_handle_type(self, tmp_path):
        proc = _make_fake_proc()
        with patch("subprocess.Popen", return_value=proc):
            handle = launch_repomapper_mcp(tmp_path)
        assert isinstance(handle, RepoMapperHandle)

    def test_handle_has_workspace(self, tmp_path):
        proc = _make_fake_proc()
        with patch("subprocess.Popen", return_value=proc):
            handle = launch_repomapper_mcp(tmp_path)
        assert handle.workspace == tmp_path

    def test_uses_default_cmd_when_none_given(self, tmp_path):
        proc = _make_fake_proc()
        with patch("subprocess.Popen", return_value=proc) as mock_popen:
            launch_repomapper_mcp(tmp_path)
        cmd = mock_popen.call_args[0][0]
        assert "repomapper-mcp" in cmd

    def test_custom_cmd_overrides_default(self, tmp_path):
        proc = _make_fake_proc()
        custom = ["python", "-m", "repomapper"]
        with patch("subprocess.Popen", return_value=proc) as mock_popen:
            launch_repomapper_mcp(tmp_path, repomapper_cmd=custom)
        cmd = mock_popen.call_args[0][0]
        assert cmd[:3] == custom

    def test_workspace_appended_to_cmd(self, tmp_path):
        proc = _make_fake_proc()
        with patch("subprocess.Popen", return_value=proc) as mock_popen:
            launch_repomapper_mcp(tmp_path)
        cmd = mock_popen.call_args[0][0]
        assert str(tmp_path) in cmd

    def test_popen_uses_stdio_pipes(self, tmp_path):
        proc = _make_fake_proc()
        with patch("subprocess.Popen", return_value=proc) as mock_popen:
            launch_repomapper_mcp(tmp_path)
        kwargs = mock_popen.call_args[1]
        assert kwargs["stdin"] == subprocess.PIPE
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["text"] is True


# ---------------------------------------------------------------------------
# RepoMapperHandle
# ---------------------------------------------------------------------------


class TestRepoMapperHandleClose:
    def test_close_terminates_running_process(self, tmp_path):
        proc = _make_fake_proc()
        proc.poll.return_value = None
        handle = RepoMapperHandle(proc=proc, workspace=tmp_path)
        handle.close()
        proc.terminate.assert_called_once()

    def test_close_noop_when_already_exited(self, tmp_path):
        proc = _make_fake_proc()
        proc.poll.return_value = 0  # already exited
        handle = RepoMapperHandle(proc=proc, workspace=tmp_path)
        handle.close()
        proc.terminate.assert_not_called()


class TestRepoMapperHandleCallTool:
    def test_symbol_graph_sends_rpc(self, tmp_path):
        response = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"symbol": "Foo"}]},
        })
        proc = _make_fake_proc(stdout_lines=[response])
        handle = RepoMapperHandle(proc=proc, workspace=tmp_path)
        result = handle.symbol_graph()
        assert result == [{"symbol": "Foo"}]

    def test_pagerank_sends_top_n(self, tmp_path):
        response = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"file": "a.py", "rank": 0.9}]},
        })
        proc = _make_fake_proc(stdout_lines=[response])
        handle = RepoMapperHandle(proc=proc, workspace=tmp_path)
        result = handle.pagerank(top_n=5)
        written = proc.stdin.write.call_args[0][0]
        payload = json.loads(written)
        assert payload["params"]["arguments"]["top_n"] == 5
        assert result == [{"file": "a.py", "rank": 0.9}]

    def test_call_tool_raises_on_error_response(self, tmp_path):
        response = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        })
        proc = _make_fake_proc(stdout_lines=[response])
        handle = RepoMapperHandle(proc=proc, workspace=tmp_path)
        with pytest.raises(RuntimeError, match="RepoMapper MCP error"):
            handle.symbol_graph()


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------


class TestSurveyCacheRoundTrip:
    def test_cache_miss_returns_none(self, tmp_path):
        db = tmp_path / "survey.db"
        result = get_cached_survey(db, tmp_path)
        assert result is None

    def test_store_then_get_returns_payload(self, tmp_path):
        db = tmp_path / "survey.db"
        payload = {"symbol_graph": [{"sym": "X"}], "pagerank": []}
        store_cached_survey(db, tmp_path, payload)
        cached = get_cached_survey(db, tmp_path)
        assert cached == payload

    def test_different_workspace_is_cache_miss(self, tmp_path):
        db = tmp_path / "survey.db"
        other = tmp_path / "other"
        other.mkdir()
        payload = {"symbol_graph": [], "pagerank": []}
        store_cached_survey(db, tmp_path, payload)
        result = get_cached_survey(db, other)
        assert result is None

    def test_different_glob_is_cache_miss(self, tmp_path):
        db = tmp_path / "survey.db"
        payload = {"symbol_graph": [], "pagerank": []}
        store_cached_survey(db, tmp_path, payload, path_glob="**/*.py")
        result = get_cached_survey(db, tmp_path, path_glob="**/*.ts")
        assert result is None


# ---------------------------------------------------------------------------
# survey() high-level function
# ---------------------------------------------------------------------------


class TestSurveyHighLevel:
    def test_returns_cached_without_launching(self, tmp_path):
        db = tmp_path / "survey.db"
        payload = {"symbol_graph": [{"sym": "cached"}], "pagerank": []}
        store_cached_survey(db, tmp_path, payload)

        with patch("subprocess.Popen") as mock_popen:
            result = survey(tmp_path, db_path=db)

        mock_popen.assert_not_called()
        assert result == payload

    def test_cache_miss_launches_mcp_and_stores(self, tmp_path):
        db = tmp_path / "survey.db"
        sym_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"sym": "A"}]}})
        pr_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"rank": 1}]}})
        proc = _make_fake_proc(stdout_lines=[sym_resp, pr_resp])
        proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=proc):
            result = survey(tmp_path, db_path=db)

        assert "symbol_graph" in result
        assert "pagerank" in result
        # Check stored in cache
        cached = get_cached_survey(db, tmp_path)
        assert cached is not None

    def test_force_refresh_bypasses_cache(self, tmp_path):
        db = tmp_path / "survey.db"
        payload = {"symbol_graph": [], "pagerank": []}
        store_cached_survey(db, tmp_path, payload)

        sym_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"fresh": True}]}})
        pr_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": []}})
        proc = _make_fake_proc(stdout_lines=[sym_resp, pr_resp])
        proc.poll.return_value = 0

        with patch("subprocess.Popen", return_value=proc):
            result = survey(tmp_path, db_path=db, force_refresh=True)

        assert result["symbol_graph"] == [{"fresh": True}]
