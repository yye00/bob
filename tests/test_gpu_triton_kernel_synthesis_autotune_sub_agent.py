"""Tests for gpu_triton_kernel_synthesis_autotune_sub_agent."""

from __future__ import annotations

import pathlib
import types

import pytest

from bob3.gpu_triton_kernel_synthesis_autotune_sub_agent import (
    gpu_triton_kernel_synthesis_autotune_sub_agent,
)


def test_gpu_triton_kernel_synthesis_autotune_sub_agent():
    """Main acceptance-criteria test: function is callable and returns expected keys."""
    result = gpu_triton_kernel_synthesis_autotune_sub_agent(
        feature_id="test-feature-123",
        ac_text="Implement a triton matrix-multiply kernel with @triton.jit",
        spec="row-wise softmax over a 2-D float32 tensor",
    )
    assert isinstance(result, dict)
    assert result["routed"] is True
    assert "kernel_source" in result
    assert isinstance(result["kernel_source"], str)
    assert "best_config" in result
    assert isinstance(result["best_config"], dict)
    assert "hardware_label" in result
    assert isinstance(result["hardware_label"], str)
    assert "numerical_report" in result
    assert "passed_gate" in result
    assert isinstance(result["passed_gate"], bool)


class TestGpuTritonKernelSynthesisAutotuneSubAgent:
    def test_routes_gpu_feature(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-001",
            ac_text="Use CUDA to write a fast reduction kernel",
            spec="parallel sum reduction",
        )
        assert result["routed"] is True

    def test_no_route_for_non_gpu_feature(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-002",
            ac_text="Add an HTTP endpoint for user login",
            spec="REST endpoint",
        )
        assert result["routed"] is False

    def test_kernel_source_contains_triton_jit(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-003",
            ac_text="Write a triton kernel for softmax",
            spec="softmax kernel",
        )
        assert result["routed"] is True
        assert "@triton.jit" in result["kernel_source"]

    def test_kernel_source_contains_autotune(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-004",
            ac_text="Implement a CUDA matrix multiply kernel",
            spec="matrix multiply",
        )
        assert result["routed"] is True
        assert "@triton.autotune" in result["kernel_source"]

    def test_best_config_has_triton_params(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-005",
            ac_text="Write a ROCm kernel for layer normalization",
            spec="layer norm",
        )
        assert result["routed"] is True
        cfg = result["best_config"]
        assert any(k in cfg for k in ("BLOCK_M", "BLOCK_N", "BLOCK_K", "num_warps", "num_stages"))

    def test_hardware_label_is_string(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-006",
            ac_text="triton kernel for attention",
            spec="attention kernel",
        )
        assert isinstance(result["hardware_label"], str)
        assert len(result["hardware_label"]) > 0

    def test_numerical_report_has_error_fields(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-007",
            ac_text="triton matrix multiply kernel",
            spec="matrix multiply",
        )
        assert result["routed"] is True
        report = result["numerical_report"]
        assert "max_abs_err" in report
        assert "max_rel_err" in report

    def test_passed_gate_is_bool(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-008",
            ac_text="@triton.jit softmax kernel",
            spec="softmax",
        )
        assert isinstance(result["passed_gate"], bool)

    def test_non_gpu_returns_minimal_dict(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-009",
            ac_text="Add a REST endpoint for user authentication",
            spec="auth endpoint",
        )
        assert result["routed"] is False
        # Non-GPU features don't have kernel artifacts
        assert result.get("kernel_source") is None or "kernel_source" not in result or result.get("kernel_source") == ""

    def test_config_path_returned_when_persisted(self, tmp_path):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-persist-001",
            ac_text="triton matmul kernel",
            spec="matmul",
            runs_root=tmp_path,
        )
        assert result["routed"] is True
        assert "config_path" in result
        config_path = result["config_path"]
        assert config_path is not None
        assert pathlib.Path(config_path).exists()

    def test_feature_id_used_in_config_path(self, tmp_path):
        fid = "my-unique-feature-xyz"
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id=fid,
            ac_text="CUDA kernel for softmax",
            spec="softmax",
            runs_root=tmp_path,
        )
        assert result["routed"] is True
        config_path = result["config_path"]
        assert fid in str(config_path)

    def test_all_timings_in_autotune_result(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-010",
            ac_text="GPU kernel for layer norm using triton",
            spec="layer norm",
        )
        assert result["routed"] is True
        assert "all_timings" in result
        assert isinstance(result["all_timings"], list)
        assert len(result["all_timings"]) > 0

    def test_detects_gpu_kernel_phrase(self):
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-011",
            ac_text="This feature requires a GPU kernel for fast inference",
            spec="inference kernel",
        )
        assert result["routed"] is True

    def test_passed_gate_true_for_zero_error(self):
        # When kernel output matches reference, gate passes
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-012",
            ac_text="triton softmax kernel",
            spec="softmax",
            kernel_output=[1.0, 2.0, 3.0],
            reference_output=[1.0, 2.0, 3.0],
        )
        assert result["routed"] is True
        assert result["passed_gate"] is True

    def test_passed_gate_false_for_large_error(self):
        # When kernel output differs significantly, gate fails
        result = gpu_triton_kernel_synthesis_autotune_sub_agent(
            feature_id="feat-013",
            ac_text="triton softmax kernel",
            spec="softmax",
            kernel_output=[1.0, 2.0, 3.0],
            reference_output=[100.0, 200.0, 300.0],
            atol=1e-5,
        )
        assert result["routed"] is True
        assert result["passed_gate"] is False
