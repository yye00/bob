"""Backend-required check exempts harness/test-infrastructure features
(feature f9ecbccb).

The gate false-failed a "curated upstream test port + xfail taxonomy"
feature — test infrastructure that legitimately writes no device code but
whose description mentions GPU concepts. A harness feature must be exempt
even when it also names compute keywords. The inverse: a pure-compute
feature (no harness marker) with a specific compute marker is still gated.
"""

import pytest

from hippy.backend_required_check import (
    is_harness_feature,
    backend_required_check,
)


# --- The motivating case: harness feature that mentions GPU concepts --------

def test_upstream_test_port_is_harness():
    title = "Curated upstream test port + xfail taxonomy"
    assert is_harness_feature(title) is True


def test_harness_feature_mentioning_gpu_is_exempt():
    title = "Curated upstream test port + xfail taxonomy"
    desc = (
        "Ports numpy/scipy tests to HIP and builds an xfail taxonomy for the "
        "kernel and matmul paths that are not yet implemented."
    )
    result = backend_required_check(title, desc)
    assert result["is_harness"] is True
    assert result["backend_required"] is False


@pytest.mark.parametrize(
    "marker",
    [
        "test port", "upstream test", "xfail", "taxonomy", "ratchet",
        "conftest", "anti-cheat", "measurement protocol", "benchmark report",
        "coverage signal", "import guard", "pass-rate", "tolerance policy",
        "dispatch", "protocol", "array-api", "get_array_module",
    ],
)
def test_each_harness_marker_classifies_as_harness(marker):
    assert is_harness_feature(f"Feature about {marker} handling") is True


# --- Compute features (no harness marker) are still gated --------------------

@pytest.mark.parametrize(
    "marker",
    ["kernel", "hiprtc", "ufunc", "matmul", "gemm", "linalg", "fft",
     "reduction", "elementwise", "device-memory"],
)
def test_compute_marker_requires_backend(marker):
    result = backend_required_check(f"Implement {marker} on device")
    assert result["is_harness"] is False
    assert result["backend_required"] is True


def test_harness_marker_wins_over_compute_marker():
    # BOTH harness-ish and names a compute marker → harness wins (exempt).
    result = backend_required_check(
        "xfail taxonomy for the matmul kernel port"
    )
    assert result["is_harness"] is True
    assert result["backend_required"] is False


# --- Bare/incidental tokens must NOT trigger the compute gate ----------------

def test_bare_hip_token_does_not_require_backend():
    result = backend_required_check("Add a hip to the docs about the device")
    assert result["is_harness"] is False
    assert result["backend_required"] is False


def test_incidental_device_mention_not_backend_required():
    result = backend_required_check(
        "Improve logging when the device is unavailable"
    )
    assert result["backend_required"] is False


# --- Shape / reason ---------------------------------------------------------

def test_result_has_reason_string():
    result = backend_required_check("kernel launch")
    assert isinstance(result["reason"], str) and result["reason"]
