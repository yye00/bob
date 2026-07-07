"""Tests for the C++/GPU characterization harness (feature fd0d64e2).

BF-6 snapshots a Python target by diffing stdout/return values. It cannot
observe a compiled C++ collective, and bitwise diffs are meaningless across GPU
reductions. This harness instead:

  1. Observer phase (:func:`capture_gpu_golden`) — builds/runs a driver or an
     rccl-tests binary against fixed inputs and captures a golden artifact:
     reduced-buffer contents, validation pass/fail, and the error bound.
  2. Verifier phase (:func:`verify_gpu_golden`) — rebuilds, re-runs, and
     compares results with a numeric TOLERANCE rather than a byte diff, and
     requires the run to have actually dispatched a device kernel (tying into
     the dispatch-coupled anti-cheat) so a host-side shortcut cannot fake a
     passing snapshot.
"""

from __future__ import annotations

import json

import pytest

from bob.cpp_gpu_characterization_harness import (
    CaptureResult,
    GpuGoldenSpec,
    GpuRunResult,
    VerifyResult,
    capture_gpu_golden,
    verify_gpu_golden,
)
from hippy.dispatch_facade import dispatch_launch, reset_launch_ledger


@pytest.fixture(autouse=True)
def _clean_ledger():
    reset_launch_ledger()
    yield
    reset_launch_ledger()


def _dispatching_runner(buffer, *, validation_passed=True, error_bound=1e-6):
    """A runner that performs a real (fake) device dispatch through the facade.

    The device kernel launch is routed through :func:`dispatch_launch` so the
    harness observes a genuine launch-ledger advance — exactly what the
    dispatch-coupled anti-cheat requires.
    """

    def _runner():
        dispatch_launch("hipModuleLaunchKernel", lambda: None)
        return GpuRunResult(
            reduced_buffer=list(buffer),
            validation_passed=validation_passed,
            error_bound=error_bound,
        )

    return _runner


def _host_only_runner(buffer):
    """A cheating runner that computes on the host and never dispatches."""

    def _runner():
        return GpuRunResult(reduced_buffer=list(buffer), validation_passed=True)

    return _runner


# ---------------------------------------------------------------------------
# Observer phase: capture_gpu_golden
# ---------------------------------------------------------------------------


def test_capture_writes_golden_under_snapshot_dir(tmp_path):
    spec = GpuGoldenSpec(name="allreduce_sum", snapshot_dir="snaps/fd0", tolerance=1e-5)
    result = capture_gpu_golden(
        spec, _dispatching_runner([1.0, 2.0, 3.0]), workspace=tmp_path
    )
    assert isinstance(result, CaptureResult)
    assert result.success is True
    assert result.golden_path.exists()
    # Golden lives under the feature snapshot_dir so the disk-reconciler treats
    # it as a satisfaction artifact.
    assert (tmp_path / "snaps" / "fd0") in result.golden_path.parents
    payload = json.loads(result.golden_path.read_text())
    assert payload["reduced_buffer"] == [1.0, 2.0, 3.0]
    assert payload["validation_passed"] is True


def test_capture_requires_a_device_dispatch(tmp_path):
    """A host-only run captured no launch evidence — capture must not succeed."""
    spec = GpuGoldenSpec(name="host_cheat", snapshot_dir="snaps", tolerance=1e-5)
    result = capture_gpu_golden(spec, _host_only_runner([1.0]), workspace=tmp_path)
    assert result.success is False
    assert "dispatch" in result.details.lower()


# ---------------------------------------------------------------------------
# Verifier phase: verify_gpu_golden
# ---------------------------------------------------------------------------


def test_verify_passes_when_within_tolerance(tmp_path):
    spec = GpuGoldenSpec(name="allreduce", snapshot_dir="snaps", tolerance=1e-3)
    capture_gpu_golden(spec, _dispatching_runner([1.0, 2.0, 3.0]), workspace=tmp_path)
    # Re-run drifts slightly but within tolerance — allowed for GPU reductions.
    result = verify_gpu_golden(
        spec, _dispatching_runner([1.0005, 2.0005, 2.9995]), workspace=tmp_path
    )
    assert isinstance(result, VerifyResult)
    assert result.passed is True


def test_verify_fails_when_drift_exceeds_tolerance(tmp_path):
    spec = GpuGoldenSpec(name="allreduce", snapshot_dir="snaps", tolerance=1e-4)
    capture_gpu_golden(spec, _dispatching_runner([1.0, 2.0, 3.0]), workspace=tmp_path)
    result = verify_gpu_golden(
        spec, _dispatching_runner([1.5, 2.0, 3.0]), workspace=tmp_path
    )
    assert result.passed is False
    assert "toler" in result.details.lower() or "drift" in result.details.lower()


def test_verify_fails_on_correctness_regression(tmp_path):
    spec = GpuGoldenSpec(name="allreduce", snapshot_dir="snaps", tolerance=1e-3)
    capture_gpu_golden(spec, _dispatching_runner([1.0], validation_passed=True), workspace=tmp_path)
    result = verify_gpu_golden(
        spec, _dispatching_runner([1.0], validation_passed=False), workspace=tmp_path
    )
    assert result.passed is False
    assert "correct" in result.details.lower() or "valid" in result.details.lower()


def test_verify_fails_when_no_device_kernel_dispatched(tmp_path):
    """A host-side shortcut in the verifier phase cannot fake a pass."""
    spec = GpuGoldenSpec(name="allreduce", snapshot_dir="snaps", tolerance=1e-3)
    capture_gpu_golden(spec, _dispatching_runner([1.0, 2.0]), workspace=tmp_path)
    result = verify_gpu_golden(spec, _host_only_runner([1.0, 2.0]), workspace=tmp_path)
    assert result.passed is False
    assert "dispatch" in result.details.lower() or "kernel" in result.details.lower()


def test_verify_fails_when_golden_missing(tmp_path):
    spec = GpuGoldenSpec(name="never_captured", snapshot_dir="snaps", tolerance=1e-3)
    result = verify_gpu_golden(spec, _dispatching_runner([1.0]), workspace=tmp_path)
    assert result.passed is False
    assert "golden" in result.details.lower() or "observer" in result.details.lower()


def test_verify_respects_error_bound(tmp_path):
    spec = GpuGoldenSpec(name="allreduce", snapshot_dir="snaps", tolerance=1e-3, max_error_bound=1e-2)
    capture_gpu_golden(
        spec, _dispatching_runner([1.0], error_bound=1e-6), workspace=tmp_path
    )
    # Error bound blows past the allowed maximum → fail even if buffer matches.
    result = verify_gpu_golden(
        spec, _dispatching_runner([1.0], error_bound=1.0), workspace=tmp_path
    )
    assert result.passed is False


# ---------------------------------------------------------------------------
# Integration with the characterization module
# ---------------------------------------------------------------------------


def test_integration_characterization_module_importable():
    import bob.acceptance.characterization as characterization

    assert hasattr(characterization, "CharacterizationAC")
