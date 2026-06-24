"""BF-5 boundary tests — empty, zero, or minimum input returns a well-defined
result rather than raising."""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob.brownfield.resurrection import (
    ResurrectionSignal,
    detect_resurrection_signals,
    detect_export_without_impl,
    detect_stale_branch,
    detect_todo_clusters,
    write_resurrection_report,
)


# ---------------------------------------------------------------------------
# detect_resurrection_signals — boundary inputs
# ---------------------------------------------------------------------------


def test_empty_touches_returns_empty_list(tmp_path: pathlib.Path):
    """Boundary: zero touches → empty list, no exception."""
    result = detect_resurrection_signals(
        workspace_root=str(tmp_path),
        touches=[],
        feature_keywords=[],
        repo="",
    )
    assert result == []


def test_empty_keywords_still_runs(tmp_path: pathlib.Path):
    """Boundary: empty feature_keywords should not raise."""
    (tmp_path / "a.py").write_text("def foo(): pass\n")
    result = detect_resurrection_signals(
        workspace_root=str(tmp_path),
        touches=["a.py"],
        feature_keywords=[],
        repo="",
    )
    assert isinstance(result, list)


def test_nonexistent_touch_path_skipped(tmp_path: pathlib.Path):
    """Boundary: path in touches that doesn't exist → skipped gracefully."""
    result = detect_resurrection_signals(
        workspace_root=str(tmp_path),
        touches=["nonexistent/path/module.py"],
        feature_keywords=["feat"],
        repo="",
    )
    assert isinstance(result, list)


def test_empty_repo_skips_pr_scan(tmp_path: pathlib.Path):
    """Boundary: empty repo string → Signal A (PR scan) is skipped."""
    (tmp_path / "clean.py").write_text("def foo(): pass\n")
    result = detect_resurrection_signals(
        workspace_root=str(tmp_path),
        touches=["clean.py"],
        feature_keywords=["feat"],
        repo="",  # empty → no PR scan attempted
    )
    pr_signals = [s for s in result if s.signal_kind == "stale_pr"]
    assert pr_signals == []


def test_todo_cluster_min_size_one(tmp_path: pathlib.Path):
    """Boundary: min_size=1 fires on a single TODO line."""
    (tmp_path / "one_todo.py").write_text("# TODO: something\ndef fn(): pass\n")
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["one_todo.py"],
        min_size=1,
    )
    assert len(result) >= 1


def test_todo_cluster_min_size_equals_count(tmp_path: pathlib.Path):
    """Boundary: min_size equals exact TODO count → fires."""
    (tmp_path / "two.py").write_text("# TODO: one\n# TODO: two\ndef fn(): pass\n")
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["two.py"],
        min_size=2,
    )
    assert len(result) >= 1


def test_todo_cluster_min_size_one_above_count(tmp_path: pathlib.Path):
    """Boundary: min_size = count+1 → does NOT fire."""
    (tmp_path / "two.py").write_text("# TODO: one\n# TODO: two\ndef fn(): pass\n")
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["two.py"],
        min_size=3,
    )
    assert result == []


def test_export_without_impl_empty_all(tmp_path: pathlib.Path):
    """Boundary: __all__ = [] → no export signals."""
    (tmp_path / "empty_all.py").write_text("__all__ = []\ndef fn(): pass\n")
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["empty_all.py"],
    )
    assert result == []


def test_export_without_impl_single_export_implemented(tmp_path: pathlib.Path):
    """Boundary: single export with real body → no signal."""
    (tmp_path / "one.py").write_text(
        "__all__ = ['fn']\ndef fn():\n    return 1\n"
    )
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["one.py"],
    )
    assert result == []


def test_stale_branch_empty_touches_returns_empty(tmp_path: pathlib.Path):
    """Boundary: empty touches → no branch scan."""
    result = detect_stale_branch(
        workspace_root=str(tmp_path),
        touches=[],
        min_diverge_days=30,
    )
    assert result == []


# ---------------------------------------------------------------------------
# write_resurrection_report — boundary inputs
# ---------------------------------------------------------------------------


def test_write_resurrection_report_empty_signals(tmp_path: pathlib.Path):
    """Boundary: zero signals → file created with 0-signal header."""
    report_path = write_resurrection_report(
        feature_id="empty-signals",
        signals=[],
        bob_root=str(tmp_path),
    )
    p = pathlib.Path(report_path)
    assert p.exists()
    content = p.read_text()
    assert "0" in content  # "Signals detected: 0"


def test_write_resurrection_report_single_signal(tmp_path: pathlib.Path):
    """Boundary: exactly one signal → rendered correctly."""
    signals = [
        ResurrectionSignal(
            signal_kind="stale_pr",
            evidence=["https://github.com/org/repo/pull/1"],
            staleness_days=91,
            recommended_action="resume_pr",
        )
    ]
    report_path = write_resurrection_report(
        feature_id="single-sig",
        signals=signals,
        bob_root=str(tmp_path),
    )
    content = pathlib.Path(report_path).read_text()
    assert "stale_pr" in content
    assert "91" in content
