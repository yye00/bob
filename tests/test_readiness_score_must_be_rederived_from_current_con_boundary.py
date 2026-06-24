"""Boundary-case tests for readiness derivation (feature f66182b9).

Verifies that empty, zero, or minimum inputs to derive_readiness_score
return well-defined results rather than raising.
"""
from __future__ import annotations

import pytest


class TestDeriveReadinessBoundary:
    """derive_readiness_score must handle boundary inputs gracefully."""

    def test_all_zero_returns_zero(self):
        from bob.readiness import derive_readiness_score

        score = derive_readiness_score(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        )
        assert score == 0.0

    def test_all_one_returns_one(self):
        from bob.readiness import derive_readiness_score

        score = derive_readiness_score(
            conf_impl_correctness=1.0,
            conf_spec_understanding=1.0,
            conf_test_quality=1.0,
        )
        assert abs(score - 1.0) < 1e-9

    def test_minimum_nonzero_input_is_finite(self):
        """Smallest representable positive float should return a well-defined finite result."""
        import math
        from bob.readiness import derive_readiness_score

        tiny = 1e-10
        score = derive_readiness_score(
            conf_impl_correctness=tiny,
            conf_spec_understanding=tiny,
            conf_test_quality=tiny,
        )
        assert math.isfinite(score)
        assert score > 0.0

    def test_mixed_zero_and_nonzero_does_not_raise(self):
        from bob.readiness import derive_readiness_score

        score = derive_readiness_score(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.5,
            conf_test_quality=0.0,
        )
        expected = (0.0 + 0.5 + 0.0) / 3.0
        assert abs(score - expected) < 1e-9

    def test_exactly_threshold_boundary(self):
        """Values at common threshold boundaries (0.70, 0.80, 0.90) round-trip cleanly."""
        from bob.readiness import derive_readiness_score

        for v in (0.70, 0.80, 0.90, 0.95):
            score = derive_readiness_score(
                conf_impl_correctness=v,
                conf_spec_understanding=v,
                conf_test_quality=v,
            )
            assert abs(score - v) < 1e-9, f"Failed for boundary value {v}"
