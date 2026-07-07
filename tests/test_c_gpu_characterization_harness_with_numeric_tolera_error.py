"""Error-path tests (feature fd0d64e2).

Invalid input raises ValueError and the function does not silently succeed.
"""

from __future__ import annotations

import pytest

from bob.cpp_gpu_characterization_harness import (
    GpuGoldenSpec,
    GpuRunResult,
    capture_gpu_golden,
    verify_gpu_golden,
)
from hippy.dispatch_facade import dispatch_launch, reset_launch_ledger


@pytest.fixture(autouse=True)
def _clean_ledger():
    reset_launch_ledger()
    yield
    reset_launch_ledger()


def _dispatching_runner(buffer):
    def _runner():
        dispatch_launch("hipModuleLaunchKernel", lambda: None)
        return GpuRunResult(reduced_buffer=list(buffer), validation_passed=True)

    return _runner


def test_spec_with_empty_name_raises(tmp_path):
    with pytest.raises(ValueError):
        GpuGoldenSpec(name="", snapshot_dir="snaps", tolerance=1e-6)


def test_spec_with_empty_snapshot_dir_raises(tmp_path):
    with pytest.raises(ValueError):
        GpuGoldenSpec(name="x", snapshot_dir="", tolerance=1e-6)


def test_negative_tolerance_raises(tmp_path):
    with pytest.raises(ValueError):
        GpuGoldenSpec(name="x", snapshot_dir="snaps", tolerance=-1.0)


def test_capture_with_non_spec_raises(tmp_path):
    with pytest.raises(ValueError):
        capture_gpu_golden("not-a-spec", _dispatching_runner([1.0]), workspace=tmp_path)


def test_capture_with_non_callable_runner_raises(tmp_path):
    spec = GpuGoldenSpec(name="x", snapshot_dir="snaps", tolerance=1e-6)
    with pytest.raises(ValueError):
        capture_gpu_golden(spec, "not-callable", workspace=tmp_path)


def test_verify_with_non_spec_raises(tmp_path):
    with pytest.raises(ValueError):
        verify_gpu_golden(123, _dispatching_runner([1.0]), workspace=tmp_path)


def test_verify_with_non_callable_runner_raises(tmp_path):
    spec = GpuGoldenSpec(name="x", snapshot_dir="snaps", tolerance=1e-6)
    with pytest.raises(ValueError):
        verify_gpu_golden(spec, None, workspace=tmp_path)


def test_runner_returning_wrong_type_raises(tmp_path):
    spec = GpuGoldenSpec(name="x", snapshot_dir="snaps", tolerance=1e-6)

    def _bad_runner():
        dispatch_launch("hipModuleLaunchKernel", lambda: None)
        return {"reduced_buffer": [1.0]}  # not a GpuRunResult

    with pytest.raises(ValueError):
        capture_gpu_golden(spec, _bad_runner, workspace=tmp_path)
