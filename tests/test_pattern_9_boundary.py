"""Boundary tests for Pattern 9 — shell-script integration AC handler (F-R7-594).

Tests that edge/minimum inputs return well-defined results rather than raising.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.ac_handler import demote_shell_script_integration_ac


def test_empty_criterion_returns_none(tmp_path: pathlib.Path) -> None:
    """Empty criterion string → None (not a shell-script integration AC)."""
    result = demote_shell_script_integration_ac("", tmp_path)
    assert result is None


def test_criterion_with_only_integration_prefix_returns_none(tmp_path: pathlib.Path) -> None:
    """'integration:' with no body → None (body is not a .sh path)."""
    result = demote_shell_script_integration_ac("integration:", tmp_path)
    assert result is None


def test_non_integration_criterion_returns_none(tmp_path: pathlib.Path) -> None:
    """Non-integration criterion → None (not handled by Pattern 9)."""
    result = demote_shell_script_integration_ac(
        "pytest: tests/test_foo.py::test_bar", tmp_path
    )
    assert result is None


def test_integration_with_python_module_path_returns_none(tmp_path: pathlib.Path) -> None:
    """integration: with a dotted Python path → None (not a shell script)."""
    result = demote_shell_script_integration_ac("integration: bob3.ac_handler", tmp_path)
    assert result is None


def test_non_executable_script_returns_false(tmp_path: pathlib.Path) -> None:
    """Minimum input that fails safety check: script exists but is not executable → (False, reason)."""
    p = tmp_path / "tools" / "setup.sh"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hi\n")
    # Explicitly strip execute bits
    p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    criterion = "integration: tools/setup.sh"
    result = demote_shell_script_integration_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason
