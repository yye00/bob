"""Tests for src/bob/pattern_9_shell_script_handler.py — Pattern 9 (F-R7-594).

Verifies that demote_shell_script_ac:
- Returns (True, "") when the integration AC body is an existing executable .sh/.bash file.
- Returns (False, reason) when the script is missing or not executable.
- Returns None for non-shell-script integration ACs and non-integration criteria.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob.pattern_9_shell_script_handler import demote_shell_script_ac


def _make_executable_script(path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\necho hello\n")
    path.chmod(0o755)
    return path


class TestDemoteShellScriptAc:
    def test_existing_executable_sh_returns_pass(self, tmp_path: pathlib.Path) -> None:
        script = _make_executable_script(tmp_path / "tools" / "deploy.sh")
        result = demote_shell_script_ac("integration: tools/deploy.sh", tmp_path)
        assert result == (True, "")

    def test_existing_executable_bash_returns_pass(self, tmp_path: pathlib.Path) -> None:
        script = _make_executable_script(tmp_path / "tools" / "setup.bash")
        result = demote_shell_script_ac("integration: tools/setup.bash", tmp_path)
        assert result == (True, "")

    def test_missing_script_returns_false(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_ac("integration: tools/missing.sh", tmp_path)
        assert result is not None
        passed, reason = result
        assert passed is False
        assert "not found" in reason or reason

    def test_non_executable_script_returns_false(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "tools" / "nox.sh"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/bash\necho hi\n")
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        result = demote_shell_script_ac("integration: tools/nox.sh", tmp_path)
        assert result is not None
        passed, reason = result
        assert passed is False

    def test_non_integration_criterion_returns_none(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_ac("pytest: tests/test_foo.py::test_bar", tmp_path)
        assert result is None

    def test_integration_dotted_python_path_returns_none(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_ac("integration: bob.patterns", tmp_path)
        assert result is None

    def test_integration_prefix_only_returns_none(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_ac("integration:", tmp_path)
        assert result is None

    def test_empty_criterion_returns_none(self, tmp_path: pathlib.Path) -> None:
        result = demote_shell_script_ac("", tmp_path)
        assert result is None

    def test_spawn_next_generation_script(self, tmp_path: pathlib.Path) -> None:
        """Simulates the original NH'd feature (51fc8cb1) that triggered F-R7-594."""
        _make_executable_script(tmp_path / "tools" / "spawn_next_generation.sh")
        result = demote_shell_script_ac(
            "integration: tools/spawn_next_generation.sh", tmp_path
        )
        assert result == (True, "")

    def test_self_heal_script(self, tmp_path: pathlib.Path) -> None:
        """Simulates the original NH'd feature (949e97e1) that triggered F-R7-594."""
        _make_executable_script(tmp_path / "tools" / "self_heal.sh")
        result = demote_shell_script_ac("integration: tools/self_heal.sh", tmp_path)
        assert result == (True, "")
