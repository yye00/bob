"""Tests for Pattern 9 — shell-script integration AC handler (F-R7-594).

Verifies that:
- An 'integration:' AC referencing an existing, executable .sh file is
  demoted to PASS with a warning.
- An 'integration:' AC referencing a missing script returns (False, reason).
- A non-executable script also returns (False, reason).
- Non-shell-script bodies are not handled (return None).
"""

from __future__ import annotations

import os
import pathlib
import stat
import tempfile

import pytest

from bob3.verifier import handle_shell_script_ac
from bob74.verifier import demote_shell_script_integration


@pytest.fixture
def tmp_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_demote_to_pass_when_script_exists_and_executable(tmp_workspace: pathlib.Path) -> None:
    """Pattern 9 PASS: existing executable .sh → (True, '')."""
    _make_script(tmp_workspace, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = handle_shell_script_ac(criterion, tmp_workspace)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_fail_when_script_missing(tmp_workspace: pathlib.Path) -> None:
    """Pattern 9 FAIL: missing script → (False, non-empty reason)."""
    criterion = "integration: tools/missing_script.sh"
    result = handle_shell_script_ac(criterion, tmp_workspace)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is False
    assert "not found" in reason


def test_fail_when_script_not_executable(tmp_workspace: pathlib.Path) -> None:
    """Pattern 9 FAIL: non-executable script → (False, non-empty reason)."""
    p = _make_script(tmp_workspace, "tools/self_heal.sh", executable=False)
    # Explicitly strip execute bits
    p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    criterion = "integration: tools/self_heal.sh"
    result = handle_shell_script_ac(criterion, tmp_workspace)
    assert result is not None, "expected a definitive answer, not None"
    passed, reason = result
    assert passed is False
    assert "not executable" in reason


def test_returns_none_for_non_integration_criterion(tmp_workspace: pathlib.Path) -> None:
    """Non-integration ACs are not handled — returns None."""
    criterion = "pytest: tests/test_something.py::test_foo"
    assert handle_shell_script_ac(criterion, tmp_workspace) is None


def test_returns_none_for_non_shell_integration_body(tmp_workspace: pathlib.Path) -> None:
    """integration: with a dotted Python path — not a shell script, returns None."""
    criterion = "integration: bob3.orchestrator.run_loop"
    assert handle_shell_script_ac(criterion, tmp_workspace) is None


def test_bash_extension_is_recognised(tmp_workspace: pathlib.Path) -> None:
    """Pattern 9 also applies to .bash files."""
    _make_script(tmp_workspace, "tools/setup.bash", executable=True)
    criterion = "integration: tools/setup.bash"
    result = handle_shell_script_ac(criterion, tmp_workspace)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_case_insensitive_integration_prefix(tmp_workspace: pathlib.Path) -> None:
    """'Integration:' (mixed-case) is recognised."""
    _make_script(tmp_workspace, "tools/run.sh", executable=True)
    criterion = "Integration: tools/run.sh"
    result = handle_shell_script_ac(criterion, tmp_workspace)
    assert result is not None
    passed, _ = result
    assert passed is True


# ---------------------------------------------------------------------------
# AC-required test functions (bob74.verifier.demote_shell_script_integration)
# ---------------------------------------------------------------------------


def test_shell_script_ac_pass_with_warning(tmp_workspace: pathlib.Path) -> None:
    """AC: existing executable .sh → demote to PASS-with-warning (F-R7-594)."""
    _make_script(tmp_workspace, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = demote_shell_script_integration(criterion, tmp_workspace)
    assert result is not None, "expected (True, '') not None"
    passed, reason = result
    assert passed is True, f"expected PASS, got FAIL with reason: {reason!r}"
    assert reason == ""


def test_shell_script_ac_fail_missing_file(tmp_workspace: pathlib.Path) -> None:
    """AC: missing script → hard FAIL with non-empty reason."""
    criterion = "integration: tools/missing_script.sh"
    result = demote_shell_script_integration(criterion, tmp_workspace)
    assert result is not None, "expected (False, reason) not None"
    passed, reason = result
    assert passed is False, "expected FAIL for missing script"
    assert reason, "reason must be non-empty"
