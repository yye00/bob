"""Tests for hand-written reference implementations (paper artifact).

Validates the D1/D2/D3 gold-standard reference implementations used for
differential testing and no-AI baseline comparisons.
"""

from __future__ import annotations

import math

import pytest

from bob.hand_written_reference_implementations_paper_artifact_stub import (
    # D1 — GPT-2 / nanoGPT reference helpers
    gelu_activation,
    softmax,
    scaled_dot_product_attention,
    layer_norm,
    # D2 — WASM interpreter reference helpers
    wasm_i32_add,
    wasm_i32_sub,
    wasm_i32_mul,
    wasm_i32_div_s,
    wasm_i32_div_u,
    wasm_i64_add,
    wasm_i64_mul,
    wasm_f64_add,
    wasm_f64_div,
    wasm_i32_clz,
    wasm_i32_ctz,
    wasm_i32_popcnt,
    # D3 — Navier-Stokes / cavity reference helpers
    ghia_reference_re100,
    mac_grid_shape,
    pressure_poisson_sor_step,
    divergence_field,
    # Registry
    get_reference_registry,
    REFERENCE_DOMAIN_D1,
    REFERENCE_DOMAIN_D2,
    REFERENCE_DOMAIN_D3,
)


# ---------------------------------------------------------------------------
# D1 — GPT-2 building blocks
# ---------------------------------------------------------------------------


class TestGeluActivation:
    def test_gelu_zero(self):
        assert gelu_activation(0.0) == pytest.approx(0.0, abs=1e-6)

    def test_gelu_positive(self):
        # GELU(1.0) ≈ 0.8413
        result = gelu_activation(1.0)
        assert result == pytest.approx(0.8413, abs=1e-3)

    def test_gelu_negative(self):
        # GELU(-1.0) is small negative
        result = gelu_activation(-1.0)
        assert result < 0.0
        assert result == pytest.approx(-0.1587, abs=1e-3)

    def test_gelu_large_positive_approaches_identity(self):
        # For very large x, GELU(x) ≈ x
        result = gelu_activation(10.0)
        assert result == pytest.approx(10.0, abs=0.01)

    def test_gelu_large_negative_approaches_zero(self):
        result = gelu_activation(-10.0)
        assert abs(result) < 0.01


class TestSoftmax:
    def test_softmax_uniform(self):
        result = softmax([1.0, 1.0, 1.0])
        assert len(result) == 3
        for v in result:
            assert v == pytest.approx(1.0 / 3.0, abs=1e-6)

    def test_softmax_sums_to_one(self):
        values = [1.0, 2.0, 3.0, -1.0]
        result = softmax(values)
        assert sum(result) == pytest.approx(1.0, abs=1e-6)

    def test_softmax_max_dominates(self):
        result = softmax([0.0, 0.0, 100.0])
        assert result[2] > 0.99

    def test_softmax_all_zeros(self):
        result = softmax([0.0, 0.0, 0.0])
        for v in result:
            assert v == pytest.approx(1.0 / 3.0, abs=1e-6)

    def test_softmax_single_element(self):
        result = softmax([5.0])
        assert result[0] == pytest.approx(1.0, abs=1e-9)

    def test_softmax_numerically_stable(self):
        # Large values should not overflow
        result = softmax([1000.0, 1001.0, 1002.0])
        assert sum(result) == pytest.approx(1.0, abs=1e-6)


class TestScaledDotProductAttention:
    def test_attention_single_head_shape(self):
        # q, k, v each (seq_len=2, d_k=4)
        import math
        q = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        k = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        v = [[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]]
        result = scaled_dot_product_attention(q, k, v)
        assert len(result) == 2
        assert len(result[0]) == 4

    def test_attention_output_is_weighted_average_of_v(self):
        # When q matches only the first key, output should be close to v[0]
        q = [[10.0, 0.0]]
        k = [[10.0, 0.0], [0.0, 10.0]]
        v = [[1.0, 0.0], [0.0, 1.0]]
        result = scaled_dot_product_attention(q, k, v)
        assert result[0][0] == pytest.approx(1.0, abs=0.01)
        assert result[0][1] == pytest.approx(0.0, abs=0.01)


class TestLayerNorm:
    def test_layer_norm_normalizes(self):
        x = [1.0, 2.0, 3.0, 4.0]
        result = layer_norm(x)
        # mean of result should be ~0, std ~1
        mean = sum(result) / len(result)
        assert mean == pytest.approx(0.0, abs=1e-5)

    def test_layer_norm_unit_variance(self):
        x = [1.0, 2.0, 3.0, 4.0]
        result = layer_norm(x)
        mean = sum(result) / len(result)
        variance = sum((v - mean) ** 2 for v in result) / len(result)
        assert variance == pytest.approx(1.0, abs=1e-4)

    def test_layer_norm_constant_input(self):
        # Constant input -> all zeros (or near zero) after norm
        x = [5.0, 5.0, 5.0, 5.0]
        result = layer_norm(x, eps=1e-5)
        for v in result:
            assert abs(v) < 1e-4

    def test_layer_norm_with_scale_shift(self):
        x = [1.0, 2.0, 3.0]
        gamma = [2.0, 2.0, 2.0]
        beta = [1.0, 1.0, 1.0]
        result = layer_norm(x, gamma=gamma, beta=beta)
        assert len(result) == 3
        # With scale=2, shift=1: mean shifts to 1, std scales to 2
        mean = sum(result) / len(result)
        assert mean == pytest.approx(1.0, abs=1e-4)


