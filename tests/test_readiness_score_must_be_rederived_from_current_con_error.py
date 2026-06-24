"""Error-path tests for readiness derivation (feature f66182b9).

Verifies that invalid inputs to derive_readiness_score raise ValueError
rather than silently succeeding with garbage output.
"""
from __future__ import annotations

import math

import pytest


class TestDeriveReadinessErrorPaths:
    """derive_readiness_score must raise ValueError for out-of-range or non-numeric inputs."""

    def test_negative_impl_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=-0.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_negative_spec_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=0.5,
                conf_spec_understanding=-0.01,
                conf_test_quality=0.5,
            )

    def test_negative_test_quality_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=0.5,
                conf_spec_understanding=0.5,
                conf_test_quality=-1.0,
            )

    def test_above_one_impl_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=1.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_above_one_spec_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=0.5,
                conf_spec_understanding=2.0,
                conf_test_quality=0.5,
            )

    def test_nan_impl_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=math.nan,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_inf_spec_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=0.5,
                conf_spec_understanding=math.inf,
                conf_test_quality=0.5,
            )

    def test_string_input_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises((ValueError, TypeError)):
            derive_readiness_score(
                conf_impl_correctness="high",  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_boolean_input_raises(self):
        """bool is a subclass of int; we must reject it explicitly."""
        from bob.readiness import derive_readiness_score

        with pytest.raises(ValueError):
            derive_readiness_score(
                conf_impl_correctness=True,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_none_input_raises(self):
        from bob.readiness import derive_readiness_score

        with pytest.raises((ValueError, TypeError)):
            derive_readiness_score(
                conf_impl_correctness=None,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )
