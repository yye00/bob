"""Tests for BF-5 Resurrection gate (Tier-1 partial-work detector).

Acceptance criteria:
- File exists: src/bob/brownfield/resurrection.py
- Function defined: bob.brownfield.resurrection.detect_resurrection_signals
- Function defined: bob.brownfield.resurrection.write_resurrection_report
- pytest: tests/test_resurrection.py
- integration: bob.orchestrator
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from bob.brownfield.resurrection import (
    ResurrectionSignal,
    detect_resurrection_signals,
    detect_stale_pr,
    detect_stale_branch,
    detect_export_without_impl,
    detect_todo_clusters,
    write_resurrection_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """A temporary workspace with some Python files."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "module_a.py").write_text(
        textwrap.dedent(
            """\
            __all__ = ['do_thing', 'missing_func']

            def do_thing():
                return 42
            """
        )
    )
    (src / "module_b.py").write_text(
        textwrap.dedent(
            """\
            # TODO: implement this properly
            # FIXME: this is broken
            # TODO: also fix this
            def stub():
                pass
            """
        )
    )
    return tmp_path


# ---------------------------------------------------------------------------
# ResurrectionSignal dataclass
# ---------------------------------------------------------------------------


def test_resurrection_signal_has_required_fields():
    sig = ResurrectionSignal(
        signal_kind="stale_pr",
        evidence=["https://github.com/org/repo/pull/1"],
        staleness_days=95,
        recommended_action="resume_pr",
    )
    assert sig.signal_kind == "stale_pr"
    assert sig.staleness_days == 95
    assert sig.recommended_action == "resume_pr"
    assert len(sig.evidence) == 1


def test_resurrection_signal_recommended_action_values():
    valid_actions = ["resume_pr", "rebase_branch", "finish_stub"]
    for action in valid_actions:
        sig = ResurrectionSignal(
            signal_kind="test",
            evidence=["evidence"],
            staleness_days=10,
            recommended_action=action,
        )
        assert sig.recommended_action == action


# ---------------------------------------------------------------------------
# detect_resurrection_signals — Signal B (export-without-impl)
# ---------------------------------------------------------------------------


def test_signal_b_detects_export_without_impl(tmp_workspace: pathlib.Path):
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_workspace),
        touches=["src/module_a.py"],
        feature_keywords=[],
        repo="",
    )
    signal_b_hits = [s for s in signals if s.signal_kind == "export_without_impl"]
    assert len(signal_b_hits) >= 1
    assert any("missing_func" in e for sig in signal_b_hits for e in sig.evidence)


def test_signal_b_no_false_positive_for_implemented(tmp_workspace: pathlib.Path):
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_workspace),
        touches=["src/module_a.py"],
        feature_keywords=[],
        repo="",
    )
    signal_b_hits = [s for s in signals if s.signal_kind == "export_without_impl"]
    # do_thing IS implemented, must not appear as a false positive
    assert not any("do_thing" in e for sig in signal_b_hits for e in sig.evidence)


def test_signal_b_skips_file_not_in_touches(tmp_workspace: pathlib.Path):
    # module_b.py has TODO clusters but NOT export-without-impl; passing a
    # different path should produce no export_without_impl signals.
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_workspace),
        touches=["src/module_b.py"],
        feature_keywords=[],
        repo="",
    )
    signal_b_hits = [s for s in signals if s.signal_kind == "export_without_impl"]
    assert signal_b_hits == []


# ---------------------------------------------------------------------------
# detect_resurrection_signals — Signal C (TODO clusters)
# ---------------------------------------------------------------------------


def test_signal_c_detects_todo_cluster(tmp_workspace: pathlib.Path):
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_workspace),
        touches=["src/module_b.py"],
        feature_keywords=[],
        repo="",
    )
    signal_c_hits = [s for s in signals if s.signal_kind == "todo_cluster"]
    assert len(signal_c_hits) >= 1


