"""Tests for bob3.verifier.check_shell_script_integration (Pattern 9, F-R7-594)."""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.verifier import check_shell_script_integration


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_shell_script_ac_pass_with_warning(tmp_path: pathlib.Path) -> None:
    """Pattern 9 PASS: existing executable .sh → (True, '') with F-R7-594 warning."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = check_shell_script_integration(criterion, tmp_path)
    assert result is not None, "expected (True, '') not None"
    passed, reason = result
    assert passed is True, f"expected PASS, got FAIL with reason: {reason!r}"
    assert reason == ""


def test_shell_script_ac_fail_when_not_executable(tmp_path: pathlib.Path) -> None:
    """Pattern 9 FAIL: non-executable script → (False, non-empty reason)."""
    p = _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    criterion = "integration: tools/self_heal.sh"
    result = check_shell_script_integration(criterion, tmp_path)
    assert result is not None, "expected definitive answer, not None"
    passed, reason = result
    assert passed is False, "expected FAIL for non-executable script"
    assert reason, "reason must be non-empty"


def test_shell_script_ac_fail_when_missing(tmp_path: pathlib.Path) -> None:
    """Pattern 9 FAIL: missing script → (False, non-empty reason)."""
    criterion = "integration: tools/missing_script.sh"
    result = check_shell_script_integration(criterion, tmp_path)
    assert result is not None, "expected definitive answer, not None"
    passed, reason = result
    assert passed is False, "expected FAIL for missing script"
    assert reason, "reason must be non-empty"
