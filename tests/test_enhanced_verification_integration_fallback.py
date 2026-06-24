"""Integration tests for F-R7-583: Pattern-8 integration AC prose-function fallback.

Tests that _check_criterion correctly handles prose-integration ACs where
the first token after 'integration:' is a bare function name rather than
a dotted module path.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from bob.enhanced_verification import _check_criterion


@pytest.fixture
def workspace_with_sweep(tmp_path):
    """Workspace containing def sweep_orphan_subagents."""
    src_dir = tmp_path / "src" / "bob"
    src_dir.mkdir(parents=True)
    reaper_file = src_dir / "reaper.py"
    reaper_file.write_text(
        "def sweep_orphan_subagents(workspace, processes):\n"
        "    \"\"\"Sweep orphan subagent processes.\"\"\"\n"
        "    pass\n"
    )
    return tmp_path


@pytest.fixture
def empty_workspace(tmp_path):
    """Workspace with no relevant definitions."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "empty.py").write_text("# nothing here\n")
    return tmp_path


def test_prose_integration_demotes(workspace_with_sweep):
    """AC-6/AC-7 integration test: prose-integration AC passes when function exists."""
    criterion = (
        "integration: sweep_orphan_subagents runs at the same cadence as stuck_executing reaper"
    )
    result = _check_criterion(
        criterion=criterion,
        workspace=workspace_with_sweep,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert result is True, (
        f"Expected _check_criterion to return True for prose-integration AC when "
        f"'def sweep_orphan_subagents' exists in workspace, got {result!r}"
    )


def test_missing_function_still_fails(empty_workspace):
    """AC-6/AC-7 integration test: prose-integration AC fails when function is absent."""
    criterion = "integration: nonexistent_function does something in the system"
    result = _check_criterion(
        criterion=criterion,
        workspace=empty_workspace,
        is_python_project=True,
        is_cmake_project=False,
        is_opm_project=False,
    )
    assert result is False, (
        f"Expected _check_criterion to return False for prose-integration AC when "
        f"'def nonexistent_function' does not exist in workspace, got {result!r}"
    )