def test_signal_c_below_threshold_produces_no_signal(tmp_workspace: pathlib.Path):
    # module_a.py has no TODO comments
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_workspace),
        touches=["src/module_a.py"],
        feature_keywords=[],
        repo="",
    )
    signal_c_hits = [s for s in signals if s.signal_kind == "todo_cluster"]
    assert signal_c_hits == []


def test_signal_c_respects_custom_threshold(tmp_path: pathlib.Path):
    # File with exactly 2 TODOs — below the default threshold of 3.
    f = tmp_path / "few_todos.py"
    f.write_text("# TODO: one\n# TODO: two\ndef fn(): pass\n")
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_path),
        touches=["few_todos.py"],
        feature_keywords=[],
        repo="",
        todo_cluster_min_size=3,
    )
    signal_c_hits = [s for s in signals if s.signal_kind == "todo_cluster"]
    assert signal_c_hits == []

    # Lower threshold to 2 — now it should fire.
    signals2 = detect_resurrection_signals(
        workspace_root=str(tmp_path),
        touches=["few_todos.py"],
        feature_keywords=[],
        repo="",
        todo_cluster_min_size=2,
    )
    signal_c_hits2 = [s for s in signals2 if s.signal_kind == "todo_cluster"]
    assert len(signal_c_hits2) >= 1


# ---------------------------------------------------------------------------
# detect_resurrection_signals — empty / edge cases
# ---------------------------------------------------------------------------


def test_no_signals_for_clean_file(tmp_path: pathlib.Path):
    f = tmp_path / "clean.py"
    f.write_text("def hello():\n    return 'world'\n")
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_path),
        touches=["clean.py"],
        feature_keywords=[],
        repo="",
    )
    assert signals == []


def test_empty_touches_returns_no_signals(tmp_workspace: pathlib.Path):
    signals = detect_resurrection_signals(
        workspace_root=str(tmp_workspace),
        touches=[],
        feature_keywords=[],
        repo="",
    )
    assert signals == []


def test_returns_list_of_resurrection_signals(tmp_workspace: pathlib.Path):
    result = detect_resurrection_signals(
        workspace_root=str(tmp_workspace),
        touches=["src/module_a.py"],
        feature_keywords=[],
        repo="",
    )
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, ResurrectionSignal)


# ---------------------------------------------------------------------------
# write_resurrection_report
# ---------------------------------------------------------------------------


def test_write_resurrection_report_creates_file(tmp_path: pathlib.Path):
    signals = [
        ResurrectionSignal(
            signal_kind="export_without_impl",
            evidence=["src/foo.py:missing_func"],
            staleness_days=30,
            recommended_action="finish_stub",
        )
    ]
    report_path = write_resurrection_report(
        feature_id="test-feature-123",
        signals=signals,
        bob_root=str(tmp_path),
    )
    assert pathlib.Path(report_path).exists()


def test_write_resurrection_report_path_convention(tmp_path: pathlib.Path):
    signals = [
        ResurrectionSignal(
            signal_kind="todo_cluster",
            evidence=["src/bar.py:line 5"],
            staleness_days=60,
            recommended_action="finish_stub",
        )
    ]
    report_path = write_resurrection_report(
        feature_id="abc-123",
        signals=signals,
        bob_root=str(tmp_path),
    )
    assert "abc-123" in report_path
    assert report_path.endswith("resurrection_report.md")


def test_write_resurrection_report_content_includes_signal_kind(tmp_path: pathlib.Path):
    signals = [
        ResurrectionSignal(
            signal_kind="stale_branch",
            evidence=["refs/heads/wip-old-feature"],
            staleness_days=45,
            recommended_action="rebase_branch",
        )
    ]
    report_path = write_resurrection_report(
        feature_id="feat-xyz",
        signals=signals,
        bob_root=str(tmp_path),
    )
    content = pathlib.Path(report_path).read_text()
    assert "stale_branch" in content
    assert "rebase_branch" in content
    assert "refs/heads/wip-old-feature" in content
    assert "45" in content


