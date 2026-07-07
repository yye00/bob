"""Tests for the opt-in backend-required check (feature d6497bed)."""

from __future__ import annotations

import pytest

from bob.backend_required_check import (
    BackendCheckResult,
    check_backend_required,
)


COMPUTE_FEATURE = {
    "name": "GPU matmul ufunc",
    "description": "Implement a HIP GPU matmul kernel for the linalg module.",
    "acceptance_criteria": ["pytest: tests/test_matmul.py"],
}

HARNESS_FEATURE = {
    "name": "Rename config flag",
    "description": "Bookkeeping: rename a config default and update docs.",
    "acceptance_criteria": ["pytest: tests/test_config.py"],
}


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_disabled_by_default_passes(tmp_path, monkeypatch):
    monkeypatch.delenv("BOB_REQUIRE_GPU_BACKEND", raising=False)
    src = _write(tmp_path, "kern.py", "x = [1, 2, 3]  # pure python\n")
    res = check_backend_required(COMPUTE_FEATURE, [src])
    assert res.passed is True
    assert res.status == "disabled"
    assert res.enabled is False


def test_enabled_compute_missing_backend_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    # Pure-python "simulated GPU" — HIP only in a docstring.
    src = _write(
        tmp_path,
        "device.py",
        '"""Simulated GPU using HIP."""\n'
        "class DeviceArray:\n"
        "    def __init__(self, data):\n"
        "        self._data = list(data)\n"
        "        self._launch_log = []\n",
    )
    res = check_backend_required(COMPUTE_FEATURE, [src])
    assert res.passed is False
    assert res.status == "backend_missing"
    assert res.is_compute is True
    assert "must use the 'hip' backend" in res.reason
    assert str(src) in res.offending_files


def test_enabled_compute_with_real_backend_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "true")
    src = _write(
        tmp_path,
        "real_kernel.py",
        "from hip import hip, hiprtc\n"
        "def launch():\n"
        "    hip.hipMalloc(1024)\n",
    )
    res = check_backend_required(COMPUTE_FEATURE, [src])
    assert res.passed is True
    assert res.status == "ok"
    assert str(src) in res.matched_files


def test_enabled_harness_feature_exempt(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    src = _write(tmp_path, "conf.py", "DEFAULT = 'x'\n")
    res = check_backend_required(HARNESS_FEATURE, [src])
    assert res.passed is True
    assert res.status == "exempt"
    assert res.is_compute is False


def test_global_kernel_marker_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "on")
    src = _write(
        tmp_path,
        "kernel.cpp",
        '__global__ void add(float* a) { a[0] += 1; }\n',
    )
    res = check_backend_required(COMPUTE_FEATURE, [src])
    assert res.passed is True
    assert res.status == "ok"


def test_workspace_relative_paths_resolved(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    (tmp_path / "src").mkdir()
    _write(tmp_path, "src/k.py", "import hip\n")
    res = check_backend_required(
        COMPUTE_FEATURE, ["src/k.py"], workspace=tmp_path
    )
    assert res.passed is True
    assert res.status == "ok"


def test_multiple_files_one_matches_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    a = _write(tmp_path, "a.py", "x = 1\n")
    b = _write(tmp_path, "b.py", "hipblas_sgemm()\n")
    res = check_backend_required(COMPUTE_FEATURE, [a, b])
    assert res.passed is True
    assert str(b) in res.matched_files
    assert str(a) in res.offending_files


def test_result_is_dataclass_and_truthy(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    src = _write(tmp_path, "k.py", "from hip import hip\n")
    res = check_backend_required(COMPUTE_FEATURE, [src])
    assert isinstance(res, BackendCheckResult)
    assert bool(res) is True


def test_reason_always_nonempty():
    res = check_backend_required(COMPUTE_FEATURE, None)
    assert res.reason


def test_unsupported_backend_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    with pytest.raises(ValueError):
        check_backend_required(COMPUTE_FEATURE, [], backend="cuda-fake")


def test_integration_reexport_from_verification():
    from bob.verification import check_backend_required as reexported

    assert reexported is check_backend_required
