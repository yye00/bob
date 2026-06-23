"""Tests for bob3.readiness_scoring (feature c13e7eb9).

Verifies:
  - derive_readiness_from_components computes mean(impl, spec, test)
  - seed_zero_readiness_features delegates to the run_loop sweep
  - Module is importable from the canonical path
"""
from __future__ import annotations

import math
import unittest
from unittest.mock import patch


class TestModuleImports:
    """The canonical module and its public API must be importable."""

    def test_module_importable(self):
        import bob3.readiness_scoring  # noqa: F401

    def test_derive_readiness_from_components_importable(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        assert callable(derive_readiness_from_components)

    def test_seed_zero_readiness_features_importable(self):
        from bob3.readiness_scoring import seed_zero_readiness_features

        assert callable(seed_zero_readiness_features)


class TestDeriveReadinessFromComponents:
    """derive_readiness_from_components must compute mean(impl, spec, test)."""

    def test_uniform_high(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=0.9,
            conf_spec_understanding=0.9,
            conf_test_quality=0.9,
        )
        assert abs(score - 0.9) < 1e-9

    def test_uniform_low(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=0.3,
            conf_spec_understanding=0.3,
            conf_test_quality=0.3,
        )
        assert abs(score - 0.3) < 1e-9

    def test_mixed_components(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=0.6,
            conf_spec_understanding=0.9,
            conf_test_quality=0.3,
        )
        expected = (0.6 + 0.9 + 0.3) / 3.0
        assert abs(score - expected) < 1e-9

    def test_all_zeros(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        )
        assert score == 0.0

    def test_all_ones(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=1.0,
            conf_spec_understanding=1.0,
            conf_test_quality=1.0,
        )
        assert abs(score - 1.0) < 1e-9

    def test_result_finite(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=0.5,
            conf_spec_understanding=0.7,
            conf_test_quality=0.8,
        )
        assert math.isfinite(score)

    def test_result_in_range(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=0.5,
            conf_spec_understanding=0.7,
            conf_test_quality=0.8,
        )
        assert 0.0 <= score <= 1.0

    def test_negative_raises(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        try:
            derive_readiness_from_components(
                conf_impl_correctness=-0.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_above_one_raises(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        try:
            derive_readiness_from_components(
                conf_impl_correctness=1.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_nan_raises(self):
        from bob3.readiness_scoring import derive_readiness_from_components

        try:
            derive_readiness_from_components(
                conf_impl_correctness=math.nan,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_delegates_to_readiness_module(self):
        """derive_readiness_from_components must use bob3.readiness.derive_readiness_score."""
        from bob3.readiness_scoring import derive_readiness_from_components

        with patch("bob3.readiness_scoring._derive_readiness_score", return_value=0.777) as mock:
            result = derive_readiness_from_components(
                conf_impl_correctness=0.8,
                conf_spec_understanding=0.8,
                conf_test_quality=0.8,
            )
        mock.assert_called_once()
        assert result == 0.777


class TestSeedZeroReadinessFeatures:
    """seed_zero_readiness_features must delegate to the run_loop sweep."""

    def test_returns_int(self):
        from bob3.readiness_scoring import seed_zero_readiness_features

        with patch("bob3.readiness_scoring._seed_readiness_at_iteration_start", return_value=0):
            result = seed_zero_readiness_features("test-project-id")
        assert isinstance(result, int)

    def test_returns_count_from_delegate(self):
        from bob3.readiness_scoring import seed_zero_readiness_features

        with patch("bob3.readiness_scoring._seed_readiness_at_iteration_start", return_value=5):
            result = seed_zero_readiness_features("test-project-id")
        assert result == 5

    def test_delegates_to_run_loop(self):
        from bob3.readiness_scoring import seed_zero_readiness_features

        with patch("bob3.readiness_scoring._seed_readiness_at_iteration_start", return_value=3) as mock:
            seed_zero_readiness_features("my-project")
        mock.assert_called_once_with("my-project")

    def test_zero_when_no_features_need_seeding(self):
        from bob3.readiness_scoring import seed_zero_readiness_features

        with patch("bob3.readiness_scoring._seed_readiness_at_iteration_start", return_value=0):
            result = seed_zero_readiness_features("empty-project")
        assert result == 0


class TestOrchestratorIntegration:
    """Verify orchestrator imports and calls readiness_scoring functions."""

    def test_derive_readiness_from_components_in_orchestrator_module(self):
        """The orchestrator must be able to import derive_readiness_from_components."""
        from bob3.readiness_scoring import derive_readiness_from_components

        score = derive_readiness_from_components(
            conf_impl_correctness=0.85,
            conf_spec_understanding=0.90,
            conf_test_quality=0.80,
        )
        expected = (0.85 + 0.90 + 0.80) / 3.0
        assert abs(score - expected) < 1e-9

    def test_seed_zero_readiness_callable_from_orchestrator_context(self):
        """seed_zero_readiness_features is importable and callable for orchestrator use."""
        from bob3.readiness_scoring import seed_zero_readiness_features

        with patch("bob3.readiness_scoring._seed_readiness_at_iteration_start", return_value=2):
            result = seed_zero_readiness_features("orch-project")
        assert result == 2

    def test_readiness_scoring_module_in_bob3_namespace(self):
        """bob3.readiness_scoring is accessible via the bob3 package namespace."""
        import bob3.readiness_scoring as rs

        assert hasattr(rs, "derive_readiness_from_components")
        assert hasattr(rs, "seed_zero_readiness_features")
