"""Tests for is_gpu_feature and gpu_keyword_set detection logic."""

from __future__ import annotations

import bob3.implementers.triton_kernel as tk


class TestGpuKeywordSet:
    def test_returns_frozenset(self):
        result = tk.gpu_keyword_set()
        assert isinstance(result, frozenset)

    def test_contains_triton(self):
        assert "triton" in tk.gpu_keyword_set()

    def test_contains_cuda(self):
        assert "cuda" in tk.gpu_keyword_set()

    def test_contains_rocm(self):
        assert "rocm" in tk.gpu_keyword_set()

    def test_contains_triton_jit(self):
        assert "@triton.jit" in tk.gpu_keyword_set()

    def test_contains_gpu_kernel(self):
        assert "GPU kernel" in tk.gpu_keyword_set()


class TestIsGpuFeature:
    def test_detects_triton_lowercase(self):
        assert tk.is_gpu_feature("implement a triton softmax kernel") is True

    def test_detects_cuda_uppercase(self):
        assert tk.is_gpu_feature("Write a CUDA matrix-multiply") is True

    def test_detects_rocm(self):
        assert tk.is_gpu_feature("Port to ROCm backend") is True

    def test_detects_triton_jit_decorator(self):
        assert tk.is_gpu_feature("Use @triton.jit to write the kernel") is True

    def test_detects_gpu_kernel_phrase(self):
        assert tk.is_gpu_feature("This feature requires a GPU kernel") is True

    def test_returns_false_for_plain_text(self):
        assert tk.is_gpu_feature("Add logging to the HTTP server") is False

    def test_returns_false_for_empty(self):
        assert tk.is_gpu_feature("") is False

    def test_returns_bool(self):
        result = tk.is_gpu_feature("triton kernel needed")
        assert isinstance(result, bool)
