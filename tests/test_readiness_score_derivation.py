"""Tests for bob3.readiness_score.derive_readiness_from_confidence (feature 7042c0c5).

Verifies that:
- derive_readiness_from_confidence is importable from bob3.readiness_score
- It computes mean(impl, spec, test) from live confidence values
- It raises ValueError for invalid inputs (out-of-range, non-numeric, non-finite)
- It handles boundary values correctly (all-zero, all-one, threshold values)
- The readiness_score module also exports derive_readiness_score as an alias
"""
from __future__ import annotations

import math

import pytest


class TestDeriveReadinessFromConfidenceImport:
    """derive_readiness_from_confidence must be importable from bob3.readiness_score."""

    def test_importable(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        assert callable(derive_readiness_from_confidence)

    def test_module_file_exists(self):
        import importlib.util

        spec = importlib.util.find_spec("bob3.readiness_score")
        assert spec is not None, "bob3.readiness_score module must exist"

    def test_derive_readiness_score_also_exported(self):
        from bob3.readiness_score import derive_readiness_score

        assert callable(derive_readiness_score)


class TestDeriveReadinessFromConfidenceComputation:
    """derive_readiness_from_confidence must compute mean(impl, spec, test)."""

    def test_all_equal_returns_same_value(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        for v in (0.0, 0.5, 0.7, 0.8, 0.9, 1.0):
            score = derive_readiness_from_confidence(
                conf_impl_correctness=v,
                conf_spec_understanding=v,
                conf_test_quality=v,
            )
            assert abs(score - v) < 1e-9, f"Failed for all-equal value {v}"

    def test_mean_of_different_values(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        score = derive_readiness_from_confidence(
            conf_impl_correctness=0.6,
            conf_spec_understanding=0.9,
            conf_test_quality=0.3,
        )
        expected = (0.6 + 0.9 + 0.3) / 3.0
        assert abs(score - expected) < 1e-9

    def test_all_zero_returns_zero(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        score = derive_readiness_from_confidence(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        )
        assert score == 0.0

    def test_all_one_returns_one(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        score = derive_readiness_from_confidence(
            conf_impl_correctness=1.0,
            conf_spec_understanding=1.0,
            conf_test_quality=1.0,
        )
        assert abs(score - 1.0) < 1e-9

    def test_result_in_valid_range(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        score = derive_readiness_from_confidence(
            conf_impl_correctness=0.7,
            conf_spec_understanding=0.8,
            conf_test_quality=0.9,
        )
        assert 0.0 <= score <= 1.0

    def test_threshold_boundary_values(self):
        """Values at common thresholds (0.70, 0.80, 0.90, 0.95) compute correctly."""
        from bob3.readiness_score import derive_readiness_from_confidence

        for v in (0.70, 0.80, 0.90, 0.95):
            score = derive_readiness_from_confidence(
                conf_impl_correctness=v,
                conf_spec_understanding=v,
                conf_test_quality=v,
            )
            assert abs(score - v) < 1e-9, f"Failed for boundary value {v}"

    def test_mixed_zero_and_nonzero(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        score = derive_readiness_from_confidence(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.9,
            conf_test_quality=0.0,
        )
        expected = 0.9 / 3.0
        assert abs(score - expected) < 1e-9

    def test_result_is_finite(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        score = derive_readiness_from_confidence(
            conf_impl_correctness=0.5,
            conf_spec_understanding=0.5,
            conf_test_quality=0.5,
        )
        assert math.isfinite(score)


class TestDeriveReadinessFromConfidenceValidation:
    """derive_readiness_from_confidence must raise ValueError for invalid inputs."""

    def test_negative_impl_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises(ValueError):
            derive_readiness_from_confidence(
                conf_impl_correctness=-0.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_negative_spec_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises(ValueError):
            derive_readiness_from_confidence(
                conf_impl_correctness=0.5,
                conf_spec_understanding=-0.01,
                conf_test_quality=0.5,
            )

    def test_negative_test_quality_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises(ValueError):
            derive_readiness_from_confidence(
                conf_impl_correctness=0.5,
                conf_spec_understanding=0.5,
                conf_test_quality=-1.0,
            )

    def test_above_one_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises(ValueError):
            derive_readiness_from_confidence(
                conf_impl_correctness=1.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_nan_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises(ValueError):
            derive_readiness_from_confidence(
                conf_impl_correctness=math.nan,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_inf_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises(ValueError):
            derive_readiness_from_confidence(
                conf_impl_correctness=0.5,
                conf_spec_understanding=math.inf,
                conf_test_quality=0.5,
            )

    def test_string_input_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises((ValueError, TypeError)):
            derive_readiness_from_confidence(
                conf_impl_correctness="high",  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_boolean_input_raises(self):
        """bool is a subclass of int; it must be rejected explicitly."""
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises(ValueError):
            derive_readiness_from_confidence(
                conf_impl_correctness=True,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_none_input_raises(self):
        from bob3.readiness_score import derive_readiness_from_confidence

        with pytest.raises((ValueError, TypeError)):
            derive_readiness_from_confidence(
                conf_impl_correctness=None,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )


class TestReadinessScoreModuleIntegrity:
    """The readiness_score module must correctly re-export from bob3.readiness."""

    def test_delegates_to_same_logic_as_readiness_module(self):
        from bob3.readiness import derive_readiness_score as canonical
        from bob3.readiness_score import derive_readiness_from_confidence

        impl, spec, test = 0.7, 0.85, 0.9
        rs_result = derive_readiness_from_confidence(
            conf_impl_correctness=impl,
            conf_spec_understanding=spec,
            conf_test_quality=test,
        )
        canonical_result = canonical(
            conf_impl_correctness=impl,
            conf_spec_understanding=spec,
            conf_test_quality=test,
        )
        assert abs(rs_result - canonical_result) < 1e-12

    def test_derive_readiness_score_alias_gives_same_result(self):
        from bob3.readiness_score import derive_readiness_from_confidence, derive_readiness_score

        impl, spec, test = 0.6, 0.75, 0.8
        result1 = derive_readiness_from_confidence(
            conf_impl_correctness=impl,
            conf_spec_understanding=spec,
            conf_test_quality=test,
        )
        result2 = derive_readiness_score(
            conf_impl_correctness=impl,
            conf_spec_understanding=spec,
            conf_test_quality=test,
        )
        assert abs(result1 - result2) < 1e-12
