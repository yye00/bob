"""Boundary-case tests (feature fd0d64e2).

Empty, zero, or minimum input returns a well-defined result rather than raising.
"""

from __future__ import annotations

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


def _dispatching_runner(buffer, *, validation_passed=True, error_bound=0.0):
    def _runner():
        dispatch_launch("hipLaunchKernel", lambda: None)
        return GpuRunResult(
            reduced_buffer=list(buffer),
            validation_passed=validation_passed,
            error_bound=error_bound,
        )

    return _runner


def test_empty_buffer_captures_well_defined_golden(tmp_path):
    """An empty reduced buffer is a valid minimum input, not an error."""
    spec = GpuGoldenSpec(name="empty", snapshot_dir="snaps", tolerance=1e-6)
    result = capture_gpu_golden(spec, _dispatching_runner([]), workspace=tmp_path)
    assert isinstance(result, CaptureResult)
    assert result.success is True
    assert result.golden_path.exists()


def test_empty_buffer_verifies_against_empty_golden(tmp_path):
    spec = GpuGoldenSpec(name="empty", snapshot_dir="snaps", tolerance=1e-6)
    capture_gpu_golden(spec, _dispatching_runner([]), workspace=tmp_path)
    result = verify_gpu_golden(spec, _dispatching_runner([]), workspace=tmp_path)
    assert isinstance(result, VerifyResult)
    assert result.passed is True


def test_zero_valued_buffer_is_well_defined(tmp_path):
    spec = GpuGoldenSpec(name="zeros", snapshot_dir="snaps", tolerance=1e-6)
    capture_gpu_golden(spec, _dispatching_runner([0.0, 0.0]), workspace=tmp_path)
    result = verify_gpu_golden(spec, _dispatching_runner([0.0, 0.0]), workspace=tmp_path)
    assert result.passed is True


def test_zero_tolerance_requires_exact_match(tmp_path):
    """A zero tolerance is a well-defined boundary: exact match passes."""
    spec = GpuGoldenSpec(name="exact", snapshot_dir="snaps", tolerance=0.0)
    capture_gpu_golden(spec, _dispatching_runner([1.0]), workspace=tmp_path)
    result = verify_gpu_golden(spec, _dispatching_runner([1.0]), workspace=tmp_path)
    assert result.passed is True


def test_single_element_buffer_minimum_input(tmp_path):
    spec = GpuGoldenSpec(name="single", snapshot_dir="snaps", tolerance=1e-6)
    capture_gpu_golden(spec, _dispatching_runner([42.0]), workspace=tmp_path)
    result = verify_gpu_golden(spec, _dispatching_runner([42.0]), workspace=tmp_path)
    assert result.passed is True
