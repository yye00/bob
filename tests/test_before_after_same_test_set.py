"""Tests: before/after snapshots cover the same test set.

Validates that with --maxfail=0, both before and after snapshots always
contain the same test node IDs regardless of how many tests fail — so the
diff only reflects genuine regressions, not missing tests due to early halt.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bob.orchestrator.run_loop import capture_pytest_snapshot
from bob.verifier.snapshot import capture as snapshot_capture


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _build_verbose_output(results: dict[str, bool]) -> str:
    """Build pytest -v style output from a nodeid→passed mapping."""
    lines = []
    for nid, passed in results.items():
        verdict = "PASSED" if passed else "FAILED"
        lines.append(f"{nid} {verdict}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Same test set before and after
# ---------------------------------------------------------------------------

class TestBeforeAfterSameTestSet:
    """Snapshots taken before and after code changes must have identical key sets."""

    def _run_two_snapshots(
        self,
        tmp_path,
        before_results: dict[str, bool],
        after_results: dict[str, bool],
    ) -> tuple[dict, dict]:
        (tmp_path / "tests").mkdir(exist_ok=True)
        call_count = [0]

        def fake_run(cmd, **kwargs):
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            call_count[0] += 1
            if call_count[0] == 1:
                return _fake_proc(stdout=_build_verbose_output(before_results))
            return _fake_proc(stdout=_build_verbose_output(after_results))

        with patch("subprocess.run", side_effect=fake_run):
            before = capture_pytest_snapshot(str(tmp_path), test_dir="tests")
            after = capture_pytest_snapshot(str(tmp_path), test_dir="tests")

        return before, after

    def test_same_keys_all_passing(self, tmp_path):
        tests = {
            "tests/test_a.py::test_one": True,
            "tests/test_a.py::test_two": True,
            "tests/test_b.py::test_three": True,
        }
        before, after = self._run_two_snapshots(tmp_path, tests, tests)
        assert set(before.keys()) == set(after.keys())

    def test_same_keys_with_many_failures_in_before(self, tmp_path):
        before_results = {f"tests/t.py::test_{i}": (i % 3 != 0) for i in range(30)}
        after_results = {k: True for k in before_results}
        before, after = self._run_two_snapshots(tmp_path, before_results, after_results)
        assert set(before.keys()) == set(after.keys())

    def test_same_keys_with_many_failures_in_after(self, tmp_path):
        nodeids = {f"tests/t.py::test_{i}": True for i in range(30)}
        after_results = {k: (i % 5 != 0) for i, k in enumerate(nodeids)}
        before, after = self._run_two_snapshots(tmp_path, nodeids, after_results)
        assert set(before.keys()) == set(after.keys())

    def test_regression_detected_correctly(self, tmp_path):
        """Only tests that changed from True→False should appear as regressions."""
        shared = {
            "tests/t.py::test_stable_pass": True,
            "tests/t.py::test_stable_fail": False,
            "tests/t.py::test_regressed": True,
        }
        after_results = dict(shared)
        after_results["tests/t.py::test_regressed"] = False

        before, after = self._run_two_snapshots(tmp_path, shared, after_results)

        regressions = [nid for nid, passed in after.items() if not passed and before.get(nid, False)]
        assert regressions == ["tests/t.py::test_regressed"]

    def test_no_false_regressions_when_test_absent_in_before(self, tmp_path):
        """A test failing in 'after' is not a regression if it was absent from 'before'."""
        before_results = {"tests/t.py::test_existing": True}
        after_results = {
            "tests/t.py::test_existing": True,
            "tests/t.py::test_new_failing": False,
        }
        before, after = self._run_two_snapshots(tmp_path, before_results, after_results)
        regressions = [
            nid for nid, passed in after.items()
            if not passed and before.get(nid) is True
        ]
        assert "tests/t.py::test_new_failing" not in regressions

    def test_25_failures_still_full_set(self, tmp_path):
        """Simulate old xdist halting at 25: with --maxfail=0 all 50 nodes present."""
        nodeids = {f"tests/t.py::test_{i:03d}": (i >= 25) for i in range(50)}
        before, after = self._run_two_snapshots(tmp_path, nodeids, nodeids)
        assert len(before) == 50
        assert len(after) == 50
        assert set(before.keys()) == set(after.keys())


# ---------------------------------------------------------------------------
# xdist does not reduce snapshot coverage
# ---------------------------------------------------------------------------

class TestXdistDoesNotReduceSnapshots:
    """With xdist and --maxfail=0, snapshot covers all tests even when many fail."""

    def test_xdist_snapshot_covers_all_tests_with_failures(self, tmp_path):
        (tmp_path / "tests").mkdir()
        all_nodeids = {f"tests/t.py::test_{i:03d}": (i % 4 != 0) for i in range(40)}
        xdist_output_lines = []
        for i, (nid, passed) in enumerate(all_nodeids.items()):
            worker = i % 4
            verdict = "PASSED" if passed else "FAILED"
            pct = int((i + 1) / len(all_nodeids) * 100)
            xdist_output_lines.append(f"[gw{worker}] [{pct:3d}%] {verdict} {nid}")
        xdist_output = "\n".join(xdist_output_lines) + "\n"

        call_count = [0]

        def fake_run(cmd, **kwargs):
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=0)
            call_count[0] += 1
            return _fake_proc(stdout=xdist_output)

        with patch("subprocess.run", side_effect=fake_run):
            with patch("os.cpu_count", return_value=8):
                snapshot = capture_pytest_snapshot(str(tmp_path), test_dir="tests")

        assert snapshot is not None
        assert len(snapshot) == 40, (
            f"Expected 40 tests in snapshot, got {len(snapshot)}"
        )

    def test_verifier_snapshot_capture_consistent(self, tmp_path):
        (tmp_path / "tests").mkdir()
        nodeids = {f"tests/t.py::test_{i}": True for i in range(10)}
        output = _build_verbose_output(nodeids)

        def fake_run(cmd, **kwargs):
            if cmd == ["python", "-c", "import xdist"]:
                return _fake_proc(returncode=1)
            return _fake_proc(stdout=output)

        with patch("subprocess.run", side_effect=fake_run):
            s1 = snapshot_capture(str(tmp_path), test_dir="tests")
        with patch("subprocess.run", side_effect=fake_run):
            s2 = snapshot_capture(str(tmp_path), test_dir="tests")

        assert set(s1.keys()) == set(s2.keys())


# ---------------------------------------------------------------------------
# Integration: bob.verifier.snapshot module is importable
# ---------------------------------------------------------------------------

class TestVerifierSnapshotIntegration:
    def test_module_importable(self):
        import bob.verifier.snapshot as m
        assert hasattr(m, "capture")
        assert hasattr(m, "MAXFAIL_FLAG")

    def test_maxfail_flag_value(self):
        from bob.verifier.snapshot import MAXFAIL_FLAG
        assert MAXFAIL_FLAG == "--maxfail=0"

    def test_capture_is_callable(self):
        from bob.verifier.snapshot import capture
        assert callable(capture)

    def test_capture_none_workspace_returns_none(self):
        from bob.verifier.snapshot import capture
        assert capture(None) is None
