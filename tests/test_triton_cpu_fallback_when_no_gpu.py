"""Tests for CPU fallback behavior when no GPU accelerator is visible."""

from __future__ import annotations

import types

import pytest
import bob.implementers.triton_kernel as tk
from bob.implementers.triton_kernel import AutotuneResult


class TestCpuFallbackWhenNoGpu:
    def test_hardware_fallback_order_ends_with_triton_cpu(self):
        order = tk.hardware_fallback_order()
        assert order[-1] == "Triton-CPU"

    def test_hardware_fallback_order_is_tuple(self):
        assert isinstance(tk.hardware_fallback_order(), tuple)

    def test_autotune_returns_triton_cpu_when_forced(self):
        result = tk.autotune_kernel(None, hardware_label="Triton-CPU")
        assert result.hardware_label == "Triton-CPU"

    def test_handle_no_accelerator_sets_status_ready(self):
        feature = types.SimpleNamespace(status="pending", halt_reason=None)
        tk.handle_no_accelerator(feature)
        assert feature.status == "ready"

    def test_handle_no_accelerator_sets_halt_reason(self):
        feature = types.SimpleNamespace(status="pending", halt_reason=None)
        tk.handle_no_accelerator(feature)
        assert feature.halt_reason == "no_accelerator_visible"

    def test_handle_no_accelerator_works_without_halt_reason_attr(self):
        feature = types.SimpleNamespace(status="pending")
        tk.handle_no_accelerator(feature)
        assert feature.status == "ready"

    def test_autotune_succeeds_without_gpu(self):
        result = tk.autotune_kernel(None)
        assert isinstance(result, AutotuneResult)
        assert len(result.all_timings) > 0

    def test_verify_numerical_works_without_gpu(self):
        from bob.implementers.triton_kernel import verify_numerical, NumericalReport
        report = verify_numerical([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert isinstance(report, NumericalReport)
        assert report.max_abs_err == pytest.approx(0.0, abs=1e-10)
