"""Tests for src/bob/verifier/pattern9_shell_integration.py (F-R7-594).

Covers is_shell_script_integration and demote_to_pass_with_warning.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob.verifier.pattern9_shell_integration import (
    demote_to_pass_with_warning,
    is_shell_script_integration,
)


# ---------------------------------------------------------------------------
# is_shell_script_integration
# ---------------------------------------------------------------------------


def test_is_shell_script_integration_true_for_sh() -> None:
    assert is_shell_script_integration("integration: tools/spawn_next_generation.sh") is True


def test_is_shell_script_integration_true_for_bash() -> None:
    assert is_shell_script_integration("integration: tools/setup.bash") is True


def test_is_shell_script_integration_false_for_pytest_ac() -> None:
    assert is_shell_script_integration("pytest: tests/test_foo.py::test_bar") is False


def test_is_shell_script_integration_false_for_python_module_body() -> None:
    assert is_shell_script_integration("integration: bob.orchestrator") is False


def test_is_shell_script_integration_false_for_empty_string() -> None:
    assert is_shell_script_integration("") is False


def test_is_shell_script_integration_case_insensitive_prefix() -> None:
    assert is_shell_script_integration("Integration: tools/run.sh") is True


def test_is_shell_script_integration_none_raises() -> None:
    with pytest.raises((TypeError, ValueError)):
        is_shell_script_integration(None)  # type: ignore[arg-type]


def test_is_shell_script_integration_non_string_raises() -> None:
    with pytest.raises((TypeError, ValueError)):
        is_shell_script_integration(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# demote_to_pass_with_warning
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


def test_demote_pass_when_script_exists_and_executable(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path, "tools/spawn_next_generation.sh", executable=True)
    result = demote_to_pass_with_warning("integration: tools/spawn_next_generation.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_demote_fail_when_script_missing(tmp_path: pathlib.Path) -> None:
    result = demote_to_pass_with_warning("integration: tools/missing.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "not found" in reason


def test_demote_fail_when_script_not_executable(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    result = demote_to_pass_with_warning("integration: tools/self_heal.sh", tmp_path)
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "not executable" in reason


def test_demote_none_for_non_integration_criterion(tmp_path: pathlib.Path) -> None:
    result = demote_to_pass_with_warning("pytest: tests/test_foo.py::test_bar", tmp_path)
    assert result is None


def test_demote_none_for_python_module_body(tmp_path: pathlib.Path) -> None:
    result = demote_to_pass_with_warning("integration: bob.verifier", tmp_path)
    assert result is None


def test_demote_pass_for_bash_extension(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path, "tools/setup.bash", executable=True)
    result = demote_to_pass_with_warning("integration: tools/setup.bash", tmp_path)
    assert result is not None
    passed, _ = result
    assert passed is True


def test_demote_warns_with_f_r7_594_tag(tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture) -> None:
    import logging
    _make_script(tmp_path, "tools/run.sh", executable=True)
    with caplog.at_level(logging.WARNING, logger="bob.verifier.pattern9_shell_integration"):
        demote_to_pass_with_warning("integration: tools/run.sh", tmp_path)
    assert any("F-R7-594" in r.message for r in caplog.records)


def test_demote_none_criterion_raises() -> None:
    with pytest.raises((TypeError, ValueError)):
        demote_to_pass_with_warning(None, pathlib.Path("/tmp"))  # type: ignore[arg-type]


def test_demote_none_workspace_raises() -> None:
    with pytest.raises((TypeError, ValueError, AttributeError)):
        demote_to_pass_with_warning("integration: tools/run.sh", None)  # type: ignore[arg-type]
