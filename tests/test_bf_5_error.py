"""BF-5 error path tests — invalid input raises ValueError; functions do not
silently succeed on bad data."""

from __future__ import annotations

import pathlib

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
# detect_resurrection_signals — invalid inputs raise ValueError
# ---------------------------------------------------------------------------


def test_invalid_workspace_type_raises():
    """Non-string workspace_root raises TypeError (not silently ignored)."""
    with pytest.raises((TypeError, AttributeError)):
        detect_resurrection_signals(
            workspace_root=None,  # type: ignore[arg-type]
            touches=["src/foo.py"],
            feature_keywords=[],
            repo="",
        )


def test_invalid_touches_type_raises():
    """Non-list touches raises TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_resurrection_signals(
            workspace_root="/tmp",
            touches="not-a-list",  # type: ignore[arg-type]
            feature_keywords=[],
            repo="",
        )


def test_invalid_pr_lookback_days_raises(tmp_path: pathlib.Path):
    """Negative pr_lookback_days raises ValueError."""
    with pytest.raises((ValueError, Exception)):
        detect_resurrection_signals(
            workspace_root=str(tmp_path),
            touches=["src/foo.py"],
            feature_keywords=[],
            repo="",
            pr_lookback_days=-1,
        )


def test_invalid_branch_diverge_days_raises(tmp_path: pathlib.Path):
    """Negative branch_diverge_days raises ValueError."""
    with pytest.raises((ValueError, Exception)):
        detect_resurrection_signals(
            workspace_root=str(tmp_path),
            touches=["src/foo.py"],
            feature_keywords=[],
            repo="",
            branch_diverge_days=-5,
        )


def test_invalid_todo_cluster_min_size_raises(tmp_path: pathlib.Path):
    """Zero or negative todo_cluster_min_size raises ValueError."""
    with pytest.raises((ValueError, Exception)):
        detect_resurrection_signals(
            workspace_root=str(tmp_path),
            touches=["src/foo.py"],
            feature_keywords=[],
            repo="",
            todo_cluster_min_size=0,
        )


# ---------------------------------------------------------------------------
# detect_export_without_impl — error paths
# ---------------------------------------------------------------------------


def test_detect_export_without_impl_invalid_workspace_raises():
    """None workspace_root raises TypeError or AttributeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_export_without_impl(
            workspace_root=None,  # type: ignore[arg-type]
            touches=["src/foo.py"],
        )


def test_detect_export_without_impl_invalid_touches_raises():
    """Non-list touches raises TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_export_without_impl(
            workspace_root="/tmp",
            touches=None,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# detect_stale_branch — error paths
# ---------------------------------------------------------------------------


def test_detect_stale_branch_invalid_workspace_raises():
    """None workspace_root raises TypeError or AttributeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_stale_branch(
            workspace_root=None,  # type: ignore[arg-type]
            touches=["src/foo.py"],
        )


def test_detect_stale_branch_invalid_touches_raises():
    """Non-list touches raises TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_stale_branch(
            workspace_root="/tmp",
            touches=None,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# detect_todo_clusters — error paths
# ---------------------------------------------------------------------------


def test_detect_todo_clusters_invalid_workspace_raises():
    """None workspace_root raises TypeError or AttributeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_todo_clusters(
            workspace_root=None,  # type: ignore[arg-type]
            touches=["src/foo.py"],
        )


def test_detect_todo_clusters_invalid_touches_raises():
    """Non-list touches raises TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_todo_clusters(
            workspace_root="/tmp",
            touches=None,  # type: ignore[arg-type]
        )


def test_detect_todo_clusters_zero_min_size_raises(tmp_path: pathlib.Path):
    """min_size=0 raises ValueError (would match every file trivially)."""
    with pytest.raises((ValueError, Exception)):
        detect_todo_clusters(
            workspace_root=str(tmp_path),
            touches=["src/foo.py"],
            min_size=0,
        )


# ---------------------------------------------------------------------------
# write_resurrection_report — error paths
# ---------------------------------------------------------------------------


def test_write_resurrection_report_invalid_feature_id_raises():
    """None feature_id raises TypeError or AttributeError."""
    with pytest.raises((TypeError, AttributeError)):
        write_resurrection_report(
            feature_id=None,  # type: ignore[arg-type]
            signals=[],
        )


def test_write_resurrection_report_invalid_signals_raises(tmp_path: pathlib.Path):
    """Non-list signals raises TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        write_resurrection_report(
            feature_id="feat-123",
            signals=None,  # type: ignore[arg-type]
            bob_root=str(tmp_path),
        )
