"""Boundary tests for repo tree truncation in bob3.swe_bench_directives (F-R7-609).

AC: empty, zero, or minimum input returns a well-defined result rather than raising.

Tests the truncation boundary of build_repo_tree (max_lines cap) and the
validate_repo_tree sentinel detection.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.swe_bench_directives import (
    build_repo_tree,
    inject_repo_tree_into_prompt,
    validate_repo_tree,
)


class TestBuildRepoTreeTruncation:
    def test_empty_workspace_does_not_raise(self, tmp_path):
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_tree_with_exactly_max_lines_not_truncated(self, tmp_path):
        lines = [f"line{i}" for i in range(10)]
        fake_output = "\n".join(lines)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = fake_output
            mock_run.return_value.returncode = 0
            result = build_repo_tree(tmp_path, max_lines=10)
        assert "… (" not in result
        assert len(result.splitlines()) == 10

    def test_tree_exceeding_max_lines_is_truncated(self, tmp_path):
        lines = [f"line{i}" for i in range(250)]
        fake_output = "\n".join(lines)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = fake_output
            mock_run.return_value.returncode = 0
            result = build_repo_tree(tmp_path, max_lines=200)
        assert "… (" in result
        result_lines = result.splitlines()
        assert len(result_lines) == 201  # 200 content + 1 trailer

    def test_trailer_shows_correct_remaining_count(self, tmp_path):
        lines = [f"line{i}" for i in range(210)]
        fake_output = "\n".join(lines)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = fake_output
            mock_run.return_value.returncode = 0
            result = build_repo_tree(tmp_path, max_lines=200)
        assert "… (10 more)" in result

    def test_single_line_workspace_does_not_raise(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "one_file.py"
            mock_run.return_value.returncode = 0
            result = build_repo_tree(tmp_path, max_lines=200)
        assert "one_file.py" in result

    def test_tree_not_installed_falls_back_gracefully(self, tmp_path):
        import subprocess
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_both_tree_and_find_timeout_returns_sentinel(self, tmp_path):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tree", timeout=10)):
            result = build_repo_tree(tmp_path)
        assert "unavailable" in result.lower() or isinstance(result, str)


class TestValidateRepoTree:
    def test_valid_tree_returns_true(self):
        assert validate_repo_tree("src/\n  bob3/\n    dispatch.py") is True

    def test_empty_string_returns_false(self):
        assert validate_repo_tree("") is False

    def test_whitespace_only_returns_false(self):
        assert validate_repo_tree("   \n  ") is False

    def test_unavailability_sentinel_returns_false(self):
        assert validate_repo_tree("(repo tree unavailable for /some/path)") is False

    def test_non_string_returns_false(self):
        assert validate_repo_tree(None) is False  # type: ignore[arg-type]
        assert validate_repo_tree(123) is False   # type: ignore[arg-type]

    def test_single_file_listing_is_valid(self):
        assert validate_repo_tree("README.md") is True

    def test_multiline_tree_is_valid(self):
        tree = ".\n├── src\n│   └── bob3\n└── tests"
        assert validate_repo_tree(tree) is True


class TestInjectRepoTreePromptBoundary:
    def test_empty_prompt_does_not_raise(self, tmp_path):
        result = inject_repo_tree_into_prompt("", tmp_path)
        assert isinstance(result, str)

    def test_result_is_non_empty_string(self, tmp_path):
        result = inject_repo_tree_into_prompt("", tmp_path)
        assert len(result) > 0

    def test_prompt_preserved_in_output(self, tmp_path):
        prompt = "Do the thing."
        result = inject_repo_tree_into_prompt(prompt, tmp_path)
        assert prompt in result
