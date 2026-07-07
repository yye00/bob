"""Tests for hippy.integration_ac_shell_handler — Pattern 9 (F-R7-594)."""

from __future__ import annotations

import pathlib
import stat

import pytest

from hippy.integration_ac_shell_handler import (
    demote_shell_integration_ac,
    is_executable_shell_script_integration,
)


def _make_script(path: pathlib.Path, *, executable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\necho hi\n")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        path.chmod(path.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def test_executable_shell_script_demotes_to_pass(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "spawn_next_generation.sh", executable=True)
    result = demote_shell_integration_ac(
        "integration: tools/spawn_next_generation.sh", tmp_path
    )
    assert result == (True, "")


def test_bash_extension_also_demotes(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "self_heal.bash", executable=True)
    result = demote_shell_integration_ac(
        "integration: tools/self_heal.bash", tmp_path
    )
    assert result == (True, "")


def test_missing_script_fails(tmp_path: pathlib.Path) -> None:
    result = demote_shell_integration_ac(
        "integration: tools/does_not_exist.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "not found" in reason


def test_non_executable_script_fails(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "setup.sh", executable=False)
    result = demote_shell_integration_ac("integration: tools/setup.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "not executable" in reason


def test_non_shell_integration_returns_none(tmp_path: pathlib.Path) -> None:
    result = demote_shell_integration_ac("integration: bob.ac_handler", tmp_path)
    assert result is None


def test_non_integration_criterion_returns_none(tmp_path: pathlib.Path) -> None:
    result = demote_shell_integration_ac("pytest: tests/test_x.py", tmp_path)
    assert result is None


def test_is_executable_true_for_executable_script(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "run.sh", executable=True)
    assert is_executable_shell_script_integration(
        "integration: tools/run.sh", tmp_path
    ) is True


def test_is_executable_false_for_missing_script(tmp_path: pathlib.Path) -> None:
    assert is_executable_shell_script_integration(
        "integration: tools/absent.sh", tmp_path
    ) is False


def test_none_criterion_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises((TypeError, ValueError)):
        demote_shell_integration_ac(None, tmp_path)  # type: ignore[arg-type]


def test_none_workspace_raises() -> None:
    with pytest.raises((TypeError, ValueError)):
        demote_shell_integration_ac("integration: tools/run.sh", None)  # type: ignore[arg-type]
