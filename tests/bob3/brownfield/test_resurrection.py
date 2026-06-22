"""Tests for BF-5 — Resurrection gate (Tier-1 partial-work detector).

Covers all four public functions required by acceptance criteria:
  - detect_stale_pr_or_branch
  - detect_export_without_impl
  - detect_todo_clusters
  - write_resurrection_report
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from bob3.brownfield.resurrection import (
    ResurrectionSignal,
    detect_export_without_impl,
    detect_stale_pr_or_branch,
    detect_todo_clusters,
    write_resurrection_report,
)


# ---------------------------------------------------------------------------
# detect_stale_pr_or_branch
# ---------------------------------------------------------------------------


def test_detect_stale_pr_or_branch_empty_touches_no_repo(tmp_path: pathlib.Path):
    """Empty touches + empty repo → empty list, no exception."""
    result = detect_stale_pr_or_branch(
        workspace_root=str(tmp_path),
        touches=[],
        feature_keywords=[],
        repo="",
    )
    assert result == []


def test_detect_stale_pr_or_branch_no_repo_no_git(tmp_path: pathlib.Path):
    """Non-git workspace without repo → returns empty (git silently fails)."""
    (tmp_path / "a.py").write_text("def foo(): pass\n")
    result = detect_stale_pr_or_branch(
        workspace_root=str(tmp_path),
        touches=["a.py"],
        feature_keywords=["feat"],
        repo="",
    )
    assert isinstance(result, list)
    # No stale_pr signals because repo="" skips PR scan
    pr_sigs = [s for s in result if s.signal_kind == "stale_pr"]
    assert pr_sigs == []


def test_detect_stale_pr_or_branch_returns_list(tmp_path: pathlib.Path):
    """Always returns a list regardless of infrastructure availability."""
    result = detect_stale_pr_or_branch(
        workspace_root=str(tmp_path),
        touches=["missing.py"],
        feature_keywords=["something"],
        repo="",
    )
    assert isinstance(result, list)


def test_detect_stale_pr_or_branch_invalid_touches_raises(tmp_path: pathlib.Path):
    """Non-list touches raises TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_stale_pr_or_branch(
            workspace_root=str(tmp_path),
            touches="not-a-list",  # type: ignore[arg-type]
            feature_keywords=[],
        )


def test_detect_stale_pr_or_branch_none_workspace_raises():
    """None workspace_root raises TypeError."""
    with pytest.raises((TypeError, AttributeError)):
        detect_stale_pr_or_branch(
            workspace_root=None,  # type: ignore[arg-type]
            touches=["a.py"],
            feature_keywords=[],
        )


def test_detect_stale_pr_or_branch_negative_lookback_raises(tmp_path: pathlib.Path):
    """Negative pr_lookback_days raises ValueError."""
    with pytest.raises(ValueError):
        detect_stale_pr_or_branch(
            workspace_root=str(tmp_path),
            touches=["a.py"],
            feature_keywords=[],
            pr_lookback_days=-1,
        )


def test_detect_stale_pr_or_branch_negative_diverge_raises(tmp_path: pathlib.Path):
    """Negative branch_diverge_days raises ValueError."""
    with pytest.raises(ValueError):
        detect_stale_pr_or_branch(
            workspace_root=str(tmp_path),
            touches=["a.py"],
            feature_keywords=[],
            branch_diverge_days=-5,
        )


# ---------------------------------------------------------------------------
# detect_export_without_impl
# ---------------------------------------------------------------------------


def test_detect_export_without_impl_no_all(tmp_path: pathlib.Path):
    """File with no __all__ → no signals."""
    (tmp_path / "no_all.py").write_text("def foo(): return 1\n")
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["no_all.py"],
    )
    assert result == []


def test_detect_export_without_impl_stub_detected(tmp_path: pathlib.Path):
    """Exported symbol with `pass` body is flagged as export_without_impl."""
    (tmp_path / "stub.py").write_text(
        textwrap.dedent(
            """\
            __all__ = ['real_fn', 'stub_fn']

            def real_fn():
                return 42

            def stub_fn():
                pass
            """
        )
    )
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["stub.py"],
    )
    signal_names = [ev for sig in result for ev in sig.evidence]
    assert any("stub_fn" in ev for ev in signal_names)


def test_detect_export_without_impl_not_implemented_error(tmp_path: pathlib.Path):
    """Exported symbol raising NotImplementedError is flagged."""
    (tmp_path / "nie.py").write_text(
        textwrap.dedent(
            """\
            __all__ = ['fn']

            def fn():
                raise NotImplementedError
            """
        )
    )
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["nie.py"],
    )
    assert len(result) >= 1
    assert result[0].signal_kind == "export_without_impl"
    assert result[0].recommended_action == "finish_stub"


def test_detect_export_without_impl_all_real(tmp_path: pathlib.Path):
    """All exported symbols with real bodies → no signal."""
    (tmp_path / "real.py").write_text(
        textwrap.dedent(
            """\
            __all__ = ['add', 'sub']

            def add(a, b):
                return a + b

            def sub(a, b):
                return a - b
            """
        )
    )
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["real.py"],
    )
    assert result == []


