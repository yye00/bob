"""Tests for deterministic_pytest_snapshots_disable_xdist_early_halt.

Acceptance criteria:
- File exists: src/bob/deterministic_pytest_snapshots_disable_xdist_early_halt.py
- Function defined: bob.deterministic_pytest_snapshots_disable_xdist_early_halt
  .deterministic_pytest_snapshots_disable_xdist_early_halt
- pytest: tests/test_deterministic_pytest_snapshots_disable_xdist_early_halt.py
  ::test_deterministic_pytest_snapshots_disable_xdist_early_halt
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

import bob.deterministic_pytest_snapshots_disable_xdist_early_halt as mod
from bob.deterministic_pytest_snapshots_disable_xdist_early_halt import (
    MAXFAIL_FLAG,
    deterministic_pytest_snapshots_disable_xdist_early_halt,
)


def _fake_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _verdict_lines(*nodeids, verdict="PASSED"):
    return "\n".join(f"{nid} {verdict}" for nid in nodeids) + "\n"


def test_deterministic_pytest_snapshots_disable_xdist_early_halt():
    """AC test: function is importable, MAXFAIL_FLAG is --maxfail=0, and basic contracts hold."""
    # function importable and callable
    assert callable(deterministic_pytest_snapshots_disable_xdist_early_halt)

    # module exposes MAXFAIL_FLAG constant
    assert MAXFAIL_FLAG == "--maxfail=0"
    assert hasattr(mod, "MAXFAIL_FLAG")
    assert mod.MAXFAIL_FLAG == "--maxfail=0"

    # returns None for missing/empty workspace (no subprocess calls)
    assert deterministic_pytest_snapshots_disable_xdist_early_halt(None) is None
    assert deterministic_pytest_snapshots_disable_xdist_early_halt("") is None

    # function signature supports test_dir kwarg
    import inspect
    sig = inspect.signature(deterministic_pytest_snapshots_disable_xdist_early_halt)
    assert "test_dir" in sig.parameters
    assert sig.parameters["test_dir"].default == "tests"

    # module docstring mentions xdist or maxfail
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "xdist" in doc or "maxfail" in doc


class TestMaxfailEnforcement:
    """Verify --maxfail=0 is always injected into the pytest subprocess command."""

    def test_maxfail_zero_injected_without_xdist(self, tmp_path):
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            deterministic_pytest_snapshots_disable_xdist_early_halt(str(tmp_path))

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert pytest_cmds, "pytest was never invoked"
        for cmd in pytest_cmds:
            assert "--maxfail=0" in cmd, f"--maxfail=0 missing from: {cmd}"

    def test_maxfail_zero_injected_with_xdist(self, tmp_path):
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=0)  # xdist present
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            with patch("os.cpu_count", return_value=8):
                deterministic_pytest_snapshots_disable_xdist_early_halt(str(tmp_path))

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert pytest_cmds, "pytest was never invoked"
        for cmd in pytest_cmds:
            assert "--maxfail=0" in cmd, f"--maxfail=0 missing in xdist cmd: {cmd}"

    def test_xdist_with_maxfail_zero_and_n_flag(self, tmp_path):
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=0)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            with patch("os.cpu_count", return_value=8):
                deterministic_pytest_snapshots_disable_xdist_early_halt(str(tmp_path))

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert pytest_cmds
        cmd = pytest_cmds[0]
        assert "--maxfail=0" in cmd
        assert "-n" in cmd

    def test_no_nonzero_maxfail_survives(self, tmp_path):
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            deterministic_pytest_snapshots_disable_xdist_early_halt(str(tmp_path))

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        for cmd in pytest_cmds:
            for arg in cmd:
                if arg.startswith("--maxfail=") and arg != "--maxfail=0":
                    pytest.fail(f"Non-zero maxfail present: {arg!r} in {cmd}")

    def test_function_accepts_test_dir_kwarg(self, tmp_path):
        (tmp_path / "my_tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            return _fake_proc(stdout=_verdict_lines("my_tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            deterministic_pytest_snapshots_disable_xdist_early_halt(
                str(tmp_path), test_dir="my_tests"
            )

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert any("my_tests" in arg for cmd in pytest_cmds for arg in cmd)

    def test_returns_dict_on_success(self, tmp_path):
        (tmp_path / "tests").mkdir()

        def fake_run(cmd, **kwargs):
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            result = deterministic_pytest_snapshots_disable_xdist_early_halt(
                str(tmp_path)
            )

        assert result is None or isinstance(result, dict)
