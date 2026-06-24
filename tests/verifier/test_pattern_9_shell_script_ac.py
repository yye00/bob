"""Tests for bob.verifier.pattern_9_shell_script_ac (F-R7-594).

Verifies:
  is_shell_script_integration_ac  — predicate for recognising shell-script integration ACs
  should_demote_to_pass_with_warning — demotion logic (exists + executable → True)
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob.verifier.pattern_9_shell_script_ac import (
    is_shell_script_integration_ac,
    should_demote_to_pass_with_warning,
)


# ---------------------------------------------------------------------------
# is_shell_script_integration_ac
# ---------------------------------------------------------------------------


def test_is_shell_script_integration_ac_true_for_sh() -> None:
    assert is_shell_script_integration_ac("integration: tools/run.sh") is True


def test_is_shell_script_integration_ac_true_for_bash() -> None:
    assert is_shell_script_integration_ac("integration: tools/run.bash") is True


def test_is_shell_script_integration_ac_false_for_python_module() -> None:
    assert is_shell_script_integration_ac("integration: bob.verifier") is False


def test_is_shell_script_integration_ac_false_for_pytest_criterion() -> None:
    assert is_shell_script_integration_ac("pytest: tests/test_foo.py::test_bar") is False


def test_is_shell_script_integration_ac_false_for_empty_string() -> None:
    assert is_shell_script_integration_ac("") is False


def test_is_shell_script_integration_ac_false_for_integration_no_body() -> None:
    assert is_shell_script_integration_ac("integration:") is False


def test_is_shell_script_integration_ac_case_insensitive_prefix() -> None:
    assert is_shell_script_integration_ac("Integration: tools/run.sh") is True


# ---------------------------------------------------------------------------
# should_demote_to_pass_with_warning
# ---------------------------------------------------------------------------


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return p


def test_demote_true_when_script_exists_and_executable(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    assert should_demote_to_pass_with_warning(
        "integration: tools/spawn_next_generation.sh", tmp_path
    ) is True


def test_demote_false_when_script_missing(tmp_path: pathlib.Path) -> None:
    assert should_demote_to_pass_with_warning(
        "integration: tools/missing.sh", tmp_path
    ) is False


def test_demote_false_when_script_not_executable(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path, "tools/no_exec.sh", executable=False)
    assert should_demote_to_pass_with_warning(
        "integration: tools/no_exec.sh", tmp_path
    ) is False


def test_demote_false_for_non_shell_integration_ac(tmp_path: pathlib.Path) -> None:
    assert should_demote_to_pass_with_warning("integration: bob.verifier", tmp_path) is False


def test_demote_emits_warning_log_on_pass(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    _make_script(tmp_path, "tools/self_heal.sh", executable=True)
    with caplog.at_level(logging.WARNING, logger="bob.verifier.pattern_9_shell_script_ac"):
        result = should_demote_to_pass_with_warning(
            "integration: tools/self_heal.sh", tmp_path
        )
    assert result is True
    assert "F-R7-594" in caplog.text
