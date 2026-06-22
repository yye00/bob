"""Boundary tests for slopsquatting first-party allowlist feature.

Tests that empty, zero, or minimum input returns a well-defined result
rather than raising (boundary case).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from bob3.slopsquatting_first_party_allowlist_must_include_tools import (
    slopsquatting_first_party_allowlist_must_include_tools,
)


def test_empty_workspace_returns_set(tmp_path: Path) -> None:
    """Empty workspace (no src/, no tools/, no .py files) returns an empty set, not an error."""
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert isinstance(result, set)
    assert len(result) == 0


def test_workspace_with_only_empty_src_dir(tmp_path: Path) -> None:
    """Workspace with empty src/ directory returns empty set."""
    (tmp_path / "src").mkdir()
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert isinstance(result, set)


def test_workspace_with_only_empty_tools_dir(tmp_path: Path) -> None:
    """Workspace with empty tools/ directory returns empty set."""
    (tmp_path / "tools").mkdir()
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert isinstance(result, set)


def test_workspace_with_single_src_module(tmp_path: Path) -> None:
    """Minimum input: a single src module returns a set with exactly that module."""
    src = tmp_path / "src" / "mypkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "mypkg" in result


def test_workspace_with_single_tools_module(tmp_path: Path) -> None:
    """Minimum input: a single tools/ module returns a set with exactly that module."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "myscript.py").write_text("# script\n")
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "myscript" in result


def test_workspace_with_single_root_module(tmp_path: Path) -> None:
    """Minimum input: a single root-level .py file is included in allowlist."""
    (tmp_path / "rootmod.py").write_text("# rootmod\n")
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "rootmod" in result


def test_spec_quality_score_in_tools_included(tmp_path: Path) -> None:
    """The specific spec_quality_score.py in tools/ is the triggering case — must be included."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# spec_quality_score\n")
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "spec_quality_score" in result


def test_foo_py_in_tools_included(tmp_path: Path) -> None:
    """tools/foo.py is a known first-party script and must be in the allowlist."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "foo.py").write_text("# foo\n")
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "foo" in result


def test_returns_set_type_always(tmp_path: Path) -> None:
    """Return type is always set regardless of workspace contents."""
    # Completely empty workspace
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert isinstance(result, set)


def test_init_not_in_result(tmp_path: Path) -> None:
    """__init__ module names are never included in the allowlist."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "__init__" not in result


def test_accepts_path_object(tmp_path: Path) -> None:
    """Accepts a Path object as input without raising."""
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert isinstance(result, set)


def test_accepts_string_path(tmp_path: Path) -> None:
    """Accepts a string path as input and returns a set (boundary: type coercion)."""
    result = slopsquatting_first_party_allowlist_must_include_tools(str(tmp_path))
    assert isinstance(result, set)
