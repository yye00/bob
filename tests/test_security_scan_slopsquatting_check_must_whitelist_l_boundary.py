"""Boundary cases for security_scan.whitelist_local_modules.

Tests that minimum / zero / empty inputs return well-defined results
rather than raising.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bob3.security_scan import whitelist_local_modules


class TestBoundaryCases:
    def test_empty_workspace_returns_set(self, tmp_path: Path) -> None:
        """An empty workspace directory returns a set without raising."""
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_workspace_with_only_pyproject(self, tmp_path: Path) -> None:
        """Workspace with only pyproject.toml returns a set without raising."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myproject"\n'
        )
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_workspace_with_empty_src(self, tmp_path: Path) -> None:
        """Workspace with empty src/ returns a set without raising."""
        (tmp_path / "src").mkdir()
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_workspace_with_empty_tools(self, tmp_path: Path) -> None:
        """Workspace with empty tools/ returns a set without raising."""
        (tmp_path / "tools").mkdir()
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_workspace_with_single_module_in_src(self, tmp_path: Path) -> None:
        """Minimum: one module in src returns a non-empty set containing that module."""
        pkg = tmp_path / "src" / "bob3"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "only_module.py").write_text("")
        result = whitelist_local_modules(tmp_path)
        assert "only_module" in result

    def test_workspace_name_itself_included(self, tmp_path: Path) -> None:
        """The workspace name itself appears in the whitelist."""
        result = whitelist_local_modules(tmp_path)
        assert tmp_path.resolve().name in result

    def test_result_is_set_not_list(self, tmp_path: Path) -> None:
        """Return value is always a set, not a list."""
        result = whitelist_local_modules(tmp_path)
        assert type(result) is set

    def test_nonexistent_subdirs_do_not_raise(self, tmp_path: Path) -> None:
        """Calling with a workspace that lacks src/ and tools/ does not raise."""
        result = whitelist_local_modules(tmp_path)
        assert isinstance(result, set)

    def test_single_py_file_at_root(self, tmp_path: Path) -> None:
        """A single .py file at the workspace root is whitelisted."""
        (tmp_path / "lone_module.py").write_text("x = 1\n")
        result = whitelist_local_modules(tmp_path)
        assert "lone_module" in result