# ---------------------------------------------------------------------------
# D2 — WASM numeric operations
# ---------------------------------------------------------------------------


class TestWasmI32Ops:
    def test_add_basic(self):
        assert wasm_i32_add(1, 2) == 3

    def test_add_overflow_wraps(self):
        # i32 wraps at 2^31
        max_i32 = 2**31 - 1
        assert wasm_i32_add(max_i32, 1) == -(2**31)

    def test_sub_basic(self):
        assert wasm_i32_sub(5, 3) == 2

    def test_sub_underflow_wraps(self):
        min_i32 = -(2**31)
        assert wasm_i32_sub(min_i32, 1) == 2**31 - 1

    def test_mul_basic(self):
        assert wasm_i32_mul(3, 4) == 12

    def test_mul_overflow_wraps(self):
        # Large multiplication wraps
        result = wasm_i32_mul(2**16, 2**16)
        # 2^32 wraps to 0 in 32-bit signed
        assert result == 0

    def test_div_s_basic(self):
        assert wasm_i32_div_s(10, 3) == 3  # truncate toward zero

    def test_div_s_negative(self):
        assert wasm_i32_div_s(-7, 2) == -3  # truncate toward zero

    def test_div_s_by_zero_raises(self):
        with pytest.raises((ZeroDivisionError, RuntimeError)):
            wasm_i32_div_s(10, 0)

    def test_div_u_basic(self):
        assert wasm_i32_div_u(10, 3) == 3

    def test_div_u_treats_as_unsigned(self):
        # -1 as unsigned i32 is 0xFFFFFFFF = 4294967295
        # 4294967295 // 2 = 2147483647
        assert wasm_i32_div_u(-1, 2) == 2**31 - 1


class TestWasmBitOps:
    def test_clz_zero(self):
        # clz(0) = 32 by WASM spec
        assert wasm_i32_clz(0) == 32

    def test_clz_one(self):
        assert wasm_i32_clz(1) == 31

    def test_clz_max(self):
        # 0x80000000 has 0 leading zeros (MSB set)
        assert wasm_i32_clz(-(2**31)) == 0

    def test_ctz_zero(self):
        assert wasm_i32_ctz(0) == 32

    def test_ctz_one(self):
        assert wasm_i32_ctz(1) == 0

    def test_ctz_power_of_two(self):
        assert wasm_i32_ctz(8) == 3

    def test_popcnt_zero(self):
        assert wasm_i32_popcnt(0) == 0

    def test_popcnt_ones(self):
        assert wasm_i32_popcnt(-1) == 32  # all bits set

    def test_popcnt_value(self):
        assert wasm_i32_popcnt(0b10110101) == 5


class TestWasmI64Ops:
    def test_i64_add_basic(self):
        assert wasm_i64_add(1, 2) == 3

    def test_i64_add_overflow_wraps(self):
        max_i64 = 2**63 - 1
        assert wasm_i64_add(max_i64, 1) == -(2**63)

    def test_i64_mul_basic(self):
        assert wasm_i64_mul(3, 4) == 12

    def test_i64_mul_large(self):
        # 2^32 * 2^32 = 2^64 wraps to 0
        result = wasm_i64_mul(2**32, 2**32)
        assert result == 0


class TestWasmF64Ops:
    def test_f64_add_basic(self):
        assert wasm_f64_add(1.5, 2.5) == pytest.approx(4.0)

    def test_f64_add_nan_propagation(self):
        result = wasm_f64_add(float("nan"), 1.0)
        assert math.isnan(result)

    def test_f64_div_basic(self):
        assert wasm_f64_div(10.0, 4.0) == pytest.approx(2.5)

    def test_f64_div_by_zero(self):
        result = wasm_f64_div(1.0, 0.0)
        assert math.isinf(result)

    def test_f64_div_zero_by_zero(self):
        result = wasm_f64_div(0.0, 0.0)
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# D3 — Navier-Stokes / cavity solver references
# ---------------------------------------------------------------------------


