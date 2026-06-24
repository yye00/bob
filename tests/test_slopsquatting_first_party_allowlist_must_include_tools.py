"""Tests for slopsquatting_first_party_allowlist_must_include_tools.

Verifies that the allowlist builder correctly includes modules from:
- src/ tree
- tools/ directory
- project-root .py files

And that edge cases (empty workspace, invalid input) are handled correctly.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from bob.slopsquatting_first_party_allowlist_must_include_tools import (
    slopsquatting_first_party_allowlist_must_include_tools,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Minimal workspace with src/, tools/, and a root-level .py file."""
    # src/bob package
    src_bob = tmp_path / "src" / "bob"
    src_bob.mkdir(parents=True)
    (src_bob / "__init__.py").write_text("")
    (src_bob / "some_module.py").write_text("# module\n")

    # tools/ with spec_quality_score.py
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# spec quality score tool\n")
    (tools / "foo.py").write_text("# foo tool\n")

    # project-root sibling .py
    (tmp_path / "root_script.py").write_text("# root-level script\n")

    return tmp_path


# ---------------------------------------------------------------------------
# Core AC test (the one named in the pytest: AC)
# ---------------------------------------------------------------------------


def test_slopsquatting_first_party_allowlist_must_include_tools(workspace: Path) -> None:
    """All three allowlist sources (src/, tools/, project-root) are present.

    This is the primary AC test; verifies end-to-end that spec_quality_score
    (tools/) and root_script (project-root) are both included, and that
    some_module (src/bob/) is also present.
    """
    result = slopsquatting_first_party_allowlist_must_include_tools(workspace)

    assert isinstance(result, set), "must return a set"
    assert "spec_quality_score" in result, "tools/spec_quality_score.py must be in allowlist"
    assert "foo" in result, "tools/foo.py must be in allowlist"
    assert "some_module" in result, "src/bob/some_module.py must be in allowlist"
    assert "root_script" in result, "project-root root_script.py must be in allowlist"
    assert "__init__" not in result, "__init__ must not appear in allowlist"


# ---------------------------------------------------------------------------
# Boundary / empty-input tests
# ---------------------------------------------------------------------------


def test_empty_workspace_returns_empty_set(tmp_path: Path) -> None:
    """An empty workspace directory (no src/, no tools/) returns an empty set rather than crashing."""
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert isinstance(result, set)
    assert len(result) == 0


def test_workspace_with_no_tools_dir(tmp_path: Path) -> None:
    """Workspace without a tools/ directory still works and returns only src/ entries."""
    src_bob = tmp_path / "src" / "bob"
    src_bob.mkdir(parents=True)
    (src_bob / "__init__.py").write_text("")
    (src_bob / "mymod.py").write_text("# mod\n")

    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "mymod" in result
    assert isinstance(result, set)


def test_workspace_with_no_src_dir(tmp_path: Path) -> None:
    """Workspace without a src/ directory still works and returns only tools/ entries."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "toolscript.py").write_text("# tool\n")

    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "toolscript" in result


def test_tools_package_dir_included(tmp_path: Path) -> None:
    """A package directory under tools/ (with __init__.py) is included."""
    tools = tmp_path / "tools"
    tools.mkdir()
    pkg = tools / "tool_package"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "tool_package" in result


def test_tools_dir_without_init_not_included(tmp_path: Path) -> None:
    """A directory under tools/ without __init__.py is NOT included as a package."""
    tools = tmp_path / "tools"
    tools.mkdir()
    subdir = tools / "not_a_package"
    subdir.mkdir()
    # No __init__.py → not a package

    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "not_a_package" not in result


def test_pyproject_name_included(tmp_path: Path) -> None:
    """pyproject.toml project name is included in the allowlist."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = \"my-cool-project\"\n"
    )
    result = slopsquatting_first_party_allowlist_must_include_tools(tmp_path)
    assert "my_cool_project" in result, "project name with hyphens normalised to underscores"


def test_accepts_string_workspace(tmp_path: Path) -> None:
    """Function accepts a string path in addition to a Path object."""
    result = slopsquatting_first_party_allowlist_must_include_tools(str(tmp_path))
    assert isinstance(result, set)


# ---------------------------------------------------------------------------
# Invalid-input / rejection tests
# ---------------------------------------------------------------------------


def test_raises_on_none_input() -> None:
    """Passing None raises ValueError rather than crashing with AttributeError."""
    with pytest.raises(ValueError, match="None"):
        slopsquatting_first_party_allowlist_must_include_tools(None)  # type: ignore[arg-type]


def test_raises_on_empty_string_input() -> None:
    """Passing an empty string raises ValueError."""
    with pytest.raises(ValueError, match="empty"):
        slopsquatting_first_party_allowlist_must_include_tools("")


def test_raises_on_nonexistent_path(tmp_path: Path) -> None:
    """Passing a path that does not exist raises ValueError."""
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="does not exist"):
        slopsquatting_first_party_allowlist_must_include_tools(missing)


def test_raises_on_file_not_directory(tmp_path: Path) -> None:
    """Passing a file path (not a directory) raises ValueError."""
    f = tmp_path / "notadir.py"
    f.write_text("# file\n")
    with pytest.raises(ValueError, match="directory"):
        slopsquatting_first_party_allowlist_must_include_tools(f)
