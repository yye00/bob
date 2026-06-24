"""Tests for default_sweep_space — boundary/edge cases, especially minimum values.

AC: asserts default_sweep_space returns dict whose BLOCK_M minimum value equals 32.
"""

from __future__ import annotations

import bob3.implementers.triton_kernel as tk


class TestBoundaryMinBlockSize:
    def test_default_sweep_space_returns_dict(self):
        space = tk.default_sweep_space()
        assert isinstance(space, dict)

    def test_block_m_minimum_equals_32(self):
        space = tk.default_sweep_space()
        assert min(space["BLOCK_M"]) == 32

    def test_block_n_minimum_equals_32(self):
        space = tk.default_sweep_space()
        assert min(space["BLOCK_N"]) == 32

    def test_block_k_minimum_equals_32(self):
        space = tk.default_sweep_space()
        assert min(space["BLOCK_K"]) == 32

    def test_num_warps_minimum_equals_2(self):
        space = tk.default_sweep_space()
        assert min(space["num_warps"]) == 2

    def test_num_stages_minimum_equals_2(self):
        space = tk.default_sweep_space()
        assert min(space["num_stages"]) == 2

    def test_block_m_contains_128(self):
        space = tk.default_sweep_space()
        assert 128 in space["BLOCK_M"]

    def test_block_n_contains_128(self):
        space = tk.default_sweep_space()
        assert 128 in space["BLOCK_N"]

    def test_num_warps_contains_8(self):
        space = tk.default_sweep_space()
        assert 8 in space["num_warps"]

    def test_num_stages_contains_4(self):
        space = tk.default_sweep_space()
        assert 4 in space["num_stages"]

    def test_has_all_required_keys(self):
        space = tk.default_sweep_space()
        for key in ("BLOCK_M", "BLOCK_N", "BLOCK_K", "num_warps", "num_stages"):
            assert key in space, f"Missing key: {key}"

    def test_all_values_are_lists(self):
        space = tk.default_sweep_space()
        for key, val in space.items():
            assert isinstance(val, list), f"Key {key!r} should be a list"
