"""Tests for brownfield scope correction (be676e0d).

Covers:
  (A) survey.launch_repomapper_mcp — stdio MCP launcher
  (B) resurrection.filter_signals_by_feature_flags — gate Signal-B/C
  (C) elicit.branch_on_mode — AskUserQuestion vs BRANCH dispatch
  (D) src/bob/CLAUDE.md exists with meta-loop guidance only
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.brownfield import survey, resurrection, elicit


# ===========================================================================
# (A) survey.launch_repomapper_mcp
# ===========================================================================


class TestLaunchRepomapperMcp:
    """Tests for survey.launch_repomapper_mcp."""

    def test_function_exists(self):
        assert hasattr(survey, "launch_repomapper_mcp")
        assert callable(survey.launch_repomapper_mcp)

    def test_returns_repomapper_handle(self, tmp_path):
        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        fake_proc.stderr = MagicMock()
        fake_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            handle = survey.launch_repomapper_mcp(tmp_path)

        assert isinstance(handle, survey.RepoMapperHandle)
        assert handle.proc is fake_proc
        assert handle.workspace == tmp_path

    def test_uses_default_cmd(self, tmp_path):
        fake_proc = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            survey.launch_repomapper_mcp(tmp_path)

        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "repomapper-mcp"
        assert str(tmp_path) in cmd

    def test_uses_custom_cmd(self, tmp_path):
        fake_proc = MagicMock()
        custom_cmd = ["python", "-m", "repomapper"]
        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            survey.launch_repomapper_mcp(tmp_path, repomapper_cmd=custom_cmd)

        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert cmd[:3] == custom_cmd

    def test_opens_stdio_pipes(self, tmp_path):
        fake_proc = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            survey.launch_repomapper_mcp(tmp_path)

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs.get("stdin") == subprocess.PIPE
        assert call_kwargs.get("stdout") == subprocess.PIPE

    def test_handle_close_terminates_process(self, tmp_path):
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None  # process still running

        with patch("subprocess.Popen", return_value=fake_proc):
            handle = survey.launch_repomapper_mcp(tmp_path)

        handle.close()
        fake_proc.terminate.assert_called_once()


# ===========================================================================
# (B) resurrection.filter_signals_by_feature_flags
# ===========================================================================


class TestFilterSignalsByFeatureFlags:
    """Tests for resurrection.filter_signals_by_feature_flags."""

    def test_function_exists(self):
        assert hasattr(resurrection, "filter_signals_by_feature_flags")
        assert callable(resurrection.filter_signals_by_feature_flags)

    def _make_signal(self, kind: str) -> resurrection.ResurrectionSignal:
        return resurrection.ResurrectionSignal(
            signal_kind=kind,
            evidence=[f"evidence for {kind}"],
            staleness_days=10,
            recommended_action="finish_stub",
        )

    def test_signal_a_always_passes(self):
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("stale_branch"),
        ]
        result = resurrection.filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        assert len(result) == 2
        assert all(s.signal_kind in {"stale_pr", "stale_branch"} for s in result)

    def test_signal_b_gated_by_default(self):
        signals = [self._make_signal("export_without_impl")]
        result = resurrection.filter_signals_by_feature_flags(signals)
        assert result == []

    def test_signal_c_gated_by_default(self):
        signals = [self._make_signal("todo_cluster")]
        result = resurrection.filter_signals_by_feature_flags(signals)
        assert result == []

    def test_signal_b_passes_when_deep_scan_enabled(self):
        signals = [self._make_signal("export_without_impl")]
        result = resurrection.filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        assert len(result) == 1
        assert result[0].signal_kind == "export_without_impl"

    def test_signal_c_passes_when_deep_scan_enabled(self):
        signals = [self._make_signal("todo_cluster")]
        result = resurrection.filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        assert len(result) == 1

    def test_mixed_signals_filtered_correctly(self):
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
            self._make_signal("stale_branch"),
        ]
        result = resurrection.filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        kinds = {s.signal_kind for s in result}
        assert kinds == {"stale_pr", "stale_branch"}

    def test_mixed_signals_all_pass_with_deep_scan(self):
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = resurrection.filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        assert len(result) == 3

    def test_empty_signals_list(self):
        result = resurrection.filter_signals_by_feature_flags([], deep_resurrection_scan=False)
        assert result == []

    def test_returns_new_list(self):
        signals = [self._make_signal("stale_pr")]
        result = resurrection.filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        assert result is not signals  # new list, not same object


# ===========================================================================
# (C) elicit.branch_on_mode
# ===========================================================================


class TestBranchOnMode:
    """Tests for elicit.branch_on_mode."""

    def test_function_exists(self):
        assert hasattr(elicit, "branch_on_mode")
        assert callable(elicit.branch_on_mode)

    def _make_feature(self, mode: str, description: str = "do something") -> SimpleNamespace:
        return SimpleNamespace(mode=mode, description=description, research_notes="")

    def test_interactive_mode_emits_ask_user_question(self):
        feature = self._make_feature("interactive")
        result = elicit.branch_on_mode(feature)
        assert isinstance(result, elicit.ElicitationResult)
        assert result.mode == "interactive"
        assert result.ask_user_question_emitted is True

    def test_interactive_mode_does_not_branch(self):
        feature = self._make_feature("interactive")
        result = elicit.branch_on_mode(feature)
        assert result.candidates == []

    def test_headless_mode_branches(self):
        feature = self._make_feature("headless")
        result = elicit.branch_on_mode(feature)
        assert isinstance(result, elicit.ElicitationResult)
        assert result.mode == "headless"
        assert len(result.candidates) > 0

    def test_headless_mode_does_not_emit_ask_user_question(self):
        feature = self._make_feature("headless")
        result = elicit.branch_on_mode(feature)
        assert result.ask_user_question_emitted is False

    def test_uses_feature_description_as_intent_stub(self):
        feature = self._make_feature("interactive", description="add auth middleware")
        result = elicit.branch_on_mode(feature)
        assert result.chosen is not None
        # The AskUserQuestion payload should reference the description
        payload_str = str(result.chosen)
        assert "add auth middleware" in payload_str

    def test_accepts_explicit_request(self):
        feature = self._make_feature("headless")
        request = elicit.ElicitationRequest(intent_stub="custom intent", candidate_count=2)
        result = elicit.branch_on_mode(feature, request=request)
        assert len(result.candidates) == 2

    def test_defaults_to_interactive_when_no_mode(self):
        feature = SimpleNamespace(description="do thing")  # no .mode attribute
        result = elicit.branch_on_mode(feature)
        assert result.mode == "interactive"


# ===========================================================================
# (D) src/bob/CLAUDE.md exists with meta-loop guidance
# ===========================================================================


class TestClaudeMd:
    """Tests for src/bob/CLAUDE.md content."""

    _CLAUDE_MD = Path(__file__).parent.parent / "src" / "bob" / "CLAUDE.md"

    def test_file_exists(self):
        assert self._CLAUDE_MD.exists(), "src/bob/CLAUDE.md must exist"

    def test_file_has_content(self):
        content = self._CLAUDE_MD.read_text()
        assert len(content.strip()) > 0

    def test_file_contains_meta_loop_guidance(self):
        content = self._CLAUDE_MD.read_text().lower()
        # Should mention meta-loop or worker guidance
        assert any(
            kw in content for kw in ("meta-loop", "worker", "guidance", "sub-agent")
        )

    def test_file_does_not_contain_operator_memory_bullets(self):
        content = self._CLAUDE_MD.read_text()
        # Operator memory bullets typically contain feature IDs (UUIDs)
        import re
        uuid_pattern = re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
        )
        assert not uuid_pattern.search(content), (
            "CLAUDE.md must not contain operator memory bullets (UUID feature IDs found)"
        )


# ===========================================================================
# Integration: bob.orchestrator import
# ===========================================================================


class TestOrchestratorIntegration:
    """Verify bob.orchestrator can be imported (integration AC)."""

    def test_orchestrator_imports_cleanly(self):
        import importlib
        mod = importlib.import_module("bob.orchestrator")
        assert mod is not None

    def test_brownfield_modules_importable(self):
        import importlib
        for module_name in [
            "bob.brownfield.survey",
            "bob.brownfield.resurrection",
            "bob.brownfield.elicit",
        ]:
            mod = importlib.import_module(module_name)
            assert mod is not None

    def test_survey_launch_repomapper_mcp_importable_from_package(self):
        from bob.brownfield.survey import launch_repomapper_mcp
        assert callable(launch_repomapper_mcp)

    def test_resurrection_filter_signals_importable_from_package(self):
        from bob.brownfield.resurrection import filter_signals_by_feature_flags
        assert callable(filter_signals_by_feature_flags)

    def test_elicit_branch_on_mode_importable_from_package(self):
        from bob.brownfield.elicit import branch_on_mode
        assert callable(branch_on_mode)
