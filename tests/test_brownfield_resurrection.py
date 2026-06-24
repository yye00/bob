"""Tests for brownfield resurrection module — BF-5 graveyard signal.

Covers:
  - signal_graveyard_prs alias exists and is callable
  - filter_signals_by_feature_flags gates Signal-B/C behind deep_resurrection_scan
  - Signal-A always passes through filter regardless of flag
  - detect_resurrection_signals orchestrates all signals
  - write_resurrection_report produces a markdown file
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bob.brownfield.resurrection import (
    ResurrectionSignal,
    detect_resurrection_signals,
    detect_stale_pr,
    detect_stale_branch,
    detect_export_without_impl,
    detect_todo_clusters,
    filter_signals_by_feature_flags,
    get_graveyard_signal,
    signal_graveyard_prs,
    write_resurrection_report,
)


# ---------------------------------------------------------------------------
# signal_graveyard_prs alias
# ---------------------------------------------------------------------------


class TestSignalGraveyardPrsAlias:
    def test_alias_exists(self):
        assert callable(signal_graveyard_prs)

    def test_alias_is_same_as_get_graveyard_signal(self):
        assert signal_graveyard_prs is get_graveyard_signal

    def test_returns_list(self):
        result = signal_graveyard_prs(repo="", feature_keywords=[])
        assert isinstance(result, list)

    def test_returns_empty_when_gh_unavailable(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = signal_graveyard_prs(repo="org/repo", feature_keywords=["auth"])
        assert result == []

    def test_returns_stale_pr_signals_only(self):
        gh_output = '[{"number": 42, "title": "auth feature", "body": "", "url": "https://github.com/org/repo/pull/42", "updatedAt": "2024-01-01"}]'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = gh_output

        with patch("subprocess.run", return_value=mock_result):
            signals = signal_graveyard_prs(repo="org/repo", feature_keywords=["auth"])

        for sig in signals:
            assert sig.signal_kind == "stale_pr"


# ---------------------------------------------------------------------------
# filter_signals_by_feature_flags
# ---------------------------------------------------------------------------


class TestFilterSignalsByFeatureFlags:
    def _make_signal(self, kind: str) -> ResurrectionSignal:
        return ResurrectionSignal(
            signal_kind=kind,
            evidence=[f"evidence for {kind}"],
            staleness_days=30,
            recommended_action="finish_stub",
        )

    def test_signal_a_passes_through_when_flag_off(self):
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("stale_branch"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        assert len(result) == 2

    def test_signal_b_filtered_when_flag_off(self):
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        assert all(s.signal_kind != "export_without_impl" for s in result)
        assert len(result) == 1

    def test_signal_c_filtered_when_flag_off(self):
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("todo_cluster"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        assert all(s.signal_kind != "todo_cluster" for s in result)
        assert len(result) == 1

    def test_all_signals_pass_when_flag_on(self):
        signals = [
            self._make_signal("stale_pr"),
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=True)
        assert len(result) == 3

    def test_empty_input_returns_empty(self):
        result = filter_signals_by_feature_flags([], deep_resurrection_scan=False)
        assert result == []

    def test_only_deep_signals_filtered_to_empty(self):
        signals = [
            self._make_signal("export_without_impl"),
            self._make_signal("todo_cluster"),
        ]
        result = filter_signals_by_feature_flags(signals, deep_resurrection_scan=False)
        assert result == []


# ---------------------------------------------------------------------------
# detect_stale_pr / detect_stale_branch / detect_export_without_impl / detect_todo_clusters
# ---------------------------------------------------------------------------


class TestDetectStalePr:
    def test_returns_list(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = detect_stale_pr(repo="org/repo", feature_keywords=[])
        assert isinstance(result, list)

    def test_returns_empty_without_gh(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = detect_stale_pr(repo="org/repo", feature_keywords=["feat"])
        assert result == []


class TestDetectStaleBranch:
    def test_returns_list(self, tmp_path):
        result = detect_stale_branch(str(tmp_path), touches=[])
        assert isinstance(result, list)

    def test_returns_empty_when_no_git(self, tmp_path):
        result = detect_stale_branch(str(tmp_path), touches=["main.py"])
        assert isinstance(result, list)


class TestDetectExportWithoutImpl:
    def test_returns_list(self, tmp_path):
        result = detect_export_without_impl(str(tmp_path), touches=[])
        assert isinstance(result, list)

    def test_detects_missing_exported_symbol(self, tmp_path):
        # Symbol exported in __all__ but not defined at all → signal fires
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            '__all__ = ["missing_func"]\n\nx = 1\n'
        )
        signals = detect_export_without_impl(str(tmp_path), touches=["mod.py"])
        assert any(s.signal_kind == "export_without_impl" for s in signals)

    def test_no_signal_for_real_impl(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            '__all__ = ["my_func"]\n\ndef my_func():\n    return 42\n'
        )
        signals = detect_export_without_impl(str(tmp_path), touches=["mod.py"])
        assert all(s.signal_kind != "export_without_impl" for s in signals)


class TestDetectTodoClusters:
    def test_returns_list(self, tmp_path):
        result = detect_todo_clusters(str(tmp_path), touches=[])
        assert isinstance(result, list)

    def test_detects_cluster(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text(
            "# TODO: do a\n# TODO: do b\n# TODO: do c\nx = 1\n"
        )
        signals = detect_todo_clusters(str(tmp_path), touches=["mod.py"], min_size=3)
        assert any(s.signal_kind == "todo_cluster" for s in signals)

    def test_no_signal_below_min_size(self, tmp_path):
        py_file = tmp_path / "mod.py"
        py_file.write_text("# TODO: only one\nx = 1\n")
        signals = detect_todo_clusters(str(tmp_path), touches=["mod.py"], min_size=3)
        assert signals == []


# ---------------------------------------------------------------------------
# detect_resurrection_signals integration
# ---------------------------------------------------------------------------


class TestDetectResurrectionSignals:
    def test_returns_list_for_empty_touches(self, tmp_path):
        result = detect_resurrection_signals(str(tmp_path), touches=[], feature_keywords=[])
        assert isinstance(result, list)

    def test_returns_empty_for_empty_touches(self, tmp_path):
        result = detect_resurrection_signals(str(tmp_path), touches=[], feature_keywords=[])
        assert result == []

    def test_runs_todo_scan_on_touch_set(self, tmp_path):
        py_file = tmp_path / "a.py"
        py_file.write_text("# TODO: x\n# TODO: y\n# TODO: z\n")
        signals = detect_resurrection_signals(
            str(tmp_path),
            touches=["a.py"],
            feature_keywords=[],
            todo_cluster_min_size=3,
        )
        kinds = {s.signal_kind for s in signals}
        assert "todo_cluster" in kinds


# ---------------------------------------------------------------------------
# write_resurrection_report
# ---------------------------------------------------------------------------


class TestWriteResurrectionReport:
    def test_creates_markdown_file(self, tmp_path):
        signals = [
            ResurrectionSignal(
                signal_kind="stale_pr",
                evidence=["https://github.com/org/repo/pull/1"],
                staleness_days=90,
                recommended_action="resume_pr",
            )
        ]
        path = write_resurrection_report(
            feature_id="test-feat-123",
            signals=signals,
            bob_root=str(tmp_path / ".bob"),
        )
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "stale_pr" in content
        assert "resume_pr" in content

    def test_empty_signals_still_creates_file(self, tmp_path):
        path = write_resurrection_report(
            feature_id="empty-feat",
            signals=[],
            bob_root=str(tmp_path / ".bob"),
        )
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "0" in content  # Signals detected: 0
