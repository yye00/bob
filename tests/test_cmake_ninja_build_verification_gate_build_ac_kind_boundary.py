"""Boundary tests for bob.build_verification (feature f3523d60).

Empty, zero, or minimum input must return a well-defined result rather than
raising.

AC: pytest: tests/test_cmake_ninja_build_verification_gate_build_ac_kind_boundary.py
"""

from __future__ import annotations

import pathlib

import pytest

import bob.build_verification as bv
from bob.build_verification import BuildResult, is_cmake_project, run_build_criterion


def test_empty_expression_returns_result(tmp_path, monkeypatch):
    """Empty expression on a CMake ws must return a BuildResult, not raise."""
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
    monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
    monkeypatch.setattr(
        bv, "_run_with_pgroup_timeout", lambda *a, **k: ("", "", 0, False)
    )
    res = run_build_criterion(tmp_path, "", kind="build")
    assert isinstance(res, BuildResult)
    assert res.passed is True


def test_missing_workspace_returns_fail(tmp_path):
    """A non-existent workspace must degrade to a fail result, not raise."""
    ghost = tmp_path / "does_not_exist"
    res = run_build_criterion(ghost, "", kind="build")
    assert isinstance(res, BuildResult)
    assert res.passed is False
    assert "workspace" in res.details.lower()


def test_no_compiler_available_returns_fail(tmp_path, monkeypatch):
    """When no toolchain is installed we return a well-defined fail."""
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
    monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: None)
    res = run_build_criterion(tmp_path, "", kind="build")
    assert res.passed is False
    assert isinstance(res.details, str) and res.details


def test_whitespace_expression(tmp_path, monkeypatch):
    """A whitespace-only expression must not raise."""
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
    monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
    monkeypatch.setattr(
        bv, "_run_with_pgroup_timeout", lambda *a, **k: ("", "", 0, False)
    )
    res = run_build_criterion(tmp_path, "   ", kind="build")
    assert isinstance(res, BuildResult)


def test_is_cmake_project_empty_dir(tmp_path):
    """is_cmake_project on an empty dir returns False, not raise."""
    assert is_cmake_project(tmp_path) is False


def test_minimum_compile_no_source(tmp_path, monkeypatch):
    """compile: with no source token returns a defined fail, not raise."""
    (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)\n")
    monkeypatch.setattr(bv, "resolve_cxx_compiler", lambda *a, **k: "hipcc")
    res = run_build_criterion(tmp_path, "", kind="compile")
    assert res.passed is False
    assert "source" in res.details.lower()
