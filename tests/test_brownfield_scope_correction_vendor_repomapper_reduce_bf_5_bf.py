"""Tests for brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf module.

AC verification:
  - File exists: src/bob/brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf.py
  - Function defined: bob.brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf
                        .brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf
  - Function is callable and returns a summary dict.

Feature: Brownfield scope correction -- vendor RepoMapper, reduce BF-5/BF-6 to enforcement.
  (A) BF-1: RepoMapper MCP launcher (survey.launch_repomapper_mcp) is the thin client.
  (B) BF-5: Signal-B/C gated behind deep_resurrection_scan (resurrection.filter_signals_by_feature_flags).
  (C) BF-6: Interactive path delegates to AskUserQuestion; headless path branches (elicit.branch_on_mode).
  (D) CLAUDE.md contains only meta-loop guidance, no operator memory bullets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ===========================================================================
# AC: primary function importable and callable
# ===========================================================================


def test_brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf():
    """AC: function is importable, callable, and returns a structured dict."""
    from bob.brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf import (
        brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf,
    )

    result = brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf()

    assert isinstance(result, dict)
    assert "scope_reductions" in result
    assert isinstance(result["scope_reductions"], list)
    assert len(result["scope_reductions"]) >= 3


class TestModuleStructure:
    """Structural tests: file exists, function importable."""

    def test_source_file_exists(self):
        src = Path(__file__).parent.parent / "src" / "bob" / (
            "brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf.py"
        )
        assert src.exists(), f"Source file missing: {src}"

    def test_function_importable(self):
        from bob.brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf import (
            brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf,
        )
        assert callable(brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf)

    def test_function_returns_dict(self):
        from bob.brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf import (
            brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf,
        )
        result = brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf()
        assert isinstance(result, dict)


class TestScopeReductionA:
    """(A) BF-1: survey.launch_repomapper_mcp thin MCP client."""

    def test_survey_launch_repomapper_mcp_exists(self):
        from bob.brownfield import survey
        assert hasattr(survey, "launch_repomapper_mcp")
        assert callable(survey.launch_repomapper_mcp)

    def test_survey_repomapper_handle_exists(self):
        from bob.brownfield.survey import RepoMapperHandle
        assert RepoMapperHandle is not None

    def test_launch_repomapper_mcp_spawns_process(self, tmp_path):
        from bob.brownfield import survey

        fake_proc = MagicMock()
        fake_proc.stdin = MagicMock()
        fake_proc.stdout = MagicMock()
        fake_proc.stderr = MagicMock()
        fake_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=fake_proc):
            handle = survey.launch_repomapper_mcp(tmp_path)

        assert isinstance(handle, survey.RepoMapperHandle)
        assert handle.workspace == tmp_path

    def test_survey_db_is_cache_not_custom_impl(self, tmp_path):
        from bob.brownfield import survey
        # survey.db stores RepoMapper output, not a reimplementation
        assert hasattr(survey, "get_cached_survey")
        assert hasattr(survey, "store_cached_survey")
        assert callable(survey.get_cached_survey)
        assert callable(survey.store_cached_survey)

    def test_scope_reduction_summary_includes_bf1(self):
        from bob.brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf import (
            brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf,
        )
        result = brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf()
        reduction_ids = [r.get("id") for r in result["scope_reductions"]]
        assert "BF-1" in reduction_ids


class TestScopeReductionB:
    """(B) BF-5: resurrection.filter_signals_by_feature_flags gates Signal-B/C."""

    def test_filter_signals_exists(self):
        from bob.brownfield import resurrection
        assert hasattr(resurrection, "filter_signals_by_feature_flags")

    def _make_signal(self, kind: str):
        from bob.brownfield.resurrection import ResurrectionSignal
        return ResurrectionSignal(
            signal_kind=kind,
            evidence=[f"ev:{kind}"],
            staleness_days=5,
            recommended_action="finish_stub",
        )

    def test_signal_a_always_passes_through(self):
        from bob.brownfield.resurrection import filter_signals_by_feature_flags
        signals = [self._make_signal("stale_pr"), self._make_signal("stale_branch")]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        assert len(result) == 2

    def test_signal_b_blocked_by_default(self):
        from bob.brownfield.resurrection import filter_signals_by_feature_flags
        signals = [self._make_signal("export_without_impl")]
        result = filter_signals_by_feature_flags(signals)
        assert result == []

    def test_signal_c_blocked_by_default(self):
        from bob.brownfield.resurrection import filter_signals_by_feature_flags
        signals = [self._make_signal("todo_cluster")]
        result = filter_signals_by_feature_flags(signals)
        assert result == []

    def test_signal_b_c_pass_when_deep_scan_on(self):
        from bob.brownfield.resurrection import filter_signals_by_feature_flags
        signals = [
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        assert len(result) == 2

    def test_scope_reduction_summary_includes_bf5(self):
        from bob.brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf import (
            brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf,
        )
        result = brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf()
        reduction_ids = [r.get("id") for r in result["scope_reductions"]]
        assert "BF-5" in reduction_ids


class TestScopeReductionC:
    """(C) BF-6: elicit.branch_on_mode dispatches by mode."""

    def test_branch_on_mode_exists(self):
        from bob.brownfield import elicit
        assert hasattr(elicit, "branch_on_mode")
        assert callable(elicit.branch_on_mode)

    def test_interactive_mode_emits_ask_user_question(self):
        from bob.brownfield.elicit import branch_on_mode, ElicitationResult
        feature = SimpleNamespace(mode="interactive", description="do x", research_notes="")
        result = branch_on_mode(feature)
        assert isinstance(result, ElicitationResult)
        assert result.ask_user_question_emitted is True

    def test_headless_mode_branches(self):
        from bob.brownfield.elicit import branch_on_mode, ElicitationResult
        feature = SimpleNamespace(mode="headless", description="do x", research_notes="")
        result = branch_on_mode(feature)
        assert isinstance(result, ElicitationResult)
        assert len(result.candidates) > 0
        assert result.ask_user_question_emitted is False

    def test_scope_reduction_summary_includes_bf6(self):
        from bob.brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf import (
            brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf,
        )
        result = brownfield_scope_correction_vendor_repomapper_reduce_bf_5_bf()
        reduction_ids = [r.get("id") for r in result["scope_reductions"]]
        assert "BF-6" in reduction_ids


class TestClaudeMdContent:
    """(D) CLAUDE.md contains meta-loop guidance only, no operator memory bullets."""

    _CLAUDE_MD = Path(__file__).parent.parent / "src" / "bob" / "CLAUDE.md"

    def test_claude_md_exists(self):
        assert self._CLAUDE_MD.exists()

    def test_claude_md_has_meta_loop_guidance(self):
        content = self._CLAUDE_MD.read_text().lower()
        assert any(kw in content for kw in ("meta-loop", "worker", "guidance", "sub-agent"))

    def test_claude_md_no_operator_memory_bullets(self):
        import re
        content = self._CLAUDE_MD.read_text()
        uuid_re = re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
        )
        assert not uuid_re.search(content), "CLAUDE.md must not contain UUID feature IDs"
