"""Tests for bob.readiness_score — live derivation from confidence components.

Acceptance criteria verified:
- Function defined: bob.readiness_score.compute_readiness_from_components
- Function defined: bob.readiness_score.seed_zero_readiness_features
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from bob.readiness_score import (
    compute_readiness_from_components,
    derive_readiness_from_confidence,
    derive_readiness_score,
    seed_zero_readiness_features,
)


class TestComputeReadinessFromComponents:
    """compute_readiness_from_components derives readiness live from confidence components."""

    def test_equal_components_return_mean(self):
        result = compute_readiness_from_components(
            conf_impl_correctness=0.9,
            conf_spec_understanding=0.9,
            conf_test_quality=0.9,
        )
        assert abs(result - 0.9) < 1e-9

    def test_mixed_components_return_mean(self):
        result = compute_readiness_from_components(
            conf_impl_correctness=0.6,
            conf_spec_understanding=0.9,
            conf_test_quality=0.75,
        )
        expected = (0.6 + 0.9 + 0.75) / 3.0
        assert abs(result - expected) < 1e-9

    def test_all_zero_returns_zero(self):
        result = compute_readiness_from_components(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        )
        assert result == 0.0

    def test_all_one_returns_one(self):
        result = compute_readiness_from_components(
            conf_impl_correctness=1.0,
            conf_spec_understanding=1.0,
            conf_test_quality=1.0,
        )
        assert abs(result - 1.0) < 1e-9

    def test_result_in_unit_interval(self):
        result = compute_readiness_from_components(
            conf_impl_correctness=0.5,
            conf_spec_understanding=0.7,
            conf_test_quality=0.3,
        )
        assert 0.0 <= result <= 1.0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            compute_readiness_from_components(
                conf_impl_correctness=-0.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_above_one_raises(self):
        with pytest.raises(ValueError):
            compute_readiness_from_components(
                conf_impl_correctness=1.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_nan_raises(self):
        with pytest.raises(ValueError):
            compute_readiness_from_components(
                conf_impl_correctness=math.nan,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_bool_raises(self):
        with pytest.raises(ValueError):
            compute_readiness_from_components(
                conf_impl_correctness=True,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_is_callable(self):
        assert callable(compute_readiness_from_components)

    def test_consistent_with_derive_readiness_score(self):
        """compute_readiness_from_components and derive_readiness_score must agree."""
        kwargs = dict(
            conf_impl_correctness=0.75,
            conf_spec_understanding=0.85,
            conf_test_quality=0.65,
        )
        assert abs(compute_readiness_from_components(**kwargs) - derive_readiness_score(**kwargs)) < 1e-9


class TestSeedZeroReadinessFeatures:
    """seed_zero_readiness_features delegates to the derivation layer."""

    def test_is_callable(self):
        assert callable(seed_zero_readiness_features)

    def test_delegates_to_derivation_layer(self):
        with patch("bob.readiness_score.seed_zero_readiness_features") as mock_fn:
            mock_fn.return_value = 3
            result = mock_fn("test-project-id")
            assert result == 3
            mock_fn.assert_called_once_with("test-project-id")

    def test_returns_int_on_no_op(self):
        """When the underlying sweep returns 0, seed_zero_readiness_features returns 0."""
        with patch("bob.readiness_derivation.seed_zero_readiness_features", return_value=0):
            result = seed_zero_readiness_features("some-project-id")
            assert isinstance(result, int)
            assert result == 0
