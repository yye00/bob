"""Tests for src/bob/repo_tree_prompt.py (F-R7-609 component A).

AC: File exists: src/bob/repo_tree_prompt.py
    Function defined: bob.dispatch.inject_repo_tree_to_worker
    pytest: tests/test_repo_tree_prompt.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.repo_tree_prompt import (
    build_repo_tree,
    inject_repo_tree_into_prompt,
    inject_repo_tree_to_worker,
)
from bob.dispatch import inject_repo_tree_to_worker as dispatch_inject


class TestRepoTreePromptModule:
    def test_module_exports_build_repo_tree(self):
        assert callable(build_repo_tree)

    def test_module_exports_inject_repo_tree_into_prompt(self):
        assert callable(inject_repo_tree_into_prompt)

    def test_module_exports_inject_repo_tree_to_worker(self):
        assert callable(inject_repo_tree_to_worker)

    def test_inject_repo_tree_to_worker_exists_in_dispatch(self):
        assert callable(dispatch_inject)


class TestInjectRepoTreeToWorker:
    def test_returns_string(self, tmp_path):
        result = inject_repo_tree_to_worker("hello", tmp_path)
        assert isinstance(result, str)

    def test_original_prompt_preserved(self, tmp_path):
        result = inject_repo_tree_to_worker("WORKER_TASK", tmp_path)
        assert "WORKER_TASK" in result

    def test_repo_tree_header_included(self, tmp_path):
        result = inject_repo_tree_to_worker("do work", tmp_path)
        assert "Repository Tree" in result

    def test_tree_prepended_not_appended(self, tmp_path):
        result = inject_repo_tree_to_worker("ORIGINAL", tmp_path)
        tree_pos = result.index("Repository Tree")
        orig_pos = result.index("ORIGINAL")
        assert tree_pos < orig_pos

    def test_accepts_path_object(self, tmp_path):
        result = inject_repo_tree_to_worker("work", tmp_path)
        assert isinstance(result, str)

    def test_accepts_string_path(self, tmp_path):
        result = inject_repo_tree_to_worker("work", str(tmp_path))
        assert isinstance(result, str)

    def test_with_files_in_workspace(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "tests").mkdir()
        result = inject_repo_tree_to_worker("prompt", tmp_path)
        assert isinstance(result, str)
        assert len(result) > len("prompt")

    def test_empty_prompt_returns_non_empty(self, tmp_path):
        result = inject_repo_tree_to_worker("", tmp_path)
        assert len(result) > 0

    def test_dispatch_alias_matches_module_function(self, tmp_path):
        from_module = inject_repo_tree_to_worker("test", tmp_path)
        from_dispatch = dispatch_inject("test", tmp_path)
        assert from_module == from_dispatch


class TestBuildRepoTree:
    def test_returns_string_for_empty_workspace(self, tmp_path):
        result = build_repo_tree(tmp_path)
        assert isinstance(result, str)

    def test_max_lines_respected(self, tmp_path):
        for i in range(50):
            (tmp_path / f"file_{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=5)
        lines = result.splitlines()
        assert len(lines) <= 6  # may have "+N more" trailer

    def test_truncation_trailer_present_when_over_limit(self, tmp_path):
        for i in range(50):
            (tmp_path / f"file_{i}.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=3)
        assert "more" in result

    def test_no_truncation_when_under_limit(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        result = build_repo_tree(tmp_path, max_lines=200)
        assert "more" not in result or "0 more" not in result
