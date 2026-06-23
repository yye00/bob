"""Tests for bob3.verifier.baseline_capture — collection gate.

Verifies that collect_and_capture:
- Aborts with status="baseline_unstable" when pytest --collect-only exits 2.
- Identifies the failing test file in the result.
- Returns status="ok" and a snapshot when collection is clean.
- Handles missing workspace / test dir gracefully.
"""
from __future__ import annotations

import pathlib
import subprocess
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from bob3.verifier.baseline_capture import (
    BaselineCaptureResult,
    BaselineUnstableError,
    CollectResult,
    abort_on_collect_error,
    collect_and_capture,
    is_baseline_unstable,
    _UNSTABLE_MARKER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# Collection failures → baseline_unstable
# ---------------------------------------------------------------------------

class TestCollectErrorTriggersAbort:
    """collect_and_capture must abort when --collect-only exits with code 2."""

    def test_returns_baseline_unstable_status(self, tmp_path):
        (tmp_path / "tests").mkdir()
        collect_output = "ERROR collecting tests/test_bad.py\nImportError: No module named foo\n"
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_output)):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.status == "baseline_unstable"

    def test_snapshot_is_none_on_unstable(self, tmp_path):
        (tmp_path / "tests").mkdir()
        collect_output = "ERROR collecting tests/test_bad.py\n"
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_output)):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.snapshot is None

    def test_identifies_failing_file(self, tmp_path):
        (tmp_path / "tests").mkdir()
        collect_output = (
            "ERROR collecting tests/test_property_based_test_generator_hypothesis_ears.py\n"
            "ImportError: No module named hypothesis\n"
        )
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_output)):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.failing_collection_file == (
            "tests/test_property_based_test_generator_hypothesis_ears.py"
        )

    def test_identifies_second_known_bad_file(self, tmp_path):
        (tmp_path / "tests").mkdir()
        collect_output = (
            "ERROR collecting tests/test_spec_linter_pre_spawn_quality_gate.py\n"
            "ImportError: cannot import name 'SpecLinter'\n"
        )
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_output)):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.failing_collection_file == (
            "tests/test_spec_linter_pre_spawn_quality_gate.py"
        )

    def test_details_populated(self, tmp_path):
        (tmp_path / "tests").mkdir()
        collect_output = "ERROR collecting tests/test_bad.py\nsome detail\n"
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_output)):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert "ERROR" in result.collection_error_details.upper()

    def test_writes_unstable_marker_file(self, tmp_path):
        (tmp_path / "tests").mkdir()
        collect_output = "ERROR collecting tests/test_bad.py\n"
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_output)):
            collect_and_capture(tmp_path, test_dir="tests")
        assert (tmp_path / _UNSTABLE_MARKER).exists()

    def test_is_baseline_unstable_returns_true_after_abort(self, tmp_path):
        (tmp_path / "tests").mkdir()
        collect_output = "ERROR collecting tests/test_bad.py\n"
        with patch("subprocess.run", return_value=_fake_proc(2, stdout=collect_output)):
            collect_and_capture(tmp_path, test_dir="tests")
        assert is_baseline_unstable(tmp_path) is True


# ---------------------------------------------------------------------------
# Clean collection → ok status + snapshot
# ---------------------------------------------------------------------------

class TestCleanCollectionReturnsOk:
    """collect_and_capture must return status="ok" when collection is clean."""

    def test_returns_ok_status(self, tmp_path):
        (tmp_path / "tests").mkdir()
        clean_output = "<Module tests/test_ok.py>\n  <Function test_something>\n"
        fake_snapshot = {"tests/test_ok.py::test_something": True}
        with (
            patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)),
            patch(
                "bob3.verifier.baseline_capture._capture_snapshot",
                return_value=fake_snapshot,
            ),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.status == "ok"

    def test_snapshot_populated_on_ok(self, tmp_path):
        (tmp_path / "tests").mkdir()
        clean_output = ""
        fake_snapshot = {"tests/test_foo.py::test_bar": True}
        with (
            patch("subprocess.run", return_value=_fake_proc(0, stdout=clean_output)),
            patch(
                "bob3.verifier.baseline_capture._capture_snapshot",
                return_value=fake_snapshot,
            ),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.snapshot == fake_snapshot

    def test_no_failing_file_on_ok(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with (
            patch("subprocess.run", return_value=_fake_proc(0, stdout="")),
            patch("bob3.verifier.baseline_capture._capture_snapshot", return_value={}),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.failing_collection_file is None

    def test_clears_stale_marker_on_clean(self, tmp_path):
        (tmp_path / "tests").mkdir()
        # Pre-place a stale marker.
        (tmp_path / _UNSTABLE_MARKER).write_text("stale\n")
        with (
            patch("subprocess.run", return_value=_fake_proc(0, stdout="")),
            patch("bob3.verifier.baseline_capture._capture_snapshot", return_value={}),
        ):
            collect_and_capture(tmp_path, test_dir="tests")
        assert not (tmp_path / _UNSTABLE_MARKER).exists()


# ---------------------------------------------------------------------------
# abort_on_collect_error — direct function tests
# ---------------------------------------------------------------------------

class TestAbortOnCollectError:
    """abort_on_collect_error raises BaselineUnstableError on collection failure."""

    def test_raises_baseline_unstable_error_on_failure(self):
        result = CollectResult(ok=False, failing_files=["tests/test_bad.py"])
        with pytest.raises(BaselineUnstableError):
            abort_on_collect_error(result)

    def test_error_message_contains_collect(self):
        result = CollectResult(ok=False, failing_files=["tests/test_bad.py"])
        with pytest.raises(BaselineUnstableError, match="collect"):
            abort_on_collect_error(result)

    def test_error_message_names_failing_file(self):
        result = CollectResult(
            ok=False,
            failing_files=["tests/test_property_based_test_generator_hypothesis_ears.py"],
        )
        with pytest.raises(BaselineUnstableError) as exc_info:
            abort_on_collect_error(result)
        assert "test_property_based_test_generator_hypothesis_ears" in str(exc_info.value)

    def test_does_not_raise_on_clean(self):
        result = CollectResult(ok=True, failing_files=[])
        abort_on_collect_error(result)  # must not raise

    def test_error_message_contains_collect_when_no_file_named(self):
        result = CollectResult(ok=False, failing_files=[])
        with pytest.raises(BaselineUnstableError, match="collect"):
            abort_on_collect_error(result)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_none_workspace_returns_ok(self):
        result = collect_and_capture(None)
        assert result.status == "ok"
        assert result.snapshot is None

    def test_missing_workspace_returns_ok(self, tmp_path):
        result = collect_and_capture(tmp_path / "nonexistent")
        assert result.status == "ok"

    def test_missing_test_dir_returns_ok(self, tmp_path):
        result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.status == "ok"

    def test_is_baseline_unstable_false_when_no_marker(self, tmp_path):
        assert is_baseline_unstable(tmp_path) is False

    def test_result_is_dataclass(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with (
            patch("subprocess.run", return_value=_fake_proc(0, stdout="")),
            patch("bob3.verifier.baseline_capture._capture_snapshot", return_value=None),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert isinstance(result, BaselineCaptureResult)
