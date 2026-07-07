"""Tests for hippy.verifier backend-required scoping + simulation rejection.

Feature 91fee1a2: the backend-required check must (a) scope its source scan to
the feature's OWN recently-modified files (not the cumulative src tree) and
(b) FAIL on simulation-admission markers even when a real backend reference is
also present. Harness/test-infra features remain exempt.
"""

from __future__ import annotations

import pathlib

import pytest

from hippy.verifier import (
    backend_required_check,
    has_simulation_admission,
    scope_to_modified_files,
)


# --------------------------------------------------------------------------
# has_simulation_admission
# --------------------------------------------------------------------------
def test_has_simulation_admission_detects_simulated_device_memory():
    assert has_simulation_admission("pool of 4 GiB simulated device memory") is True


def test_has_simulation_admission_detects_in_a_real_gpu_admission():
    txt = "in a real GPU implementation each Stream would wrap a hipStream_t; here it does not"
    assert has_simulation_admission(txt) is True


def test_has_simulation_admission_is_case_insensitive():
    assert has_simulation_admission("SIMULATED GPU device") is True


def test_has_simulation_admission_false_for_real_code():
    txt = "from hip import hip\nhip.hipMalloc(nbytes)\nhipModuleLaunchKernel(...)"
    assert has_simulation_admission(txt) is False


def test_has_simulation_admission_empty_string_is_false():
    assert has_simulation_admission("") is False


# --------------------------------------------------------------------------
# backend_required_check — simulation rejection even with real reference
# --------------------------------------------------------------------------
def test_check_fails_on_simulation_even_with_real_backend_reference(tmp_path):
    f = tmp_path / "stream.py"
    f.write_text(
        "from hip import hip\n"
        "def launch():\n"
        "    hip.hipModuleLaunchKernel(mod)\n"
        "# in a real GPU implementation each Stream would wrap a hipStream_t; here it does not\n"
    )
    result = backend_required_check([f])
    assert result["passed"] is False
    assert "simulation" in result["reason"].lower()


def test_check_passes_when_only_real_backend_and_no_simulation(tmp_path):
    f = tmp_path / "gemm.py"
    f.write_text(
        "from hip import hip\n"
        "def gemm():\n"
        "    hip.hipMalloc(n)\n"
        "    hipblasSgemm(handle)\n"
    )
    result = backend_required_check([f])
    assert result["passed"] is True


def test_check_fails_when_no_file_references_backend(tmp_path):
    f = tmp_path / "fake.py"
    f.write_text("def add(a, b):\n    return a + b\n")
    result = backend_required_check([f])
    assert result["passed"] is False
    assert "backend" in result["reason"].lower()


# --------------------------------------------------------------------------
# scoping: only judge the feature's own files, not the cumulative src tree
# --------------------------------------------------------------------------
def test_check_scoped_to_own_files_ignores_earlier_facade(tmp_path):
    # An earlier feature's real HIP facade exists in the tree...
    facade = tmp_path / "hip_facade.py"
    facade.write_text("from hip import hip\nhip.hipMalloc(1)\nhipModuleLaunchKernel(m)\n")
    # ...but THIS feature only wrote a pure-Python fake.
    my_fake = tmp_path / "my_new_module.py"
    my_fake.write_text("def compute():\n    return sum(range(10))\n")
    # Judged on its OWN file only -> must FAIL (no backend reference of its own).
    result = backend_required_check([my_fake])
    assert result["passed"] is False


def test_check_harness_feature_is_exempt(tmp_path):
    f = tmp_path / "conftest_helper.py"
    f.write_text("def add(a, b):\n    return a + b\n")
    result = backend_required_check([f], is_harness=True)
    assert result["passed"] is True


# --------------------------------------------------------------------------
# scope_to_modified_files — mtime window with full-scan fallback
# --------------------------------------------------------------------------
def test_scope_to_modified_files_selects_recent(tmp_path):
    import os
    import time

    old = tmp_path / "old.py"
    old.write_text("x = 1\n")
    new = tmp_path / "new.py"
    new.write_text("y = 2\n")
    start = time.time()
    # Backdate old well before the window; touch new after start.
    os.utime(old, (start - 10_000, start - 10_000))
    os.utime(new, (start + 5, start + 5))
    selected = scope_to_modified_files([old, new], feature_start_time=start)
    assert new in selected
    assert old not in selected


def test_scope_to_modified_files_full_scan_fallback_when_empty(tmp_path):
    import os
    import time

    a = tmp_path / "a.py"
    a.write_text("x = 1\n")
    b = tmp_path / "b.py"
    b.write_text("y = 2\n")
    future = time.time() + 100_000  # nothing is newer than this
    os.utime(a, (future - 200_000, future - 200_000))
    os.utime(b, (future - 200_000, future - 200_000))
    # Window yields nothing -> fall back to the full list.
    selected = scope_to_modified_files([a, b], feature_start_time=future)
    assert set(selected) == {a, b}
