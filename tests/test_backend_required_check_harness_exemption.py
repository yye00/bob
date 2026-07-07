"""Feature c28dbe93: backend-required check MUST exempt harness features.

A test-infrastructure feature legitimately writes no device code even when
its description mentions GPU concepts. It must be classified as harness and
exempted from the backend-required gate. The inverse of F-R7-640: naming the
backend is not the same as using it.
"""

import pytest

from hippy.backend_required_check import (
    is_harness_feature,
    backend_required_check,
)


class TestIsHarnessFeature:
    def test_test_port_title_is_harness(self):
        assert is_harness_feature(
            "Curated upstream test port + xfail taxonomy for numpy/scipy"
        ) is True

    def test_xfail_taxonomy_is_harness(self):
        assert is_harness_feature(
            "Build an xfail taxonomy ratchet for the conftest suite"
        ) is True

    def test_plain_compute_feature_is_not_harness(self):
        assert is_harness_feature(
            "Implement hipblasSgemm matmul kernel on the device"
        ) is False

    def test_harness_marker_wins_over_incidental_compute_word(self):
        # A test-port feature that PORTS numpy tests exercising matmul/fft is
        # still harness — it writes no device code itself.
        assert is_harness_feature(
            "Upstream test port for the linalg matmul and fft ufunc paths"
        ) is True

    def test_harness_via_description_when_title_terse(self):
        assert is_harness_feature(
            "Ratchet",
            description="Establish an xfail taxonomy and pass-rate ratchet",
        ) is True


class TestBackendRequiredCheck:
    def test_harness_feature_not_gated(self):
        result = backend_required_check(
            "Curated upstream test port + xfail taxonomy"
        )
        assert result["is_harness"] is True
        assert result["backend_required"] is False

    def test_compute_feature_is_gated(self):
        result = backend_required_check(
            "Implement hipblasSgemm matmul kernel"
        )
        assert result["is_harness"] is False
        assert result["backend_required"] is True

    def test_boundary_both_harness_and_kernel_still_gated_when_no_harness_marker(self):
        # A clearly-compute title with no harness marker gets checked.
        result = backend_required_check(
            "Elementwise reduction kernel via hiprtc"
        )
        assert result["backend_required"] is True

    def test_bare_hip_mention_is_not_compute_intent(self):
        # "hip" / "device" as incidental tokens must NOT trigger the gate.
        result = backend_required_check(
            "Documentation update referencing the hip device model"
        )
        assert result["is_harness"] is False
        assert result["backend_required"] is False

    def test_returns_reason_string(self):
        result = backend_required_check("Build a conftest import guard")
        assert isinstance(result["reason"], str)
        assert result["reason"]
