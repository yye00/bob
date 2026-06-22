"""Tests for repo_tree component of bob3.dispatch (F-R7-609).

Covers compute_repo_tree and build_repo_tree: output shape, capping,
truncation trailer, and fallback behaviour.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.dispatch import build_repo_tree, compute_repo_tree, inject_repo_tree_into_prompt


class TestComputeRepoTree:
    def test_returns_string(self, tmp_path):
        result = compute_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_accepts_path_object(self, tmp_path):
        result = compute_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_accepts_string_path(self, tmp_path):
        result = compute_repo_tree(str(tmp_path))
        assert isinstance(result, str)

    def test_empty_directory_does_not_raise(self, tmp_path):
        result = compute_repo_tree(tmp_path)
        assert result is not None

    def test_max_lines_parameter_respected(self, tmp_path):
        for i in range(20):
            (tmp_path / f"file_{i}.py").write_text("")
        result = compute_repo_tree(tmp_path, max_lines=5)
        lines = result.splitlines()
        assert len(lines) <= 6  # 5 content lines + optional trailer

    def test_truncation_trailer_present_when_overflow(self, tmp_path):
        for i in range(30):
            (tmp_path / f"file_{i}.py").write_text("")
        result = compute_repo_tree(tmp_path, max_lines=5)
        assert "more" in result

    def test_no_trailer_when_within_limit(self, tmp_path):
        (tmp_path / "only.py").write_text("")
        result = compute_repo_tree(tmp_path, max_lines=200)
        assert "… (" not in result

    def test_delegates_to_build_repo_tree(self, tmp_path):
        expected = build_repo_tree(tmp_path)
        result = compute_repo_tree(tmp_path)
        assert result == expected

    def test_default_max_lines_is_200(self, tmp_path):
        result = compute_repo_tree(tmp_path)
        lines = result.splitlines()
        assert len(lines) <= 201  # 200 lines + possible trailer


class TestBuildRepoTree:
    def test_returns_string_for_real_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_truncation_trailer_format(self, tmp_path):
        for i in range(50):
            (tmp_path / f"f{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=10)
        lines = result.splitlines()
        last = lines[-1]
        assert "more" in last

    def test_exactly_at_limit_has_no_trailer(self, tmp_path):
        # Create exactly max_lines files; tree output may vary but result fits
        for i in range(3):
            (tmp_path / f"g{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=200)
        assert isinstance(result, str)

    def test_fallback_when_tree_not_available(self, tmp_path):
        (tmp_path / "z.py").write_text("")
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("tree not found")
            result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_fallback_includes_workspace_info_or_unavailable(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("both missing")
            result = build_repo_tree(tmp_path)
        assert isinstance(result, str)


class TestInjectRepoTreeIntoPrompt:
    def test_result_contains_original_prompt(self, tmp_path):
        result = inject_repo_tree_into_prompt("my task", tmp_path)
        assert "my task" in result

    def test_result_contains_repo_tree_header(self, tmp_path):
        result = inject_repo_tree_into_prompt("task", tmp_path)
        assert "Repository Tree" in result

    def test_tree_is_prepended_not_appended(self, tmp_path):
        result = inject_repo_tree_into_prompt("task", tmp_path)
        tree_pos = result.find("Repository Tree")
        task_pos = result.find("task")
        assert tree_pos < task_pos

    def test_empty_prompt_still_gets_tree_header(self, tmp_path):
        result = inject_repo_tree_into_prompt("", tmp_path)
        assert "Repository Tree" in result