def test_write_resurrection_report_multiple_signals(tmp_path: pathlib.Path):
    signals = [
        ResurrectionSignal(
            signal_kind="export_without_impl",
            evidence=["src/mod.py:missing_fn"],
            staleness_days=20,
            recommended_action="finish_stub",
        ),
        ResurrectionSignal(
            signal_kind="todo_cluster",
            evidence=["src/mod.py:line 3"],
            staleness_days=20,
            recommended_action="finish_stub",
        ),
    ]
    report_path = write_resurrection_report(
        feature_id="multi-sig-feat",
        signals=signals,
        bob_root=str(tmp_path),
    )
    content = pathlib.Path(report_path).read_text()
    assert "export_without_impl" in content
    assert "todo_cluster" in content


def test_write_resurrection_report_creates_parent_dirs(tmp_path: pathlib.Path):
    signals = [
        ResurrectionSignal(
            signal_kind="todo_cluster",
            evidence=["x.py:line 1"],
            staleness_days=5,
            recommended_action="finish_stub",
        )
    ]
    # Use a deeply nested bob_root to test mkdir -p behavior
    deep_root = tmp_path / "a" / "b" / "c"
    report_path = write_resurrection_report(
        feature_id="deep-test",
        signals=signals,
        bob_root=str(deep_root),
    )
    assert pathlib.Path(report_path).exists()


# ---------------------------------------------------------------------------
# integration: bob.orchestrator imports from bob.brownfield.resurrection
# ---------------------------------------------------------------------------


def test_orchestrator_imports_resurrection_symbols():
    import bob.orchestrator as orch
    # The orchestrator __init__.py must expose the resurrection functions.
    assert hasattr(orch, "detect_resurrection_signals")
    assert hasattr(orch, "write_resurrection_report")


# ---------------------------------------------------------------------------
# Public named entry points: detect_stale_pr, detect_stale_branch, etc.
# ---------------------------------------------------------------------------


def test_detect_stale_pr_returns_list():
    # gh CLI not available / no creds -- must return empty list, not raise.
    result = detect_stale_pr(repo="org/repo", feature_keywords=["some-feature"])
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, ResurrectionSignal)


def test_detect_stale_branch_returns_list(tmp_path: pathlib.Path):
    # Not a git repo -- must return empty list, not raise.
    result = detect_stale_branch(
        workspace_root=str(tmp_path),
        touches=["src/foo.py"],
        min_diverge_days=30,
    )
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, ResurrectionSignal)


def test_detect_export_without_impl_finds_missing_export(tmp_workspace: pathlib.Path):
    result = detect_export_without_impl(
        workspace_root=str(tmp_workspace),
        touches=["src/module_a.py"],
    )
    assert isinstance(result, list)
    assert any("missing_func" in e for sig in result for e in sig.evidence)


def test_detect_export_without_impl_no_false_positive(tmp_workspace: pathlib.Path):
    result = detect_export_without_impl(
        workspace_root=str(tmp_workspace),
        touches=["src/module_a.py"],
    )
    # do_thing is implemented -- must not appear
    assert not any("do_thing" in e for sig in result for e in sig.evidence)


def test_detect_todo_clusters_fires_on_dense_file(tmp_workspace: pathlib.Path):
    result = detect_todo_clusters(
        workspace_root=str(tmp_workspace),
        touches=["src/module_b.py"],
        min_size=3,
    )
    assert len(result) >= 1
    assert all(s.signal_kind == "todo_cluster" for s in result)


def test_detect_todo_clusters_empty_for_clean_file(tmp_path: pathlib.Path):
    (tmp_path / "clean.py").write_text("def hello():\n    return 'world'\n")
    result = detect_todo_clusters(
        workspace_root=str(tmp_path),
        touches=["clean.py"],
    )
    assert result == []


def test_detect_todo_clusters_respects_min_size(tmp_path: pathlib.Path):
    (tmp_path / "two_todos.py").write_text("# TODO: one\n# TODO: two\ndef fn(): pass\n")
    assert detect_todo_clusters(str(tmp_path), ["two_todos.py"], min_size=3) == []
    assert len(detect_todo_clusters(str(tmp_path), ["two_todos.py"], min_size=2)) >= 1
