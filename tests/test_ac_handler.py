"""Tests for bob.ac_handler — Pattern 9 handle_integration_ac (F-R7-594)."""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob.ac_handler import (
    demote_shell_script_integration,
    demote_shell_script_integration_ac,
    handle_integration_ac,
)


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    mode = p.stat().st_mode
    if executable:
        p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        p.chmod(mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return p


# ── handle_integration_ac ────────────────────────────────────────────────────


def test_handle_integration_ac_pass_existing_executable(tmp_path: pathlib.Path) -> None:
    """Existing executable .sh → (True, '') — AC demoted to PASS."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh")
    result = handle_integration_ac("integration: tools/spawn_next_generation.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_handle_integration_ac_fail_missing_script(tmp_path: pathlib.Path) -> None:
    """Missing script → (False, reason) — real bug surfaces correctly."""
    result = handle_integration_ac("integration: tools/missing.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_handle_integration_ac_fail_non_executable(tmp_path: pathlib.Path) -> None:
    """Non-executable script → (False, reason) — safety invariant enforced."""
    _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    result = handle_integration_ac("integration: tools/self_heal.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_handle_integration_ac_returns_none_for_non_integration(tmp_path: pathlib.Path) -> None:
    """Non-integration criterion → None; caller continues to next pattern."""
    result = handle_integration_ac("pytest: tests/test_foo.py::test_bar", tmp_path)
    assert result is None


def test_handle_integration_ac_returns_none_for_python_module(tmp_path: pathlib.Path) -> None:
    """integration: with dotted Python path → None (not a shell script)."""
    result = handle_integration_ac("integration: bob.verifier", tmp_path)
    assert result is None


def test_handle_integration_ac_recognises_bash_extension(tmp_path: pathlib.Path) -> None:
    """.bash extension is also recognised as a shell script."""
    _make_script(tmp_path, "tools/setup.bash")
    result = handle_integration_ac("integration: tools/setup.bash", tmp_path)
    assert result is not None
    passed, _ = result
    assert passed is True


# ── aliases ───────────────────────────────────────────────────────────────────


def test_demote_shell_script_integration_is_alias(tmp_path: pathlib.Path) -> None:
    """demote_shell_script_integration delegates to handle_integration_ac."""
    _make_script(tmp_path, "tools/run.sh")
    assert demote_shell_script_integration(
        "integration: tools/run.sh", tmp_path
    ) == handle_integration_ac("integration: tools/run.sh", tmp_path)


def test_demote_shell_script_integration_ac_is_alias(tmp_path: pathlib.Path) -> None:
    """demote_shell_script_integration_ac alias works identically."""
    _make_script(tmp_path, "tools/run.sh")
    result = demote_shell_script_integration_ac("integration: tools/run.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


# ── regression guards ─────────────────────────────────────────────────────────


def test_regression_spawn_next_generation_sh(tmp_path: pathlib.Path) -> None:
    """Regression: 51fc8cb1 integration AC must PASS."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh")
    result = handle_integration_ac("integration: tools/spawn_next_generation.sh", tmp_path)
    assert result is not None
    assert result[0] is True


def test_regression_self_heal_sh(tmp_path: pathlib.Path) -> None:
    """Regression: 949e97e1 integration AC must PASS."""
    _make_script(tmp_path, "tools/self_heal.sh")
    result = handle_integration_ac("integration: tools/self_heal.sh", tmp_path)
    assert result is not None
    assert result[0] is True


# ── AC-required test names (F-R7-594) ────────────────────────────────────────


def test_shell_script_integration_pass_with_warning(tmp_path: pathlib.Path) -> None:
    """integration: AC with existing executable script → PASS with warning (F-R7-594)."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh")
    result = demote_shell_script_integration("integration: tools/spawn_next_generation.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_shell_script_missing_fails(tmp_path: pathlib.Path) -> None:
    """integration: AC with missing script → hard FAIL (real bugs surface)."""
    result = demote_shell_script_integration("integration: tools/missing_script.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_shell_script_not_executable_fails(tmp_path: pathlib.Path) -> None:
    """integration: AC with non-executable script → hard FAIL (safety invariant)."""
    _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    result = demote_shell_script_integration("integration: tools/self_heal.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason
