"""Tests for resolve_target returning 'in_workspace'."""
from __future__ import annotations

from pathlib import Path

import pytest

from bob.spec_quality.integration_reachability import resolve_target


def test_stdlib_module_is_in_workspace():
    assert resolve_target("os") == "in_workspace"


def test_pathlib_is_in_workspace():
    assert resolve_target("pathlib") == "in_workspace"


def test_sys_is_in_workspace():
    assert resolve_target("sys") == "in_workspace"


def test_file_in_src_is_in_workspace(tmp_path):
    (tmp_path / "src" / "myapp" / "utils").mkdir(parents=True)
    (tmp_path / "src" / "myapp" / "utils" / "helpers.py").write_text("# helper")
    assert resolve_target("myapp.utils.helpers", workspace=tmp_path) == "in_workspace"


def test_package_init_is_in_workspace(tmp_path):
    pkg = tmp_path / "src" / "mypkg" / "sub"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    assert resolve_target("mypkg.sub", workspace=tmp_path) == "in_workspace"


def test_root_level_module_is_in_workspace(tmp_path):
    (tmp_path / "mymodule.py").write_text("")
    assert resolve_target("mymodule", workspace=tmp_path) == "in_workspace"