def test_detect_export_without_impl_missing_symbol(tmp_path: pathlib.Path):
    """Symbol in __all__ with no corresponding def → export_without_impl."""
    (tmp_path / "missing.py").write_text(
        "__all__ = ['ghost']\n"
    )
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["missing.py"],
    )
    assert len(result) >= 1
    assert any("ghost" in ev for sig in result for ev in sig.evidence)


def test_detect_export_without_impl_skips_non_py(tmp_path: pathlib.Path):
    """Non-.py files in touches are silently skipped."""
    (tmp_path / "data.json").write_text('{"key": "value"}')
    result = detect_export_without_impl(
        workspace_root=str(tmp_path),
        touches=["data.json"],
    )
    assert result == []


# ---------------------------------------------------------------------------
# detect_todo_clusters
# ---------------------------------------------------------------------------


def test_detect_todo_clusters_below_min(tmp_path: pathlib.Path):
    """Fewer TODOs than min_size → no signal."""
    (tmp_path / "one.py").write_text("# TODO: do something\ndef fn(): return 1\n")
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["one.py"],
        min_size=3,
    )
    assert result == []


def test_detect_todo_clusters_at_min(tmp_path: pathlib.Path):
    """Exactly min_size TODOs → signal fires."""
    content = "\n".join(f"# TODO: item {i}" for i in range(3)) + "\ndef fn(): pass\n"
    (tmp_path / "three.py").write_text(content)
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["three.py"],
        min_size=3,
    )
    assert len(result) >= 1
    assert result[0].signal_kind == "todo_cluster"
    assert result[0].recommended_action == "finish_stub"


def test_detect_todo_clusters_fixme_counts(tmp_path: pathlib.Path):
    """FIXME comments count toward the cluster threshold."""
    content = "# FIXME: one\n# FIXME: two\n# FIXME: three\ndef fn(): pass\n"
    (tmp_path / "fixme.py").write_text(content)
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["fixme.py"],
        min_size=3,
    )
    assert len(result) >= 1


def test_detect_todo_clusters_evidence_includes_line_refs(tmp_path: pathlib.Path):
    """Evidence list must include per-line references."""
    content = "# TODO: a\n# TODO: b\n# TODO: c\ndef fn(): pass\n"
    (tmp_path / "ev.py").write_text(content)
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["ev.py"],
        min_size=3,
    )
    assert len(result) >= 1
    assert len(result[0].evidence) >= 3


def test_detect_todo_clusters_missing_file_skipped(tmp_path: pathlib.Path):
    """Non-existent path in touches is silently skipped."""
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["does_not_exist.py"],
        min_size=1,
    )
    assert result == []


# ---------------------------------------------------------------------------
# write_resurrection_report
# ---------------------------------------------------------------------------


def test_write_resurrection_report_creates_file(tmp_path: pathlib.Path):
    """Report file is created at the expected path."""
    signals = [
        ResurrectionSignal(
            signal_kind="stale_branch",
            evidence=["refs/heads/old-feature"],
            staleness_days=45,
            recommended_action="rebase_branch",
        )
    ]
    path_str = write_resurrection_report(
        feature_id="feat-abc",
        signals=signals,
        bob3_root=str(tmp_path),
    )
    p = pathlib.Path(path_str)
    assert p.exists()
    assert p.name == "resurrection_report.md"


def test_write_resurrection_report_contains_signal_data(tmp_path: pathlib.Path):
    """Report body includes signal_kind, staleness_days, and recommended_action."""
    signals = [
        ResurrectionSignal(
            signal_kind="todo_cluster",
            evidence=["src/foo.py:line 7", "src/foo.py:line 15"],
            staleness_days=0,
            recommended_action="finish_stub",
        )
    ]
    path_str = write_resurrection_report(
        feature_id="feat-xyz",
        signals=signals,
        bob3_root=str(tmp_path),
    )
    content = pathlib.Path(path_str).read_text()
    assert "todo_cluster" in content
    assert "finish_stub" in content
    assert "src/foo.py" in content


def test_write_resurrection_report_path_structure(tmp_path: pathlib.Path):
    """Report is written under <bob3_root>/features/<feature_id>/."""
    path_str = write_resurrection_report(
        feature_id="my-feature-id",
        signals=[],
        bob3_root=str(tmp_path),
    )
    p = pathlib.Path(path_str)
    assert "my-feature-id" in str(p)
    assert "features" in str(p)


def test_write_resurrection_report_multiple_signals(tmp_path: pathlib.Path):
    """All signals appear in the report."""
    signals = [
        ResurrectionSignal(
            signal_kind="stale_pr",
            evidence=["https://github.com/org/repo/pull/42"],
            staleness_days=100,
            recommended_action="resume_pr",
        ),
        ResurrectionSignal(
            signal_kind="export_without_impl",
            evidence=["src/mod.py:broken_fn (stub body)"],
            staleness_days=0,
            recommended_action="finish_stub",
        ),
    ]
    path_str = write_resurrection_report(
        feature_id="multi-signal-feat",
        signals=signals,
        bob3_root=str(tmp_path),
    )
    content = pathlib.Path(path_str).read_text()
    assert "stale_pr" in content
    assert "export_without_impl" in content
    assert "resume_pr" in content
    assert "finish_stub" in content
