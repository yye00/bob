"""Integration tests for brownfield scope correction (F-R7-611).

Tests that the three BF scope-reduction modules integrate correctly:
  (A) survey.run_repomapper_mcp — launches and returns a RepoMapperHandle
  (B) resurrection.filter_signals_by_feature_flag — gates Signal-B/C properly
  (C) elicit.route_by_mode — routes to AskUserQuestion or BRANCH correctly
  (D) Integration with bob.orchestrator import structure
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.brownfield import survey, resurrection, elicit


# ===========================================================================
# (A) survey.run_repomapper_mcp integration
# ===========================================================================


class TestSurveyRunRepomapperMcp:
    """Integration: run_repomapper_mcp returns a handle and delegates correctly."""

    def test_returns_repo_mapper_handle(self, tmp_path):
        """run_repomapper_mcp returns a RepoMapperHandle instance."""
        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc):
            handle = survey.run_repomapper_mcp(tmp_path)
        assert isinstance(handle, survey.RepoMapperHandle)
        handle.close()

    def test_handle_has_symbol_graph_and_pagerank_methods(self, tmp_path):
        """Returned handle exposes symbol_graph and pagerank methods."""
        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        with patch("subprocess.Popen", return_value=fake_proc):
            handle = survey.run_repomapper_mcp(tmp_path)
        assert callable(handle.symbol_graph)
        assert callable(handle.pagerank)
        handle.close()

    def test_custom_repomapper_cmd_is_forwarded(self, tmp_path):
        """Custom repomapper_cmd is passed to Popen."""
        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        custom_cmd = ["my-repomapper", "--verbose"]
        with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
            survey.run_repomapper_mcp(tmp_path, repomapper_cmd=custom_cmd)
        called_cmd = mock_popen.call_args[0][0]
        assert called_cmd[0] == "my-repomapper"
        assert called_cmd[1] == "--verbose"


# ===========================================================================
# (B) resurrection.filter_signals_by_feature_flag integration
# ===========================================================================


class TestResurrectionFilterSignalsByFeatureFlag:
    """Integration: filter_signals_by_feature_flag gates Signal-B/C correctly."""

    def _make_signal(self, kind: str) -> resurrection.ResurrectionSignal:
        return resurrection.ResurrectionSignal(
            signal_kind=kind,
            evidence=[f"test evidence for {kind}"],
            staleness_days=30,
            recommended_action="finish_stub",
        )

    def test_signal_a_always_passes(self):
        """Signal-A (stale_pr) always passes regardless of deep_scan flag."""
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = resurrection.filter_signals_by_feature_flag(signals, deep_resurrection_scan=False)
        kinds = [s.signal_kind for s in result]
        assert "stale_pr" in kinds
        assert "export_without_impl" not in kinds
        assert "todo_cluster" not in kinds

    def test_deep_scan_true_passes_all(self):
        """When deep_resurrection_scan=True, all signal kinds pass."""
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = resurrection.filter_signals_by_feature_flag(signals, deep_resurrection_scan=True)
        assert len(result) == 3

    def test_deep_scan_false_filters_b_and_c(self):
        """When deep_resurrection_scan=False, Signal-B and Signal-C are filtered."""
        signals = [
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = resurrection.filter_signals_by_feature_flag(signals, deep_resurrection_scan=False)
        assert result == []

    def test_stale_branch_signal_passes(self):
        """stale_branch is Signal-A and always passes."""
        signals = [self._make_signal("stale_branch")]
        result = resurrection.filter_signals_by_feature_flag(signals)
        assert len(result) == 1
        assert result[0].signal_kind == "stale_branch"

    def test_empty_signals_returns_empty(self):
        """Empty input list → empty output."""
        result = resurrection.filter_signals_by_feature_flag([])
        assert result == []


# ===========================================================================
# (C) elicit.route_by_mode integration
# ===========================================================================


class TestElicitRouteByMode:
    """Integration: route_by_mode dispatches to interactive or headless path."""

    def _make_feature(self, mode: str) -> SimpleNamespace:
        return SimpleNamespace(
            mode=mode,
            description="add user authentication to the API",
            research_notes="See BF-6 spec for context",
        )

    def test_interactive_mode_emits_ask_user_question(self):
        """Interactive mode returns ElicitationResult with ask_user_question_emitted=True."""
        feature = self._make_feature("interactive")
        result = elicit.route_by_mode(feature)
        assert isinstance(result, elicit.ElicitationResult)
        assert result.mode == "interactive"
        assert result.ask_user_question_emitted is True

    def test_headless_mode_returns_candidates(self):
        """Headless mode returns ElicitationResult with candidates populated."""
        feature = self._make_feature("headless")
        result = elicit.route_by_mode(feature)
        assert isinstance(result, elicit.ElicitationResult)
        assert result.mode == "headless"
        assert isinstance(result.candidates, list)
        assert len(result.candidates) > 0

    def test_headless_mode_does_not_emit_ask_user_question(self):
        """Headless mode never emits AskUserQuestion."""
        feature = self._make_feature("headless")
        result = elicit.route_by_mode(feature)
        assert result.ask_user_question_emitted is False

    def test_interactive_mode_does_not_have_candidates(self):
        """Interactive mode does not populate candidates (that's headless-only)."""
        feature = self._make_feature("interactive")
        result = elicit.route_by_mode(feature)
        assert result.candidates == []

    def test_pre_built_request_is_used_when_provided(self):
        """When a pre-built request is provided, it is used directly."""
        feature = self._make_feature("headless")
        request = elicit.ElicitationRequest(
            intent_stub="fix the auth bug",
            candidate_count=2,
        )
        result = elicit.route_by_mode(feature, request=request)
        assert len(result.candidates) == 2

    def test_mode_attribute_missing_defaults_to_interactive(self):
        """Feature with no .mode attribute defaults to interactive mode."""
        feature = SimpleNamespace(description="some task")
        result = elicit.route_by_mode(feature)
        assert result.mode == "interactive"
        assert result.ask_user_question_emitted is True


# ===========================================================================
# (D) Module import integration — bob.orchestrator wiring
# ===========================================================================


class TestBrownfieldOrchestratorImports:
    """Integration: all required functions are importable at the bob package level."""

    def test_survey_run_repomapper_mcp_importable(self):
        """bob.brownfield.survey.run_repomapper_mcp is importable."""
        from bob.brownfield.survey import run_repomapper_mcp
        assert callable(run_repomapper_mcp)

    def test_resurrection_filter_signals_by_feature_flag_importable(self):
        """bob.brownfield.resurrection.filter_signals_by_feature_flag is importable."""
        from bob.brownfield.resurrection import filter_signals_by_feature_flag
        assert callable(filter_signals_by_feature_flag)

    def test_elicit_route_by_mode_importable(self):
        """bob.brownfield.elicit.route_by_mode is importable."""
        from bob.brownfield.elicit import route_by_mode
        assert callable(route_by_mode)

    def test_brownfield_package_importable(self):
        """bob.brownfield package imports without error."""
        import bob.brownfield
        assert bob.brownfield is not None

    def test_all_three_modules_importable_together(self):
        """All three brownfield scope-correction modules import together without conflict."""
        from bob.brownfield import survey as s, resurrection as r, elicit as e
        assert s is not None
        assert r is not None
        assert e is not None
