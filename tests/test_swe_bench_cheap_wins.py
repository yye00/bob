"""Tests for the SWE-Bench cheap-wins façade (F-R7-609).

Exercises the three AC-named entry points on :mod:`bob.swe_bench_cheap_wins`:
  build_repo_tree, select_edit_mode, mutation_pass_check — plus the
  bob.dispatch integration surface.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import bob.dispatch as dispatch
from bob.swe_bench_cheap_wins import (
    EditModeDecision,
    build_repo_tree,
    mutation_pass_check,
    select_edit_mode,
)


# ── AC surface exists on the façade ────────────────────────────────────────────


def test_facade_reexports_are_dispatch_objects():
    assert build_repo_tree is dispatch.build_repo_tree
    assert select_edit_mode is dispatch.select_edit_mode
    assert mutation_pass_check is dispatch.mutation_pass_check


# ── (A) build_repo_tree ────────────────────────────────────────────────────────


class TestBuildRepoTree:
    def test_returns_string(self, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_lists_a_file(self, tmp_path):
        (tmp_path / "unique_name.py").write_text("")
        result = build_repo_tree(tmp_path)
        assert "unique_name.py" in result

    def test_caps_at_max_lines_and_marks_truncation(self, tmp_path):
        for i in range(50):
            (tmp_path / f"f{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=5)
        assert "more" in result
        # Capped: 5 content lines + the "… (N more)" trailer.
        assert len(result.splitlines()) <= 6


# ── (C) select_edit_mode ───────────────────────────────────────────────────────


class TestSelectEditMode:
    def test_small_edit_is_replace(self):
        d = select_edit_mode(1, 5)
        assert isinstance(d, EditModeDecision)
        assert d.mode == "replace"

    def test_many_sites_is_rewrite(self):
        d = select_edit_mode(4, 5)
        assert d.mode == "rewrite"

    def test_large_span_is_rewrite(self):
        d = select_edit_mode(1, 41)
        assert d.mode == "rewrite"

    def test_records_sites_and_span(self):
        d = select_edit_mode(2, 20)
        assert d.sites == 2
        assert d.span == 20


# ── (D) mutation_pass_check ────────────────────────────────────────────────────


class TestMutationPassCheck:
    def test_still_passing_means_weak_test(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = mutation_pass_check(["pytest", "t.py"], tmp_path, "feat-1")
        assert result is True

    def test_failing_after_mutation_means_strong_test(self, tmp_path):
        with patch("bob.dispatch.subprocess.run") as mock:
            mock.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = mutation_pass_check(["pytest", "t.py"], tmp_path, "feat-1")
        assert result is False

    def test_empty_command_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            mutation_pass_check([], tmp_path, "feat-1")

    def test_blank_feature_id_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            mutation_pass_check(["pytest"], tmp_path, "   ")


# ── integration: bob.dispatch ──────────────────────────────────────────────────


def test_integration_bob_dispatch_importable():
    import bob.dispatch  # noqa: F401

    assert hasattr(bob.dispatch, "apply_cheap_wins")
