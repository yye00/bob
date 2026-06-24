"""Tests for bob3.verifier.pattern9_shell_script_handler (F-R7-594).

Pattern 9: when an integration AC body is an existing, executable .sh/.bash file,
demote it to PASS with a WARNING.  Missing or non-executable scripts hard-FAIL.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.verifier import pattern9_shell_script_handler


# ---------------------------------------------------------------------------
# PASS-demotion cases
# ---------------------------------------------------------------------------


def test_pass_when_sh_script_exists_and_executable(tmp_path: pathlib.Path) -> None:
    """Existing, executable .sh file → (True, '')."""
    script = tmp_path / "tools" / "run.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho hi\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    result = pattern9_shell_script_handler("integration: tools/run.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_pass_when_bash_script_exists_and_executable(tmp_path: pathlib.Path) -> None:
    """Existing, executable .bash file → (True, '')."""
    script = tmp_path / "tools" / "setup.bash"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho hi\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    result = pattern9_shell_script_handler("integration: tools/setup.bash", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_pass_for_spawn_next_generation_sh() -> None:
    """tools/spawn_next_generation.sh exists and is executable in real workspace."""
    workspace = pathlib.Path("/home/yelkhamr/dark-factory/bob91")
    result = pattern9_shell_script_handler(
        "integration: tools/spawn_next_generation.sh", workspace
    )
    assert result is not None
    passed, _ = result
    assert passed is True


def test_pass_for_self_heal_sh() -> None:
    """tools/self_heal.sh exists and is executable in real workspace."""
    workspace = pathlib.Path("/home/yelkhamr/dark-factory/bob91")
    result = pattern9_shell_script_handler(
        "integration: tools/self_heal.sh", workspace
    )
    assert result is not None
    passed, _ = result
    assert passed is True


# ---------------------------------------------------------------------------
# FAIL cases (script missing or non-executable)
# ---------------------------------------------------------------------------


def test_fail_when_script_does_not_exist(tmp_path: pathlib.Path) -> None:
    """Missing script → (False, reason)."""
    result = pattern9_shell_script_handler("integration: tools/missing.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_fail_when_script_not_executable(tmp_path: pathlib.Path) -> None:
    """Script exists but not executable → (False, reason)."""
    script = tmp_path / "tools" / "setup.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho hi\n")
    script.chmod(script.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

    result = pattern9_shell_script_handler("integration: tools/setup.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


# ---------------------------------------------------------------------------
# Pass-through cases (not a shell-script integration AC)
# ---------------------------------------------------------------------------


def test_none_returned_for_pytest_ac(tmp_path: pathlib.Path) -> None:
    """pytest: AC → None (not handled by Pattern 9)."""
    result = pattern9_shell_script_handler(
        "pytest: tests/test_foo.py::test_bar", tmp_path
    )
    assert result is None


def test_none_returned_for_python_module_integration(tmp_path: pathlib.Path) -> None:
    """integration: with a dotted Python module path → None."""
    result = pattern9_shell_script_handler("integration: bob3.orchestrator", tmp_path)
    assert result is None


def test_none_returned_for_empty_criterion(tmp_path: pathlib.Path) -> None:
    """Empty string → None."""
    result = pattern9_shell_script_handler("", tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# WARNING log emission
# ---------------------------------------------------------------------------


def test_warning_logged_on_pass_demotion(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    """PASS-demotion must emit a WARNING containing 'F-R7-594'."""
    import logging
    script = tmp_path / "tools" / "run.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/bash\necho hi\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    with caplog.at_level(logging.WARNING):
        pattern9_shell_script_handler("integration: tools/run.sh", tmp_path)

    assert any("F-R7-594" in r.message for r in caplog.records)
