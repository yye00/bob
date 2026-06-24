"""Tests for _read_first_party_packages — tools/ and project-root coverage.

AC integration tests:
  - test_tools_dir_included: tools/foo.py → 'foo' in result
  - test_root_sibling_included: bar.py at root → 'bar' in result
  - test_src_packages_still_included: regression guard for F-R7-481
  - test_init_py_excluded_from_stems: __init__.py not added as '__init__'
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bob.security_checks import _read_first_party_packages


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Minimal workspace skeleton."""
    (tmp_path / "src").mkdir()
    return tmp_path


def test_tools_dir_included(workspace: Path) -> None:
    """tools/foo.py must add 'foo' to the first-party set."""
    tools = workspace / "tools"
    tools.mkdir()
    (tools / "foo.py").write_text("# first-party tool\n")

    result = _read_first_party_packages(workspace)

    assert "foo" in result


def test_root_sibling_included(workspace: Path) -> None:
    """bar.py at project root must add 'bar' to the first-party set."""
    (workspace / "bar.py").write_text("# root-level script\n")

    result = _read_first_party_packages(workspace)

    assert "bar" in result


def test_src_packages_still_included(workspace: Path) -> None:
    """Regression guard: src/<pkg>/__init__.py still included (F-R7-481)."""
    pkg = workspace / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")

    result = _read_first_party_packages(workspace)

    assert "mypkg" in result


def test_src_module_stems_still_included(workspace: Path) -> None:
    """Regression guard: src/<pkg>/module.py stems still included (F-R7-481)."""
    pkg = workspace / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "utils.py").write_text("# utility module\n")

    result = _read_first_party_packages(workspace)

    assert "utils" in result


def test_init_py_excluded_from_tools(workspace: Path) -> None:
    """tools/__init__.py must NOT add '__init__' to the set."""
    tools = workspace / "tools"
    tools.mkdir()
    (tools / "__init__.py").write_text("")

    result = _read_first_party_packages(workspace)

    assert "__init__" not in result


def test_init_py_excluded_from_root(workspace: Path) -> None:
    """Root __init__.py must NOT add '__init__' to the set."""
    (workspace / "__init__.py").write_text("")

    result = _read_first_party_packages(workspace)

    assert "__init__" not in result


def test_spec_quality_score_in_tools(workspace: Path) -> None:
    """tools/spec_quality_score.py must add 'spec_quality_score' to the set."""
    tools = workspace / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# spec quality score tool\n")

    result = _read_first_party_packages(workspace)

    assert "spec_quality_score" in result


def test_spec_quality_score_not_in_empty_workspace(workspace: Path) -> None:
    """Without any spec_quality_score.py, 'spec_quality_score' must NOT be in the set."""
    result = _read_first_party_packages(workspace)

    assert "spec_quality_score" not in result


def test_tools_subpackage_included(workspace: Path) -> None:
    """tools/subpkg/__init__.py must add 'subpkg' as a first-party name."""
    tools = workspace / "tools"
    tools.mkdir()
    subpkg = tools / "subpkg"
    subpkg.mkdir()
    (subpkg / "__init__.py").write_text("")

    result = _read_first_party_packages(workspace)

    assert "subpkg" in result


def test_returns_set_of_strings(workspace: Path) -> None:
    """Return type must be a set of strings."""
    result = _read_first_party_packages(workspace)

    assert isinstance(result, set)
    for item in result:
        assert isinstance(item, str)
