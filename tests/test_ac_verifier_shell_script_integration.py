"""Tests for bob3.ac_verifier.handle_shell_script_integration (Pattern 9 / F-R7-594).

Verifies that integration ACs whose body is an executable shell script are
demoted to PASS-with-warning rather than hard-failing the feature.
"""

from __future__ import annotations

import pathlib
import stat

import pytest

from bob3.ac_verifier import (
    demote_shell_script_integration_ac,
    handle_shell_script_integration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_executable_script(directory: pathlib.Path, relative: str) -> pathlib.Path:
    p = directory / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/bash\necho hello\n")
    p.chmod(0o755)
    return p


# ---------------------------------------------------------------------------
# handle_shell_script_integration — happy paths
# ---------------------------------------------------------------------------

class TestHandleShellScriptIntegration:
    def test_returns_pass_when_sh_script_exists_and_executable(self, tmp_path: pathlib.Path) -> None:
        _make_executable_script(tmp_path, "tools/spawn_next_generation.sh")
        result = handle_shell_script_integration(
            "integration: tools/spawn_next_generation.sh", tmp_path
        )
        assert result is not None
        passed, reason = result
        assert passed is True
        assert reason == ""

    def test_returns_pass_when_bash_script_exists_and_executable(self, tmp_path: pathlib.Path) -> None:
        _make_executable_script(tmp_path, "tools/self_heal.bash")
        result = handle_shell_script_integration(
            "integration: tools/self_heal.bash", tmp_path
        )
        assert result is not None
        passed, _ = result
        assert passed is True

    def test_returns_none_for_pytest_ac(self, tmp_path: pathlib.Path) -> None:
        result = handle_shell_script_integration(
            "pytest: tests/test_foo.py::test_bar", tmp_path
        )
        assert result is None

    def test_returns_none_for_python_module_integration(self, tmp_path: pathlib.Path) -> None:
        result = handle_shell_script_integration(
            "integration: bob3.ac_verifier", tmp_path
        )
        assert result is None

    def test_returns_false_when_script_missing(self, tmp_path: pathlib.Path) -> None:
        result = handle_shell_script_integration(
            "integration: tools/missing.sh", tmp_path
        )
        assert result is not None
        passed, reason = result
        assert passed is False
        assert reason

    def test_returns_false_when_script_not_executable(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "tools" / "locked.sh"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/bash\necho hi\n")
        p.chmod(p.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        result = handle_shell_script_integration("integration: tools/locked.sh", tmp_path)
        assert result is not None
        passed, reason = result
        assert passed is False
        assert reason

    def test_is_alias_for_demote_shell_script_integration_ac(self, tmp_path: pathlib.Path) -> None:
        _make_executable_script(tmp_path, "tools/run.sh")
        r1 = handle_shell_script_integration("integration: tools/run.sh", tmp_path)
        r2 = demote_shell_script_integration_ac("integration: tools/run.sh", tmp_path)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Real-workspace scripts (tools/spawn_next_generation.sh, tools/self_heal.sh)
# ---------------------------------------------------------------------------

class TestRealWorkspaceScripts:
    """Verify that the two known shell-script integration ACs from NH'd features pass."""

    _WORKSPACE = pathlib.Path(__file__).parent.parent

    def test_spawn_next_generation_sh_passes(self) -> None:
        result = handle_shell_script_integration(
            "integration: tools/spawn_next_generation.sh", self._WORKSPACE
        )
        assert result is not None
        passed, reason = result
        assert passed is True, f"Expected PASS but got FAIL: {reason}"

    def test_self_heal_sh_passes(self) -> None:
        result = handle_shell_script_integration(
            "integration: tools/self_heal.sh", self._WORKSPACE
        )
        assert result is not None
        passed, reason = result
        assert passed is True, f"Expected PASS but got FAIL: {reason}"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestErrorPaths:
    def test_none_workspace_raises(self) -> None:
        with pytest.raises((TypeError, ValueError, AttributeError)):
            handle_shell_script_integration("integration: tools/run.sh", None)  # type: ignore[arg-type]

    def test_non_string_criterion_raises(self) -> None:
        with pytest.raises((TypeError, ValueError, AttributeError)):
            handle_shell_script_integration(42, pathlib.Path("/tmp"))  # type: ignore[arg-type]
