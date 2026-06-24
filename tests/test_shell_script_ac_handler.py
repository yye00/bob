"""Tests for bob.verifier.shell_script_ac_handler.handle_shell_script_ac (F-R7-594).

Verifies Pattern 9 — shell-script integration AC handler:
- Existing executable .sh → PASS-with-warning (True, '')
- Missing script → hard FAIL (False, reason)
- Non-executable script → hard FAIL (False, reason)
- Non-shell-script integration AC → None (fall through)
- Non-integration AC → None (fall through)
"""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from bob.verifier.shell_script_ac_handler import handle_shell_script_ac


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return p


def test_existing_executable_sh_returns_pass(tmp_path: pathlib.Path) -> None:
    """Pattern 9 PASS: existing executable .sh → (True, '') PASS-with-warning."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = handle_shell_script_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_existing_executable_bash_returns_pass(tmp_path: pathlib.Path) -> None:
    """Pattern 9 PASS: existing executable .bash → (True, '') PASS-with-warning."""
    _make_script(tmp_path, "tools/self_heal.bash", executable=True)
    criterion = "integration: tools/self_heal.bash"
    result = handle_shell_script_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_missing_script_returns_fail(tmp_path: pathlib.Path) -> None:
    """Pattern 9 FAIL: missing script → (False, non-empty reason)."""
    criterion = "integration: tools/missing_script.sh"
    result = handle_shell_script_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_non_executable_script_returns_fail(tmp_path: pathlib.Path) -> None:
    """Pattern 9 FAIL: script exists but not executable → (False, non-empty reason)."""
    _make_script(tmp_path, "tools/setup.sh", executable=False)
    criterion = "integration: tools/setup.sh"
    result = handle_shell_script_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_non_shell_integration_ac_returns_none(tmp_path: pathlib.Path) -> None:
    """Non-shell-script integration AC → None (fall through to next pattern)."""
    result = handle_shell_script_ac("integration: bob.verifier", tmp_path)
    assert result is None


def test_non_integration_ac_returns_none(tmp_path: pathlib.Path) -> None:
    """Non-integration AC → None (not handled by Pattern 9)."""
    result = handle_shell_script_ac("pytest: tests/test_foo.py::test_bar", tmp_path)
    assert result is None


def test_self_heal_script_pattern(tmp_path: pathlib.Path) -> None:
    """Regression: tools/self_heal.sh (the specific AC that caused NH)."""
    _make_script(tmp_path, "tools/self_heal.sh", executable=True)
    criterion = "integration: tools/self_heal.sh"
    result = handle_shell_script_ac(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""
