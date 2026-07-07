"""Tests for bob.triton_kernel_synth — GPU/Triton kernel synthesis + autotune sub-agent."""

from __future__ import annotations

import pytest

from bob.triton_kernel_synth import synthesize_triton_kernel, autotune_and_gate


def test_synthesize_returns_jit_kernel_source():
    src = synthesize_triton_kernel("row-wise softmax over a 2-D float32 tensor")
    assert isinstance(src, str)
    assert "@triton.jit" in src
    assert "@triton.autotune" in src


def test_synthesize_custom_kernel_name():
    src = synthesize_triton_kernel("elementwise add", kernel_name="my_add")
    assert "my_add" in src


def test_autotune_and_gate_returns_winning_config_over_standard_axes():
    result = autotune_and_gate("matmul kernel")
    assert isinstance(result, dict)
    best = result["best_config"]
    for axis in ("BLOCK_M", "BLOCK_N", "BLOCK_K", "num_warps", "num_stages"):
        assert axis in best
    assert result["passed_gate"] is True
    assert "kernel_source" in result
    assert "hardware_label" in result
    assert "all_timings" in result and len(result["all_timings"]) > 0


def test_autotune_and_gate_gates_on_numerical_correctness():
    good = autotune_and_gate(
        "softmax", kernel_output=[1.0, 2.0], reference_output=[1.0, 2.0]
    )
    assert good["passed_gate"] is True

    bad = autotune_and_gate(
        "softmax", kernel_output=[1.0, 2.0], reference_output=[9.0, 9.0]
    )
    assert bad["passed_gate"] is False


def test_autotune_and_gate_persists_winning_config(tmp_path):
    result = autotune_and_gate("matmul", feature_id="feat-xyz", runs_root=tmp_path)
    persisted = result["config_path"]
    assert persisted is not None
    assert persisted.exists()
    assert persisted.read_text().strip() != ""


def test_autotune_and_gate_without_feature_id_does_not_persist():
    result = autotune_and_gate("matmul")
    assert result["config_path"] is None
