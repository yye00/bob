"""Tests for bob3.verifier.baseline_capture — regression guard.

Verifies that when the baseline is unstable:
- No feature is demoted to regression via db.detect_regression.
- The orchestrator must skip detect_regression when collect_and_capture
  returns baseline_unstable (the contract enforced by this module).
- The is_baseline_unstable sentinel correctly signals the guard condition.
"""
from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest

from bob3.verifier.baseline_capture import (
    BaselineCaptureResult,
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


def _unstable_result(failing_file: str = "tests/test_bad.py") -> BaselineCaptureResult:
    return BaselineCaptureResult(
        status="baseline_unstable",
        snapshot=None,
        failing_collection_file=failing_file,
        collection_error_details="ERROR collecting " + failing_file,
    )


def _ok_result(snapshot: dict | None = None) -> BaselineCaptureResult:
    return BaselineCaptureResult(status="ok", snapshot=snapshot or {})


# ---------------------------------------------------------------------------
# Regression guard contract tests
# ---------------------------------------------------------------------------

class TestNoRegressionOnUnstableBaseline:
    """The caller must not invoke detect_regression when baseline is unstable."""

    def test_unstable_result_has_none_snapshot(self, tmp_path):
        """baseline_unstable result snapshot is None — caller cannot diff."""
        (tmp_path / "tests").mkdir()
        with patch(
            "subprocess.run",
            return_value=_fake_proc(2, stdout="ERROR collecting tests/test_bad.py\n"),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.snapshot is None, (
            "Caller must not use snapshot for regression diff when status is baseline_unstable"
        )

    def test_unstable_status_is_not_ok(self, tmp_path):
        (tmp_path / "tests").mkdir()
        with patch(
            "subprocess.run",
            return_value=_fake_proc(2, stdout="ERROR collecting tests/test_bad.py\n"),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")
        assert result.status != "ok"

    def test_guard_logic_skips_detect_regression(self, tmp_path):
        """Simulate the orchestrator guard: detect_regression is NOT called when
        collect_and_capture returns baseline_unstable."""
        (tmp_path / "tests").mkdir()
        mock_detect = MagicMock(return_value=None)

        with patch(
            "subprocess.run",
            return_value=_fake_proc(2, stdout="ERROR collecting tests/test_bad.py\n"),
        ):
            before = collect_and_capture(tmp_path, test_dir="tests")

        # Orchestrator guard: only call detect_regression when status == "ok"
        # and snapshot is not None.
        if before.status == "ok" and before.snapshot is not None:
            mock_detect(before_results=before.snapshot, after_results={})

        mock_detect.assert_not_called()

    def test_guard_logic_calls_detect_regression_on_ok(self, tmp_path):
        """Simulate the orchestrator guard: detect_regression IS called when clean."""
        (tmp_path / "tests").mkdir()
        fake_snapshot = {"tests/test_ok.py::test_foo": True}
        mock_detect = MagicMock(return_value=None)

        with (
            patch("subprocess.run", return_value=_fake_proc(0, stdout="")),
            patch(
                "bob3.verifier.baseline_capture._capture_snapshot",
                return_value=fake_snapshot,
            ),
        ):
            before = collect_and_capture(tmp_path, test_dir="tests")

        if before.status == "ok" and before.snapshot is not None:
            mock_detect(before_results=before.snapshot, after_results={"tests/test_ok.py::test_foo": False})

        mock_detect.assert_called_once()

    def test_unstable_marker_blocks_regression_check(self, tmp_path):
        """is_baseline_unstable can be used as an additional guard."""
        (tmp_path / "tests").mkdir()
        # Simulate a prior run that left the marker.
        (tmp_path / _UNSTABLE_MARKER).write_text("baseline_unstable\n")

        mock_detect = MagicMock(return_value=None)

        # Guard: if marker exists, skip regression detection entirely.
        if not is_baseline_unstable(tmp_path):
            mock_detect()

        mock_detect.assert_not_called()

    def test_stable_baseline_does_not_block_regression_check(self, tmp_path):
        """is_baseline_unstable returns False when no marker — guard passes."""
        mock_detect = MagicMock(return_value=None)

        if not is_baseline_unstable(tmp_path):
            mock_detect()

        mock_detect.assert_called_once()

    def test_unrelated_feature_not_demoted(self, tmp_path):
        """When baseline_unstable, the failing_collection_file is correctly
        identified and is NOT the feature being tested (unrelated feature guard)."""
        (tmp_path / "tests").mkdir()
        collect_output = (
            "ERROR collecting tests/test_property_based_test_generator_hypothesis_ears.py\n"
        )
        with patch(
            "subprocess.run",
            return_value=_fake_proc(2, stdout=collect_output),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")

        assert result.status == "baseline_unstable"
        assert result.failing_collection_file == (
            "tests/test_property_based_test_generator_hypothesis_ears.py"
        )
        # The failing file is different from the feature under test —
        # the framework must not attribute this to an unrelated feature.
        feature_under_test = "tests/test_some_new_feature.py"
        assert result.failing_collection_file != feature_under_test


# ---------------------------------------------------------------------------
# Marker lifecycle tests
# ---------------------------------------------------------------------------

class TestMarkerLifecycle:
    def test_marker_persists_across_calls_until_clean(self, tmp_path):
        (tmp_path / "tests").mkdir()
        # First call: unstable.
        with patch(
            "subprocess.run",
            return_value=_fake_proc(2, stdout="ERROR collecting tests/test_bad.py\n"),
        ):
            collect_and_capture(tmp_path, test_dir="tests")

        assert is_baseline_unstable(tmp_path)

        # Second call: clean.
        with (
            patch("subprocess.run", return_value=_fake_proc(0, stdout="")),
            patch("bob3.verifier.baseline_capture._capture_snapshot", return_value={}),
        ):
            result = collect_and_capture(tmp_path, test_dir="tests")

        assert result.status == "ok"
        assert not is_baseline_unstable(tmp_path)

    def test_multiple_unstable_calls_leave_one_marker(self, tmp_path):
        (tmp_path / "tests").mkdir()
        for _ in range(3):
            with patch(
                "subprocess.run",
                return_value=_fake_proc(2, stdout="ERROR collecting tests/test_bad.py\n"),
            ):
                collect_and_capture(tmp_path, test_dir="tests")
        markers = list(tmp_path.glob(_UNSTABLE_MARKER))
        # There should be exactly one marker file (not three).
        assert len(markers) == 1
