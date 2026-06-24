"""Tests for Pattern 9 — shell-script integration AC handler (F-R7-594).

Verifies handle_shell_script_ac from bob3.patterns.pattern_9:
- Existing executable .sh/.bash → PASS (True, "")
- Missing script → FAIL (False, reason)
- Non-executable script → FAIL (False, reason)
- Non-integration or non-shell criterion → None (fall-through)
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.patterns.pattern_9 import handle_shell_script_ac


@pytest.fixture
def tmp_workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path


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


def test_demote_to_pass_sh_exists_and_executable(tmp_workspace: pathlib.Path) -> None:
    _make_script(tmp_workspace, "tools/spawn_next_generation.sh", executable=True)
    result = handle_shell_script_ac("integration: tools/spawn_next_generation.sh", tmp_workspace)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_fail_when_script_missing(tmp_workspace: pathlib.Path) -> None:
    result = handle_shell_script_ac("integration: tools/missing_script.sh", tmp_workspace)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "not found" in reason


def test_fail_when_script_not_executable(tmp_workspace: pathlib.Path) -> None:
    _make_script(tmp_workspace, "tools/self_heal.sh", executable=False)
    result = handle_shell_script_ac("integration: tools/self_heal.sh", tmp_workspace)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "not executable" in reason


def test_returns_none_for_non_integration_criterion(tmp_workspace: pathlib.Path) -> None:
    assert handle_shell_script_ac("pytest: tests/test_foo.py::test_bar", tmp_workspace) is None


def test_returns_none_for_non_shell_integration_body(tmp_workspace: pathlib.Path) -> None:
    assert handle_shell_script_ac("integration: bob3.verifier", tmp_workspace) is None


def test_bash_extension_recognised(tmp_workspace: pathlib.Path) -> None:
    _make_script(tmp_workspace, "tools/setup.bash", executable=True)
    result = handle_shell_script_ac("integration: tools/setup.bash", tmp_workspace)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_case_insensitive_integration_prefix(tmp_workspace: pathlib.Path) -> None:
    _make_script(tmp_workspace, "tools/run.sh", executable=True)
    result = handle_shell_script_ac("Integration: tools/run.sh", tmp_workspace)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_warning_emitted_on_pass(tmp_workspace: pathlib.Path, caplog: pytest.LogCaptureFixture) -> None:
    import logging
    _make_script(tmp_workspace, "tools/deploy.sh", executable=True)
    with caplog.at_level(logging.WARNING, logger="bob3.patterns.pattern_9"):
        result = handle_shell_script_ac("integration: tools/deploy.sh", tmp_workspace)
    assert result == (True, "")
    assert any("F-R7-594" in r.message for r in caplog.records)


def test_nested_path_within_workspace(tmp_workspace: pathlib.Path) -> None:
    _make_script(tmp_workspace, "a/b/c/script.sh", executable=True)
    result = handle_shell_script_ac("integration: a/b/c/script.sh", tmp_workspace)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_returns_none_for_python_module_path(tmp_workspace: pathlib.Path) -> None:
    assert handle_shell_script_ac("integration: bob3.patterns.pattern_9", tmp_workspace) is None
