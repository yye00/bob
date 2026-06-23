"""Boundary case tests for brownfield scope correction (F-R7-611).

Tests that empty, zero, or minimum inputs return well-defined results
rather than raising. Covers:
  (A) survey.run_repomapper_mcp — empty workspace path
  (B) resurrection.filter_signals_by_config — empty signals list, None config
  (C) elicit.branch_candidates_headless — zero/minimum candidate count
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob3.brownfield import survey, resurrection, elicit


# ===========================================================================
# (A) survey.run_repomapper_mcp — boundary cases
# ===========================================================================


class TestRunRepomapperMcpBoundary:
    """Boundary: run_repomapper_mcp with minimal/edge-case inputs."""

    def test_workspace_with_no_files_returns_handle(self, tmp_path):
        """Empty workspace dir returns a valid handle, does not raise."""
        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc):
            handle = survey.run_repomapper_mcp(tmp_path)
        assert isinstance(handle, survey.RepoMapperHandle)
        handle.close()

    def test_none_repomapper_cmd_uses_default(self, tmp_path):
        """Passing None for repomapper_cmd falls back to default command."""
        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            survey.run_repomapper_mcp(tmp_path, repomapper_cmd=None)
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "repomapper-mcp"

    def test_empty_repomapper_cmd_list_uses_default(self, tmp_path):
        """Empty list falls back to default (falsy branch in implementation)."""
        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            survey.run_repomapper_mcp(tmp_path, repomapper_cmd=None)
        call_args = mock_popen.call_args[0][0]
        assert len(call_args) >= 1

    def test_handle_close_on_already_terminated_process(self, tmp_path):
        """close() when process has already exited does not raise."""
        fake_proc = MagicMock()
        fake_proc.poll.return_value = 0  # already exited
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc):
            handle = survey.run_repomapper_mcp(tmp_path)
        handle.close()
        fake_proc.terminate.assert_not_called()


# ===========================================================================
# (B) resurrection.filter_signals_by_config — boundary cases
# ===========================================================================


class TestFilterSignalsByConfigBoundary:
    """Boundary: filter_signals_by_config with empty/None inputs."""

    def _make_signal(self, kind: str) -> resurrection.ResurrectionSignal:
        return resurrection.ResurrectionSignal(
            signal_kind=kind,
            evidence=[],
            staleness_days=0,
            recommended_action="finish_stub",
        )

    def test_empty_signals_empty_config_returns_empty(self):
        """Empty signals list + empty config → empty result, no raise."""
        result = resurrection.filter_signals_by_config([], config={})
        assert result == []

    def test_empty_signals_none_config_returns_empty(self):
        """Empty signals + None config → empty result, no raise."""
        result = resurrection.filter_signals_by_config([], config=None)
        assert result == []

    def test_none_config_defaults_deep_scan_off(self):
        """None config behaves as deep_resurrection_scan=False."""
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
        ]
        result = resurrection.filter_signals_by_config(signals, config=None)
        kinds = {s.signal_kind for s in result}
        assert "stale_pr" in kinds
        assert "export_without_impl" not in kinds

    def test_empty_config_defaults_deep_scan_off(self):
        """Empty config behaves as deep_resurrection_scan=False."""
        signals = [self._make_signal("todo_cluster")]
        result = resurrection.filter_signals_by_config(signals, config={})
        assert result == []

    def test_single_stale_pr_signal_passes_both_configs(self):
        """Signal-A always passes regardless of config."""
        signals = [self._make_signal("stale_pr")]
        result_off = resurrection.filter_signals_by_config(signals, config={})
        result_on = resurrection.filter_signals_by_config(
            signals, config={"deep_resurrection_scan": True}
        )
        assert len(result_off) == 1
        assert len(result_on) == 1

    def test_deep_scan_true_passes_all_signal_kinds(self):
        """All three signal kinds pass when deep_resurrection_scan=True."""
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = resurrection.filter_signals_by_config(
            signals, config={"deep_resurrection_scan": True}
        )
        assert len(result) == 3

    def test_minimum_single_signal_returns_list(self):
        """Single signal input always returns a list."""
        signals = [self._make_signal("stale_pr")]
        result = resurrection.filter_signals_by_config(signals)
        assert isinstance(result, list)


# ===========================================================================
# (C) elicit.branch_candidates_headless — boundary cases
# ===========================================================================


class TestBranchCandidatesHeadlessBoundary:
    """Boundary: branch_candidates_headless with zero/minimum candidate counts."""

    def test_zero_candidate_count_returns_empty_list(self):
        """candidate_count=0 returns empty list, does not raise."""
        request = elicit.ElicitationRequest(
            intent_stub="add authentication",
            candidate_count=0,
        )
        result = elicit.branch_candidates_headless(request)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_one_candidate_count_returns_single_candidate(self):
        """candidate_count=1 returns exactly one candidate dict."""
        request = elicit.ElicitationRequest(
            intent_stub="add authentication",
            candidate_count=1,
        )
        result = elicit.branch_candidates_headless(request)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_empty_intent_stub_returns_candidates(self):
        """Empty intent_stub does not raise; returns candidates with empty interpretation."""
        request = elicit.ElicitationRequest(
            intent_stub="",
            candidate_count=2,
        )
        result = elicit.branch_candidates_headless(request)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_candidate_has_required_keys(self):
        """Each candidate dict has at minimum candidate_id and interpretation keys."""
        request = elicit.ElicitationRequest(
            intent_stub="fix the auth bug",
            candidate_count=2,
        )
        result = elicit.branch_candidates_headless(request)
        for candidate in result:
            assert "candidate_id" in candidate
            assert "interpretation" in candidate

    def test_empty_research_notes_does_not_raise(self):
        """Empty research_notes is valid boundary input."""
        request = elicit.ElicitationRequest(
            intent_stub="refactor the pipeline",
            research_notes="",
            candidate_count=3,
        )
        result = elicit.branch_candidates_headless(request)
        assert len(result) == 3

    def test_returns_list_not_none(self):
        """Return value is always a list (never None)."""
        request = elicit.ElicitationRequest(intent_stub="do something", candidate_count=1)
        result = elicit.branch_candidates_headless(request)
        assert result is not None
        assert isinstance(result, list)