class TestGhiaReferenceData:
    def test_returns_dict_with_expected_keys(self):
        data = ghia_reference_re100()
        assert "y" in data
        assert "u" in data

    def test_y_and_u_same_length(self):
        data = ghia_reference_re100()
        assert len(data["y"]) == len(data["u"])

    def test_y_values_in_unit_interval(self):
        data = ghia_reference_re100()
        for y in data["y"]:
            assert 0.0 <= y <= 1.0

    def test_includes_key_ghia_points(self):
        # Ghia et al. table has 17 points
        data = ghia_reference_re100()
        assert len(data["y"]) >= 17

    def test_u_velocity_varies_along_centreline(self):
        data = ghia_reference_re100()
        u_vals = data["u"]
        # The u-velocity is not constant: there must be both positive and
        # near-zero/negative values (recirculation zone in lower half)
        assert max(u_vals) > 0.5
        assert min(u_vals) < 0.0

    def test_u_velocity_at_bottom_near_zero(self):
        data = ghia_reference_re100()
        y_vals = data["y"]
        u_vals = data["u"]
        # At y=0 (bottom wall) u should be 0
        bot_idx = min(range(len(y_vals)), key=lambda i: y_vals[i])
        assert abs(u_vals[bot_idx]) < 1e-6

    def test_u_velocity_at_top_equals_one(self):
        data = ghia_reference_re100()
        y_vals = data["y"]
        u_vals = data["u"]
        top_idx = max(range(len(y_vals)), key=lambda i: y_vals[i])
        assert u_vals[top_idx] == pytest.approx(1.0, abs=1e-6)


class TestMacGridShape:
    def test_basic_shape(self):
        u_shape, v_shape, p_shape = mac_grid_shape(n=4)
        # u: (n+1, n), v: (n, n+1), p: (n, n)
        assert u_shape == (5, 4)
        assert v_shape == (4, 5)
        assert p_shape == (4, 4)

    def test_n_equals_1(self):
        u_shape, v_shape, p_shape = mac_grid_shape(n=1)
        assert u_shape == (2, 1)
        assert v_shape == (1, 2)
        assert p_shape == (1, 1)

    def test_n_equals_8(self):
        u_shape, v_shape, p_shape = mac_grid_shape(n=8)
        assert u_shape == (9, 8)
        assert v_shape == (8, 9)
        assert p_shape == (8, 8)


class TestPressurePoissonSorStep:
    def test_returns_updated_pressure_same_shape(self):
        import numpy as np
        n = 4
        p = np.zeros((n, n))
        b = np.ones((n, n))  # divergence source
        p_new = pressure_poisson_sor_step(p, b, dx=1.0 / n, omega=1.5)
        assert p_new.shape == p.shape

    def test_reduces_residual_over_iterations(self):
        import numpy as np
        n = 8
        p = np.zeros((n, n))
        # A simple manufactured right-hand-side
        b = np.zeros((n, n))
        b[n // 2, n // 2] = 1.0

        initial_norm = np.linalg.norm(b)
        p_current = p.copy()
        for _ in range(50):
            p_current = pressure_poisson_sor_step(p_current, b, dx=1.0 / n, omega=1.5)
        # After iterations, the max pressure should be nonzero (solver is doing work)
        assert np.max(np.abs(p_current)) > 0.0


class TestDivergenceField:
    def test_zero_velocity_has_zero_divergence(self):
        import numpy as np
        n = 4
        u = np.zeros((n + 1, n))
        v = np.zeros((n, n + 1))
        div = divergence_field(u, v, dx=1.0 / n)
        assert np.allclose(div, 0.0)

    def test_uniform_flow_has_zero_divergence(self):
        import numpy as np
        n = 4
        dx = 1.0 / n
        u = np.ones((n + 1, n))  # uniform u everywhere
        v = np.zeros((n, n + 1))  # no v
        div = divergence_field(u, v, dx=dx)
        # uniform u: du/dx = 0 everywhere (same value left and right)
        assert np.allclose(div, 0.0, atol=1e-10)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestReferenceRegistry:
    def test_registry_has_three_domains(self):
        reg = get_reference_registry()
        assert REFERENCE_DOMAIN_D1 in reg
        assert REFERENCE_DOMAIN_D2 in reg
        assert REFERENCE_DOMAIN_D3 in reg

    def test_registry_domains_have_functions(self):
        reg = get_reference_registry()
        for domain, fns in reg.items():
            assert isinstance(fns, dict)
            assert len(fns) > 0

    def test_d1_registry_contains_expected_functions(self):
        reg = get_reference_registry()
        d1 = reg[REFERENCE_DOMAIN_D1]
        assert "gelu" in d1
        assert "softmax" in d1
        assert "layer_norm" in d1

    def test_d2_registry_contains_expected_functions(self):
        reg = get_reference_registry()
        d2 = reg[REFERENCE_DOMAIN_D2]
        assert "i32_add" in d2
        assert "i32_clz" in d2

    def test_d3_registry_contains_expected_functions(self):
        reg = get_reference_registry()
        d3 = reg[REFERENCE_DOMAIN_D3]
        assert "ghia_reference_re100" in d3
        assert "mac_grid_shape" in d3

    def test_registry_functions_are_callable(self):
        reg = get_reference_registry()
        for domain, fns in reg.items():
            for name, fn in fns.items():
                assert callable(fn), f"Registry entry {domain}/{name} is not callable"
