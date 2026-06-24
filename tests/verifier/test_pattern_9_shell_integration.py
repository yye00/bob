"""Tests for bob.verifier.pattern_9_shell_integration.demote_shell_script_ac (F-R7-594)."""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from bob.verifier.pattern_9_shell_integration import demote_shell_script_ac


# ---------------------------------------------------------------------------
# Happy-path: existing, executable shell scripts
# ---------------------------------------------------------------------------


def test_executable_sh_script_returns_pass(tmp_path: pathlib.Path) -> None:
    """Existing, executable .sh script → (True, '') — PASS demotion."""
    script = tmp_path / "tools" / "run.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho ok\n")
    script.chmod(0o755)
    result = demote_shell_script_ac("integration: tools/run.sh", tmp_path)
    assert result == (True, "")


def test_executable_bash_script_returns_pass(tmp_path: pathlib.Path) -> None:
    """Existing, executable .bash script → (True, '') — PASS demotion."""
    script = tmp_path / "tools" / "setup.bash"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho setup\n")
    script.chmod(0o755)
    result = demote_shell_script_ac("integration: tools/setup.bash", tmp_path)
    assert result == (True, "")


def test_spawn_next_generation_pattern(tmp_path: pathlib.Path) -> None:
    """Reproduces the exact AC that caused NH: 'integration: tools/spawn_next_generation.sh'."""
    script = tmp_path / "tools" / "spawn_next_generation.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho spawn\n")
    script.chmod(0o755)
    result = demote_shell_script_ac("integration: tools/spawn_next_generation.sh", tmp_path)
    assert result == (True, "")


def test_self_heal_pattern(tmp_path: pathlib.Path) -> None:
    """Reproduces the exact AC that caused NH: 'integration: tools/self_heal.sh'."""
    script = tmp_path / "tools" / "self_heal.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho heal\n")
    script.chmod(0o755)
    result = demote_shell_script_ac("integration: tools/self_heal.sh", tmp_path)
    assert result == (True, "")


# ---------------------------------------------------------------------------
# Safety: missing or non-executable scripts must hard-FAIL
# ---------------------------------------------------------------------------


def test_missing_script_returns_false(tmp_path: pathlib.Path) -> None:
    """Script does not exist → (False, reason) hard FAIL."""
    result = demote_shell_script_ac("integration: tools/missing.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_non_executable_script_returns_false(tmp_path: pathlib.Path) -> None:
    """Script exists but is not executable → (False, reason) hard FAIL."""
    script = tmp_path / "tools" / "locked.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho locked\n")
    script.chmod(script.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    result = demote_shell_script_ac("integration: tools/locked.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


# ---------------------------------------------------------------------------
# Non-shell-script integration ACs → None (fall through)
# ---------------------------------------------------------------------------


def test_python_module_integration_returns_none(tmp_path: pathlib.Path) -> None:
    """'integration: bob.verifier.ac_validator' → None (not a shell script)."""
    result = demote_shell_script_ac("integration: bob.verifier.ac_validator", tmp_path)
    assert result is None


def test_non_integration_prefix_returns_none(tmp_path: pathlib.Path) -> None:
    """'pytest: tests/test_foo.py' → None (not an integration AC)."""
    result = demote_shell_script_ac("pytest: tests/test_foo.py", tmp_path)
    assert result is None


def test_empty_string_returns_none(tmp_path: pathlib.Path) -> None:
    """Empty string → None."""
    result = demote_shell_script_ac("", tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Warning tag emitted (F-R7-594)
# ---------------------------------------------------------------------------


def test_warning_log_emitted_on_demotion(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When demoted to PASS, a WARNING containing 'F-R7-594' must be logged."""
    import logging

    script = tmp_path / "tools" / "run.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho ok\n")
    script.chmod(0o755)
    with caplog.at_level(logging.WARNING):
        demote_shell_script_ac("integration: tools/run.sh", tmp_path)
    assert any("F-R7-594" in r.message for r in caplog.records)
