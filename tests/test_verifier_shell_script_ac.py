"""Tests for bob3.verifier.demote_shell_script_integration_ac (Pattern 9, F-R7-594).

Verifies that check_shell_script_integration / demote_shell_script_integration_ac
in bob3.verifier correctly handles integration ACs referencing shell scripts.
"""

from __future__ import annotations

import os
import pathlib
import stat

import pytest

from bob3.verifier import demote_shell_script_integration_ac


def _make_executable_script(path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\necho ok\n")
    path.chmod(0o755)
    return path


class TestDemoteShellScriptIntegrationAc:
    def test_existing_executable_sh_returns_true(self, tmp_path: pathlib.Path) -> None:
        _make_executable_script(tmp_path / "tools" / "run.sh")
        result = demote_shell_script_integration_ac("integration: tools/run.sh", tmp_path)
        assert result is not None
        passed, reason = result
        assert passed is True
        assert reason == ""

    def test_existing_executable_bash_returns_true(self, tmp_path: pathlib.Path) -> None:
        _make_executable_script(tmp_path / "tools" / "run.bash")
        result = demote_shell_script_integration_ac("integration: tools/run.bash", tmp_path)
        assert result is not None
        passed, reason = result
        assert passed is True
        assert reason == ""

    def test_missing_script_returns_false(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_integration_ac(
            "integration: tools/missing.sh", tmp_path
        )
        assert result is not None
        passed, reason = result
        assert passed is False
        assert reason

    def test_non_executable_script_returns_false(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "tools" / "noexec.sh"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/bash\n")
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        result = demote_shell_script_integration_ac("integration: tools/noexec.sh", tmp_path)
        assert result is not None
        passed, reason = result
        assert passed is False
        assert reason

    def test_non_integration_criterion_returns_none(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_integration_ac(
            "pytest: tests/test_foo.py::test_bar", tmp_path
        )
        assert result is None

    def test_integration_with_python_module_returns_none(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_integration_ac("integration: bob3.verifier", tmp_path)
        assert result is None

    def test_spawn_next_generation_script(self, tmp_path: pathlib.Path) -> None:
        """Mirrors the real-world case that triggered F-R7-594."""
        _make_executable_script(tmp_path / "tools" / "spawn_next_generation.sh")
        result = demote_shell_script_integration_ac(
            "integration: tools/spawn_next_generation.sh", tmp_path
        )
        assert result is not None
        passed, _ = result
        assert passed is True

    def test_self_heal_script(self, tmp_path: pathlib.Path) -> None:
        """Mirrors the real-world case that triggered F-R7-594."""
        _make_executable_script(tmp_path / "tools" / "self_heal.sh")
        result = demote_shell_script_integration_ac(
            "integration: tools/self_heal.sh", tmp_path
        )
        assert result is not None
        passed, _ = result
        assert passed is True

    def test_function_is_importable_from_verifier_module(self) -> None:
        """Confirms the alias is exported from bob3.verifier."""
        import bob3.verifier as m
        assert callable(getattr(m, "demote_shell_script_integration_ac", None))
