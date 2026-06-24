"""Tests for Pattern 9 — shell-script integration AC handler (F-R7-594).

Verifies ``bob.ac_verifier.demote_shell_script_integration_ac``:
when an 'integration:' AC body is a path to an existing executable .sh/.bash
file, the AC is demoted to PASS with a WARNING tagged F-R7-594.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob.ac_verifier import demote_shell_script_integration_ac


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return p


def test_existing_executable_sh_returns_pass(tmp_path: pathlib.Path) -> None:
    """Existing executable .sh → (True, ''), PASS-with-warning."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh")
    result = demote_shell_script_integration_ac(
        "integration: tools/spawn_next_generation.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_existing_executable_bash_returns_pass(tmp_path: pathlib.Path) -> None:
    """.bash extension is also recognised as a shell script."""
    _make_script(tmp_path, "tools/setup.bash")
    result = demote_shell_script_integration_ac("integration: tools/setup.bash", tmp_path)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_missing_script_returns_fail(tmp_path: pathlib.Path) -> None:
    """Missing script → (False, non-empty reason) — real bug still surfaces."""
    result = demote_shell_script_integration_ac(
        "integration: tools/missing.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_non_executable_script_returns_fail(tmp_path: pathlib.Path) -> None:
    """Script exists but is not executable → (False, reason)."""
    _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    result = demote_shell_script_integration_ac(
        "integration: tools/self_heal.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_non_integration_criterion_returns_none(tmp_path: pathlib.Path) -> None:
    """Non-integration ACs return None — Pattern 9 does not handle them."""
    result = demote_shell_script_integration_ac(
        "pytest: tests/test_foo.py::test_bar", tmp_path
    )
    assert result is None


def test_integration_with_python_module_body_returns_none(tmp_path: pathlib.Path) -> None:
    """integration: with a Python dotted path is not a shell script → None."""
    result = demote_shell_script_integration_ac(
        "integration: bob.ac_verifier", tmp_path
    )
    assert result is None


def test_self_heal_sh_regression(tmp_path: pathlib.Path) -> None:
    """Regression guard: tools/self_heal.sh existing and executable → PASS (F-R7-594)."""
    _make_script(tmp_path, "tools/self_heal.sh")
    result = demote_shell_script_integration_ac(
        "integration: tools/self_heal.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_none_workspace_raises(tmp_path: pathlib.Path) -> None:
    """None workspace raises, does not silently succeed."""
    with pytest.raises((TypeError, ValueError)):
        demote_shell_script_integration_ac("integration: tools/run.sh", None)  # type: ignore[arg-type]


def test_non_string_criterion_raises(tmp_path: pathlib.Path) -> None:
    """Non-string criterion raises, does not silently succeed."""
    with pytest.raises((TypeError, ValueError, AttributeError)):
        demote_shell_script_integration_ac(42, tmp_path)  # type: ignore[arg-type]


def test_warns_on_pass_demotion(tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture) -> None:
    """A WARNING log line tagged F-R7-594 is emitted when AC is demoted to PASS."""
    import logging
    _make_script(tmp_path, "tools/run.sh")
    with caplog.at_level(logging.WARNING):
        result = demote_shell_script_integration_ac("integration: tools/run.sh", tmp_path)
    assert result is not None
    passed, _ = result
    assert passed is True
    assert any("F-R7-594" in r.message for r in caplog.records)
