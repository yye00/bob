"""Tests for bob3.ac_handler Pattern 9 — shell-script integration AC handler (F-R7-594).

Exercises ``demote_shell_script_integration`` and its alias
``demote_shell_script_integration_ac`` from ``bob3.ac_handler``.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.ac_handler import (
    demote_shell_script_integration,
    demote_shell_script_integration_ac,
)


def _make_script(workspace: pathlib.Path, rel: str, executable: bool = True) -> pathlib.Path:
    p = workspace / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return p


# ── canonical entry point ─────────────────────────────────────────────────────


def test_demote_shell_script_integration_pass_with_existing_executable(
    tmp_path: pathlib.Path,
) -> None:
    """Existing executable .sh → (True, '') — AC demoted to PASS with warning."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh")
    result = demote_shell_script_integration(
        "integration: tools/spawn_next_generation.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_demote_shell_script_integration_fail_missing_script(
    tmp_path: pathlib.Path,
) -> None:
    """Missing script → (False, reason) — real bug surfaces correctly."""
    result = demote_shell_script_integration(
        "integration: tools/missing.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_demote_shell_script_integration_fail_non_executable(
    tmp_path: pathlib.Path,
) -> None:
    """Non-executable script → (False, reason) — safety invariant enforced."""
    _make_script(tmp_path, "tools/self_heal.sh", executable=False)
    result = demote_shell_script_integration(
        "integration: tools/self_heal.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is False
    assert reason


def test_demote_shell_script_integration_returns_none_for_non_integration(
    tmp_path: pathlib.Path,
) -> None:
    """Non-integration criterion → None; caller should continue to next pattern."""
    result = demote_shell_script_integration(
        "pytest: tests/test_foo.py::test_bar", tmp_path
    )
    assert result is None


def test_demote_shell_script_integration_returns_none_for_python_path(
    tmp_path: pathlib.Path,
) -> None:
    """integration: with a dotted Python path → None (not a shell script)."""
    result = demote_shell_script_integration(
        "integration: bob3.verifier", tmp_path
    )
    assert result is None


def test_demote_shell_script_integration_recognises_bash_extension(
    tmp_path: pathlib.Path,
) -> None:
    """.bash extension is also recognised as a shell script."""
    _make_script(tmp_path, "tools/setup.bash")
    result = demote_shell_script_integration(
        "integration: tools/setup.bash", tmp_path
    )
    assert result is not None
    passed, _ = result
    assert passed is True


# ── alias ─────────────────────────────────────────────────────────────────────


def test_alias_demote_shell_script_integration_ac_is_callable(
    tmp_path: pathlib.Path,
) -> None:
    """demote_shell_script_integration_ac alias works identically."""
    _make_script(tmp_path, "tools/run.sh")
    result = demote_shell_script_integration_ac(
        "integration: tools/run.sh", tmp_path
    )
    assert result is not None
    passed, reason = result
    assert passed is True
    assert reason == ""


def test_alias_matches_primary_function_on_missing_script(
    tmp_path: pathlib.Path,
) -> None:
    """demote_shell_script_integration_ac returns same result as primary on failure."""
    primary = demote_shell_script_integration("integration: tools/ghost.sh", tmp_path)
    alias = demote_shell_script_integration_ac("integration: tools/ghost.sh", tmp_path)
    assert primary == alias


# ── regression guards for NH'd features (F-R7-594) ───────────────────────────


def test_regression_spawn_next_generation_sh(tmp_path: pathlib.Path) -> None:
    """Regression: 51fc8cb1 (Parent-gen DB inheritance) integration AC must PASS."""
    _make_script(tmp_path, "tools/spawn_next_generation.sh")
    result = demote_shell_script_integration(
        "integration: tools/spawn_next_generation.sh", tmp_path
    )
    assert result is not None
    assert result[0] is True


def test_regression_self_heal_sh(tmp_path: pathlib.Path) -> None:
    """Regression: 949e97e1 (Stale-bytecode guard) integration AC must PASS."""
    _make_script(tmp_path, "tools/self_heal.sh")
    result = demote_shell_script_integration(
        "integration: tools/self_heal.sh", tmp_path
    )
    assert result is not None
    assert result[0] is True
