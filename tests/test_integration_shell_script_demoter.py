"""Tests for bob.integration_shell_script_demoter (Pattern 9, F-R7-594).

Pattern 9: when an 'integration:' AC body is a path to an existing, executable
.sh/.bash file, demote the AC to PASS with a WARNING.  Missing or
non-executable scripts hard-FAIL so real bugs still surface.  Non-shell-script
bodies return None so the caller continues to the next pattern.
"""

from __future__ import annotations

import logging
import pathlib
import stat

import pytest

from bob.integration_shell_script_demoter import (
    demote_shell_script_integration_ac,
    is_executable_shell_script_integration,
)


def _make_script(path: pathlib.Path, *, executable: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\necho hi\n")
    if executable:
        path.chmod(0o755)
    else:
        path.chmod(path.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


# --- is_executable_shell_script_integration ---------------------------------


def test_predicate_true_for_existing_executable_script(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "run.sh", executable=True)
    assert is_executable_shell_script_integration(
        "integration: tools/run.sh", tmp_path
    ) is True


def test_predicate_true_for_bash_extension(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "run.bash", executable=True)
    assert is_executable_shell_script_integration(
        "integration: tools/run.bash", tmp_path
    ) is True


def test_predicate_false_for_missing_script(tmp_path: pathlib.Path) -> None:
    assert is_executable_shell_script_integration(
        "integration: tools/missing.sh", tmp_path
    ) is False


def test_predicate_false_for_non_executable_script(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "run.sh", executable=False)
    assert is_executable_shell_script_integration(
        "integration: tools/run.sh", tmp_path
    ) is False


def test_predicate_false_for_non_shell_body(tmp_path: pathlib.Path) -> None:
    assert is_executable_shell_script_integration(
        "integration: bob.verification.integration_ac_resolver", tmp_path
    ) is False


def test_predicate_false_for_non_integration_criterion(tmp_path: pathlib.Path) -> None:
    assert is_executable_shell_script_integration(
        "pytest: tests/test_foo.py::test_bar", tmp_path
    ) is False


# --- demote_shell_script_integration_ac -------------------------------------


def test_demote_pass_for_executable_script(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    _make_script(tmp_path / "tools" / "spawn_next_generation.sh", executable=True)
    with caplog.at_level(logging.WARNING):
        result = demote_shell_script_integration_ac(
            "integration: tools/spawn_next_generation.sh", tmp_path
        )
    assert result == (True, "")
    assert any("F-R7-594" in rec.getMessage() for rec in caplog.records)


def test_demote_fail_for_missing_script(tmp_path: pathlib.Path) -> None:
    result = demote_shell_script_integration_ac(
        "integration: tools/self_heal.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "not found" in reason.lower() or "missing" in reason.lower()


def test_demote_fail_for_non_executable_script(tmp_path: pathlib.Path) -> None:
    _make_script(tmp_path / "tools" / "self_heal.sh", executable=False)
    result = demote_shell_script_integration_ac(
        "integration: tools/self_heal.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is False
    assert "executable" in reason.lower()


def test_demote_none_for_dotted_python_path(tmp_path: pathlib.Path) -> None:
    result = demote_shell_script_integration_ac(
        "integration: bob.verification.integration_ac_resolver", tmp_path
    )
    assert result is None


def test_demote_none_for_non_integration_criterion(tmp_path: pathlib.Path) -> None:
    result = demote_shell_script_integration_ac(
        "pytest: tests/test_foo.py::test_bar", tmp_path
    )
    assert result is None


def test_demote_type_error_for_none_criterion(tmp_path: pathlib.Path) -> None:
    with pytest.raises((TypeError, ValueError)):
        demote_shell_script_integration_ac(None, tmp_path)  # type: ignore[arg-type]


def test_predicate_type_error_for_none_criterion(tmp_path: pathlib.Path) -> None:
    with pytest.raises((TypeError, ValueError)):
        is_executable_shell_script_integration(None, tmp_path)  # type: ignore[arg-type]
