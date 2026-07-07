"""Tests for live readiness rederivation (feature cd58d8cf).

readiness_score MUST be rederived from the current confidence components on
each refinement attempt — never carried forward as decaying stored state.

Covers:
  - rederive_readiness_score: mean of the three live components, with the
    persisted (possibly-decayed) readiness_score explicitly ignored.
  - assess_feature_confidence: package-level entry point that derives readiness
    from the demonstrated spec_quality_score composite.
"""
from __future__ import annotations

import math

import pytest


class TestRederiveReadinessScore:
    """rederive_readiness_score aggregates live components at read time."""

    def test_returns_mean_of_components(self):
        from bob.readiness import rederive_readiness_score

        score = rederive_readiness_score(
            conf_impl_correctness=0.9,
            conf_spec_understanding=0.6,
            conf_test_quality=0.3,
        )
        assert abs(score - (0.9 + 0.6 + 0.3) / 3.0) < 1e-9

    def test_ignores_stale_persisted_readiness(self):
        """A decayed prior readiness must not lower a fresh recomputation."""
        from bob.readiness import rederive_readiness_score

        # High live components should yield high readiness regardless of any
        # decayed stored value the caller might pass for context.
        fresh = rederive_readiness_score(
            conf_impl_correctness=0.95,
            conf_spec_understanding=0.95,
            conf_test_quality=0.95,
            previous_readiness_score=0.10,
        )
        assert fresh > 0.9

    def test_recovery_is_not_ratcheted_down(self):
        """Successive attempts with improving components raise readiness."""
        from bob.readiness import rederive_readiness_score

        low = rederive_readiness_score(
            conf_impl_correctness=0.4,
            conf_spec_understanding=0.4,
            conf_test_quality=0.4,
        )
        high = rederive_readiness_score(
            conf_impl_correctness=0.8,
            conf_spec_understanding=0.8,
            conf_test_quality=0.8,
        )
        assert high > low

    def test_all_zero_returns_zero(self):
        from bob.readiness import rederive_readiness_score

        assert rederive_readiness_score(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        ) == 0.0

    def test_all_one_returns_one(self):
        from bob.readiness import rederive_readiness_score

        assert abs(
            rederive_readiness_score(
                conf_impl_correctness=1.0,
                conf_spec_understanding=1.0,
                conf_test_quality=1.0,
            )
            - 1.0
        ) < 1e-9

    def test_matches_derive_readiness_score(self):
        """rederive is a live-recompute wrapper over the same aggregation."""
        from bob.readiness import derive_readiness_score, rederive_readiness_score

        kwargs = dict(
            conf_impl_correctness=0.7,
            conf_spec_understanding=0.5,
            conf_test_quality=0.9,
        )
        assert rederive_readiness_score(**kwargs) == derive_readiness_score(**kwargs)

    def test_negative_component_raises(self):
        from bob.readiness import rederive_readiness_score

        with pytest.raises(ValueError):
            rederive_readiness_score(
                conf_impl_correctness=-0.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_above_one_component_raises(self):
        from bob.readiness import rederive_readiness_score

        with pytest.raises(ValueError):
            rederive_readiness_score(
                conf_impl_correctness=0.5,
                conf_spec_understanding=1.5,
                conf_test_quality=0.5,
            )

    def test_nan_component_raises(self):
        from bob.readiness import rederive_readiness_score

        with pytest.raises(ValueError):
            rederive_readiness_score(
                conf_impl_correctness=math.nan,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_bool_component_raises(self):
        from bob.readiness import rederive_readiness_score

        with pytest.raises(ValueError):
            rederive_readiness_score(
                conf_impl_correctness=True,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_invalid_previous_readiness_raises(self):
        from bob.readiness import rederive_readiness_score

        with pytest.raises(ValueError):
            rederive_readiness_score(
                conf_impl_correctness=0.5,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
                previous_readiness_score=2.0,
            )


class TestAssessFeatureConfidence:
    """Package-level assess_feature_confidence entry point."""

    def test_is_callable(self):
        from bob.readiness import assess_feature_confidence

        assert callable(assess_feature_confidence)

    def test_missing_feature_returns_zeroed_dict(self):
        from bob.readiness import assess_feature_confidence

        result = assess_feature_confidence("nonexistent-feature-id-000000")
        assert isinstance(result, dict)
        assert result["readiness_score"] == 0.0
        assert set(result) >= {
            "conf_spec_understanding",
            "conf_impl_correctness",
            "conf_test_adequacy",
            "readiness_score",
        }

    def test_delegates_to_db_assessment(self):
        """Package entry point matches the canonical db implementation."""
        from bob import db
        from bob.readiness import assess_feature_confidence

        fid = "nonexistent-feature-id-111111"
        assert assess_feature_confidence(fid) == db.assess_feature_confidence(fid)
