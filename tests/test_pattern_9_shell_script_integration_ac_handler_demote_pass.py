"""Tests for Pattern 9 — shell-script integration AC handler demote-to-PASS (F-R7-594).

Verifies the canonical entry point
``bob.pattern_9_shell_script_integration_ac_handler_demote_pass``
(function ``pattern_9_shell_script_integration_ac_handler_demote_pass``).
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob.pattern_9_shell_script_integration_ac_handler_demote_pass import (
    pattern_9_shell_script_integration_ac_handler_demote_pass,
)


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_pattern_9_shell_script_integration_ac_handler_demote_pass(
    tmp_path: pathlib.Path,
) -> None:
    """Primary AC test: existing executable .sh → (True, ''), PASS-with-warning."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    criterion = "integration: tools/spawn_next_generation.sh"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is not None, "expected definitive answer, not None"
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_pattern_9_fail_missing_script(tmp_path: pathlib.Path) -> None:
    """Missing script → (False, non-empty reason) — real bug still surfaces."""
    criterion = "integration: tools/missing_script.sh"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason  # non-empty failure reason


def test_pattern_9_fail_non_executable_script(tmp_path: pathlib.Path) -> None:
    """Non-executable script → (False, reason) — safety invariant enforced."""
    p = _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    criterion = "integration: tools/self_heal.sh"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_pattern_9_returns_none_for_non_integration_criterion(tmp_path: pathlib.Path) -> None:
    """Non-integration ACs are not handled — returns None, caller continues."""
    criterion = "pytest: tests/test_something.py::test_foo"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is None


def test_pattern_9_returns_none_for_non_shell_body(tmp_path: pathlib.Path) -> None:
    """integration: with a Python path is not a shell script — returns None."""
    criterion = "integration: bob.orchestrator.run_loop"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is None


def test_pattern_9_recognises_bash_extension(tmp_path: pathlib.Path) -> None:
    """.bash extension is also recognised as a shell script."""
    _make_script(tmp_path, "tools/setup.bash", executable=True)
    criterion = "integration: tools/setup.bash"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_pattern_9_case_insensitive_prefix(tmp_path: pathlib.Path) -> None:
    """'Integration:' (mixed-case) is treated identically to 'integration:'."""
    _make_script(tmp_path, "tools/run.sh", executable=True)
    criterion = "Integration: tools/run.sh"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_pattern_9_self_heal_sh_existing_executable(tmp_path: pathlib.Path) -> None:
    """Regression guard: tools/self_heal.sh existing and executable → PASS (F-R7-594)."""
    _make_script(tmp_path, "tools/self_heal.sh", executable=True)
    criterion = "integration: tools/self_heal.sh"
    result = pattern_9_shell_script_integration_ac_handler_demote_pass(criterion, tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""
