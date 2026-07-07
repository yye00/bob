"""Slopsquatting first-party allowlist — tools/ and project-root .py modules.

Verifies that ``bob.security_checks._read_first_party_packages`` (and the public
wrapper ``slopsquatting_first_party_allowlist_must_include_tools``) allowlist
project-internal scripts under ``tools/`` and project-root ``*.py`` files, so the
slopsquatting PyPI probe never hard-fails on local-only imports.

Regression target: feature b20b4725 NH'd on
``import spec_quality_score`` because ``tools/spec_quality_score.py`` was not in
the first-party allowlist.
"""

from __future__ import annotations

from pathlib import Path

from bob.security_checks import _read_first_party_packages
from bob.slopsquatting_first_party_allowlist_must_include_tools import (
    slopsquatting_first_party_allowlist_must_include_tools,
)


def _make_workspace(tmp_path: Path) -> Path:
    (tmp_path / "src" / "mypkg").mkdir(parents=True)
    (tmp_path / "src" / "mypkg" / "__init__.py").write_text("")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# spec_quality_score\n")
    (tools / "foo.py").write_text("# foo\n")
    (tmp_path / "rootscript.py").write_text("# root\n")
    return tmp_path


def test_read_first_party_includes_tools_module(tmp_path: Path) -> None:
    """The triggering case: tools/spec_quality_score.py is first-party."""
    ws = _make_workspace(tmp_path)
    result = _read_first_party_packages(ws)
    assert "spec_quality_score" in result


def test_read_first_party_includes_tools_foo(tmp_path: Path) -> None:
    """tools/foo.py is a first-party script."""
    ws = _make_workspace(tmp_path)
    assert "foo" in _read_first_party_packages(ws)


def test_read_first_party_includes_root_module(tmp_path: Path) -> None:
    """Project-root .py files are first-party (importable via pythonpath)."""
    ws = _make_workspace(tmp_path)
    assert "rootscript" in _read_first_party_packages(ws)


def test_read_first_party_includes_src_package(tmp_path: Path) -> None:
    """src/ packages remain in the allowlist (no regression)."""
    ws = _make_workspace(tmp_path)
    assert "mypkg" in _read_first_party_packages(ws)


def test_read_first_party_returns_set(tmp_path: Path) -> None:
    """Return type is a set of import names."""
    result = _read_first_party_packages(_make_workspace(tmp_path))
    assert isinstance(result, set)
    assert all(isinstance(x, str) for x in result)


def test_read_first_party_no_src_still_walks_tools(tmp_path: Path) -> None:
    """A workspace with only tools/ (no src/) still allowlists tools scripts."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "spec_quality_score.py").write_text("# s\n")
    result = _read_first_party_packages(tmp_path)
    assert "spec_quality_score" in result


def test_wrapper_matches_core_for_tools(tmp_path: Path) -> None:
    """The public wrapper includes the same tools/root modules as the core walk."""
    ws = _make_workspace(tmp_path)
    wrapper = slopsquatting_first_party_allowlist_must_include_tools(ws)
    for name in ("spec_quality_score", "foo", "rootscript", "mypkg"):
        assert name in wrapper


def test_init_excluded(tmp_path: Path) -> None:
    """__init__ is never an allowlisted import name."""
    ws = _make_workspace(tmp_path)
    assert "__init__" not in _read_first_party_packages(ws)
