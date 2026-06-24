"""Tests for synthesize_kernel — verifies the returned source has the right shape."""

from __future__ import annotations

import bob.implementers.triton_kernel as tk


class TestSynthesizeKernelSignatureMatches:
    def test_returns_string(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert isinstance(src, str)

    def test_contains_triton_jit_decorator(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "@triton.jit" in src

    def test_contains_triton_autotune_decorator(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "@triton.autotune" in src

    def test_contains_block_m_constexpr(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "BLOCK_M" in src

    def test_contains_block_n_constexpr(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "BLOCK_N" in src

    def test_contains_block_k_constexpr(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "BLOCK_K" in src

    def test_contains_num_warps(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "num_warps" in src

    def test_contains_num_stages(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "num_stages" in src

    def test_contains_launcher_function(self):
        src = tk.synthesize_kernel("row-wise softmax", kernel_name="my_kernel")
        assert "def my_kernel(" in src

    def test_contains_import_triton(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "import triton" in src

    def test_contains_import_torch(self):
        src = tk.synthesize_kernel("row-wise softmax")
        assert "import torch" in src

    def test_spec_embedded_in_docstring(self):
        spec = "custom test spec for softmax"
        src = tk.synthesize_kernel(spec)
        assert spec in src
