"""Tests boundary condition: is_stale returns False when orchestrator dir has zero source files."""

from __future__ import annotations

import time
import pathlib

import pytest

from bob3.orchestrator.stale_bytecode_guard import is_stale, check_freshness


def test_is_stale_false_when_orchestrator_dir_empty(tmp_path):
    """is_stale returns False when orchestrator dir exists but has zero .py files."""
    orch_dir = tmp_path / "src" / "bob3" / "orchestrator"
    orch_dir.mkdir(parents=True)
    # No .py files — put a non-py file to ensure dir is non-empty but has no .py
    (orch_dir / "README.txt").write_text("docs only")
    start_time = time.time() - 60
    assert is_stale(tmp_path, start_time) is False


def test_check_freshness_empty_when_no_py_files(tmp_path):
    """check_freshness returns [] when orchestrator dir has zero .py files."""
    orch_dir = tmp_path / "src" / "bob3" / "orchestrator"
    orch_dir.mkdir(parents=True)
    start_time = time.time() - 60
    result = check_freshness(tmp_path, start_time)
    assert result == []


def test_check_freshness_empty_when_no_src_dir(tmp_path):
    """check_freshness returns [] when src/ directory doesn't exist."""
    # tmp_path has no src/ subdirectory
    start_time = time.time() - 60
    result = check_freshness(tmp_path, start_time)
    assert result == []


def test_is_stale_false_when_no_src_dir(tmp_path):
    """is_stale returns False when workspace has no src/ directory."""
    start_time = time.time() - 60
    assert is_stale(tmp_path, start_time) is False


def test_check_freshness_empty_when_orchestrator_dir_is_empty(tmp_path):
    """check_freshness returns [] when orchestrator directory exists but is completely empty."""
    orch_dir = tmp_path / "src" / "bob3" / "orchestrator"
    orch_dir.mkdir(parents=True)
    # Completely empty directory
    assert list(orch_dir.iterdir()) == []
    start_time = time.time() - 60
    result = check_freshness(tmp_path, start_time)
    assert result == []


def test_is_stale_false_for_multiple_empty_bob_dirs(tmp_path):
    """is_stale returns False when multiple bob*/orchestrator dirs all have zero .py files."""
    for gen in ("bob3", "bob12", "bob14"):
        d = tmp_path / "src" / gen / "orchestrator"
        d.mkdir(parents=True)
        (d / "notes.md").write_text("docs")
    start_time = time.time() - 60
    assert is_stale(tmp_path, start_time) is False
