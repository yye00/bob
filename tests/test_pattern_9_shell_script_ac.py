"""Tests for Pattern 9 — shell-script integration AC handler via bob3.ac_handler.

Verifies demote_shell_script_integration_ac:
- Existing executable .sh → PASS-with-warning (True, '')
- Missing script → hard FAIL (False, reason)
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.ac_handler import demote_shell_script_integration_ac


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_shell_script_ac_pass_with_warning_when_exists_and_executable(
    tmp_path: pathlib.Path,
) -> None:
    """Pattern 9 PASS: existing executable .sh → (True, '') PASS-with-warning."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = demote_shell_script_integration_ac(criterion, tmp_path)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_shell_script_ac_fail_when_file_missing(tmp_path: pathlib.Path) -> None:
    """Pattern 9 FAIL: missing script → (False, non-empty reason)."""
    criterion = "integration: tools/missing_script.sh"
    result = demote_shell_script_integration_ac(criterion, tmp_path)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is False
    assert reason  # non-empty failure reason
