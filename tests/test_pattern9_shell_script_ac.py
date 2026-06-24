"""Tests for bob77.verifier.pattern9_shell_script_handler (F-R7-594).

Verifies the Pattern 9 handler exposed via bob77.verifier:
- Existing executable .sh → PASS-with-warning (True, '')
- Missing script → hard FAIL (False, non-empty reason)
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob77.verifier import pattern9_shell_script_handler


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_shell_script_ac_pass_with_warning(tmp_path: pathlib.Path) -> None:
    """Pattern 9 PASS: existing executable .sh → (True, '') PASS-with-warning."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = pattern9_shell_script_handler(criterion, tmp_path)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_missing_script_fails(tmp_path: pathlib.Path) -> None:
    """Pattern 9 FAIL: missing script → (False, non-empty reason)."""
    criterion = "integration: tools/missing_script.sh"
    result = pattern9_shell_script_handler(criterion, tmp_path)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is False
    assert reason  # non-empty failure reason
