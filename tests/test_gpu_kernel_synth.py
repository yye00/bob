"""Tests for hippy.gpu_kernel_synth — Triton kernel synthesis + autotune sub-agent.

Covers the two public functions required by the feature acceptance criteria:

- ``synthesize_triton_kernel``: generate a ``@triton.jit`` kernel source.
- ``autotune_and_verify``: sweep the autotune grid, pick the winner, persist
  it, and gate on numerical correctness against a CPU reference.
"""

from __future__ import annotations

import pytest

from hippy.gpu_kernel_synth import autotune_and_verify, synthesize_triton_kernel


class TestSynthesizeTritonKernel:
    def test_returns_nonempty_source(self):
        src = synthesize_triton_kernel("row-wise softmax over a 2-D float32 tensor")
        assert isinstance(src, str)
        assert len(src) > 0

    def test_source_contains_triton_jit_decorator(self):
        src = synthesize_triton_kernel("elementwise add")
        assert "@triton.jit" in src

    def test_source_contains_autotune_over_block_axes(self):
        src = synthesize_triton_kernel("matmul")
        assert "@triton.autotune" in src
        for axis in ("BLOCK_M", "BLOCK_N", "BLOCK_K", "num_warps", "num_stages"):
            assert axis in src

    def test_custom_kernel_name_appears(self):
        src = synthesize_triton_kernel("relu", kernel_name="my_relu")
        assert "my_relu" in src

    def test_empty_spec_raises_value_error(self):
        with pytest.raises(ValueError):
            synthesize_triton_kernel("")

    def test_non_string_spec_raises(self):
        with pytest.raises((ValueError, TypeError)):
            synthesize_triton_kernel(123)  # type: ignore[arg-type]


class TestAutotuneAndVerify:
    def test_returns_expected_keys(self):
        result = autotune_and_verify("test-feat", "softmax")
        assert isinstance(result, dict)
        for key in (
            "best_config",
            "all_timings",
            "hardware_label",
            "numerical_report",
            "passed_gate",
            "config_path",
        ):
            assert key in result

    def test_best_config_covers_sweep_axes(self):
        result = autotune_and_verify("test-feat", "matmul")
        assert isinstance(result["best_config"], dict)
        assert result["best_config"]  # non-empty

    def test_passes_gate_with_matching_outputs(self):
        result = autotune_and_verify(
            "test-feat",
            "add",
            kernel_output=[1.0, 2.0, 3.0],
            reference_output=[1.0, 2.0, 3.0],
        )
        assert result["passed_gate"] is True

    def test_fails_gate_with_divergent_outputs(self):
        result = autotune_and_verify(
            "test-feat",
            "add",
            kernel_output=[1.0, 2.0, 3.0],
            reference_output=[100.0, 200.0, 300.0],
        )
        assert result["passed_gate"] is False

    def test_persists_config_to_disk(self, tmp_path):
        result = autotune_and_verify("feat-persist", "softmax", runs_root=tmp_path)
        assert result["config_path"] is not None
        from pathlib import Path

        assert Path(result["config_path"]).exists()

    def test_custom_sweep_space_honored(self):
        space = {"BLOCK_M": [16], "BLOCK_N": [16], "BLOCK_K": [16]}
        result = autotune_and_verify("feat", "add", sweep_space=space)
        assert len(result["all_timings"]) == 1

    def test_invalid_sweep_space_raises(self):
        with pytest.raises(ValueError):
            autotune_and_verify("feat", "add", sweep_space="BLOCK_M=16")  # type: ignore[arg-type]

    def test_empty_spec_raises(self):
        with pytest.raises(ValueError):
            autotune_and_verify("feat", "")

    def test_non_string_feature_id_raises(self):
        with pytest.raises((ValueError, TypeError)):
            autotune_and_verify(None, "add")  # type: ignore[arg-type]


class TestImplementerIntegration:
    def test_implementer_exposes_router(self):
        from hippy import implementer

        assert hasattr(implementer, "maybe_route_gpu_feature")

    def test_router_routes_gpu_ac(self):
        from hippy import implementer

        result = implementer.maybe_route_gpu_feature(
            feature_id="feat-gpu",
            ac_text="Write a @triton.jit matmul kernel on CUDA",
            spec="matmul",
        )
        assert result is not None
        assert result["routed"] is True
        assert "kernel_source" in result

    def test_router_skips_non_gpu_ac(self):
        from hippy import implementer

        result = implementer.maybe_route_gpu_feature(
            feature_id="feat-cpu",
            ac_text="Add two integers and return the sum",
            spec="add",
        )
        assert result is None
