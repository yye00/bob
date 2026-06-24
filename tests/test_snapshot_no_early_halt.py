"""Tests: verifier snapshot path invokes pytest with --maxfail=0.

Acceptance criteria covered:
- Verifier snapshot path invokes pytest with --maxfail=0 (no early termination)
- If xdist is used, --maxfail=0 is enforced
- integration: bob.verifier.snapshot
"""

from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

import bob.orchestrator.run_loop as run_loop_mod
from bob.orchestrator.run_loop import capture_pytest_snapshot
import bob.verifier.snapshot as verifier_snapshot
from bob.verifier.snapshot import MAXFAIL_FLAG, capture as snapshot_capture


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _verdict_lines(*nodeids: str, verdict: str = "PASSED") -> str:
    return "\n".join(f"{nid} {verdict}" for nid in nodeids) + "\n"


# ---------------------------------------------------------------------------
# --maxfail=0 always present in capture_pytest_snapshot
# ---------------------------------------------------------------------------

class TestMaxfailFlagInCaptureSnapshot:
    """capture_pytest_snapshot must always include --maxfail=0."""

    def test_maxfail_zero_in_cmd_without_xdist(self, tmp_path):
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            capture_pytest_snapshot(str(tmp_path), test_dir="tests")

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert pytest_cmds, "pytest was never called"
        for cmd in pytest_cmds:
            assert "--maxfail=0" in cmd, (
                f"--maxfail=0 missing from pytest cmd: {cmd}"
            )

    def test_maxfail_zero_in_cmd_with_xdist(self, tmp_path):
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=0)  # xdist available
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            with patch("os.cpu_count", return_value=8):
                capture_pytest_snapshot(str(tmp_path), test_dir="tests")

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert pytest_cmds, "pytest was never called"
        for cmd in pytest_cmds:
            assert "--maxfail=0" in cmd, (
                f"--maxfail=0 missing from xdist pytest cmd: {cmd}"
            )

    def test_maxfail_zero_appears_before_xdist_flags(self, tmp_path):
        """--maxfail=0 must be in the base command, not added after xdist flags."""
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=0)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            with patch("os.cpu_count", return_value=8):
                capture_pytest_snapshot(str(tmp_path), test_dir="tests")

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert pytest_cmds
        cmd = pytest_cmds[0]
        assert "--maxfail=0" in cmd
        if "-n" in cmd:
            # --maxfail=0 should be in the base command (before -n)
            mf_idx = cmd.index("--maxfail=0")
            n_idx = cmd.index("-n")
            assert mf_idx < n_idx, (
                "--maxfail=0 should appear before xdist -n flag"
            )

    def test_xdist_with_maxfail_zero_both_present(self, tmp_path):
        """When xdist is available, both --maxfail=0 and -n must be in the cmd."""
        (tmp_path / "tests").mkdir()
        captured_cmds: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(list(cmd))
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=0)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            with patch("os.cpu_count", return_value=8):
                capture_pytest_snapshot(str(tmp_path), test_dir="tests")

        pytest_cmds = [c for c in captured_cmds if "pytest" in c]
        assert pytest_cmds
        cmd = pytest_cmds[0]
        assert "--maxfail=0" in cmd
        assert "-n" in cmd
        assert "--dist=loadfile" in cmd


# ---------------------------------------------------------------------------
# bob.verifier.snapshot wrapper
# ---------------------------------------------------------------------------

class TestVerifierSnapshotModule:
    """bob.verifier.snapshot.capture delegates with --maxfail=0 guaranteed."""

    def test_module_exports_maxfail_flag_constant(self):
        assert MAXFAIL_FLAG == "--maxfail=0"

    def test_capture_returns_dict_on_success(self, tmp_path):
        (tmp_path / "tests").mkdir()
        expected = {"tests/t.py::test_a": True}

        def fake_run(cmd, **kwargs):
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            return _fake_proc(stdout=_verdict_lines("tests/t.py::test_a"))

        with patch("subprocess.run", side_effect=fake_run):
            result = snapshot_capture(str(tmp_path), test_dir="tests")

        assert isinstance(result, dict)
        assert "tests/t.py::test_a" in result

    def test_capture_returns_none_on_missing_workspace(self):
        result = snapshot_capture(None)
        assert result is None

    def test_capture_delegates_to_run_loop(self, tmp_path):
        (tmp_path / "tests").mkdir()
        fake_snapshot = {"tests/t.py::test_x": True}

        with patch(
            "bob.orchestrator.run_loop.capture_pytest_snapshot",
            return_value=fake_snapshot,
        ) as mock_fn:
            result = snapshot_capture(str(tmp_path), test_dir="tests")

        mock_fn.assert_called_once_with(
            str(tmp_path), test_dir="tests", changed_files=None
        )
        assert result == fake_snapshot

    def test_capture_passes_changed_files(self, tmp_path):
        (tmp_path / "tests").mkdir()
        changed = ["src/foo.py"]

        with patch(
            "bob.orchestrator.run_loop.capture_pytest_snapshot",
            return_value=None,
        ) as mock_fn:
            snapshot_capture(str(tmp_path), changed_files=changed)

        mock_fn.assert_called_once_with(
            str(tmp_path), test_dir="tests", changed_files=changed
        )


# ---------------------------------------------------------------------------
# --maxfail=0 constant in run_loop command construction
# ---------------------------------------------------------------------------

class TestRunLoopCommandContainsMaxfail:
    """Introspect the source of capture_pytest_snapshot for --maxfail=0."""

    def test_maxfail_zero_literal_in_source(self):
        import inspect
        source = inspect.getsource(capture_pytest_snapshot)
        assert "--maxfail=0" in source, (
            "capture_pytest_snapshot source must contain '--maxfail=0'"
        )

    def test_maxfail_zero_in_cmd_list_not_just_comments(self):
        """Verify --maxfail=0 appears in a list literal, not just a comment."""
        import ast
        import inspect
        source = inspect.getsource(capture_pytest_snapshot)
        tree = ast.parse(source)
        found_in_list = False
        for node in ast.walk(tree):
            if isinstance(node, ast.List):
                for elt in node.elts:
                    if isinstance(elt, ast.Constant) and elt.value == "--maxfail=0":
                        found_in_list = True
                        break
        assert found_in_list, (
            "--maxfail=0 must appear as a string literal in a list in capture_pytest_snapshot"
        )
