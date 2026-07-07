"""Error-path tests: invalid input raises ValueError and the function does not
silently succeed (feature d6497bed)."""

from __future__ import annotations

import pytest

from bob.backend_required_check import check_backend_required


COMPUTE_FEATURE = {
    "name": "GPU kernel",
    "description": "A HIP GPU matmul kernel.",
    "acceptance_criteria": [],
}


def test_non_mapping_feature_raises():
    with pytest.raises(ValueError):
        check_backend_required("not a mapping", [])


def test_none_feature_raises():
    with pytest.raises(ValueError):
        check_backend_required(None, [])


def test_single_path_string_as_src_files_raises(monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    # A bare string is a common mistake — must not be silently treated as an
    # iterable of characters.
    with pytest.raises(ValueError):
        check_backend_required(COMPUTE_FEATURE, "src/kernel.py")


def test_non_iterable_src_files_raises(monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    with pytest.raises(ValueError):
        check_backend_required(COMPUTE_FEATURE, 42)


def test_non_path_entry_raises(monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    with pytest.raises(ValueError):
        check_backend_required(COMPUTE_FEATURE, [123])


def test_unsupported_backend_raises():
    with pytest.raises(ValueError):
        check_backend_required(COMPUTE_FEATURE, [], backend="opencl")


def test_error_not_silently_swallowed(monkeypatch):
    monkeypatch.setenv("BOB_REQUIRE_GPU_BACKEND", "1")
    # Confirm the invalid call raises rather than returning a passing result.
    raised = False
    try:
        check_backend_required(COMPUTE_FEATURE, 3.14)
    except ValueError:
        raised = True
    assert raised is True
