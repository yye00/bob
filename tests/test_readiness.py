"""Tests for bob3.readiness — live readiness derivation.

Covers compute_readiness_score, restore_baseline_confidence, and the
integration between derive_readiness_score and the run-loop seed sweep.
"""
from __future__ import annotations

import math
import uuid

import pytest


class TestComputeReadinessScore:
    """compute_readiness_score must derive readiness from confidence components."""

    def test_mean_of_equal_components(self):
        from bob3.readiness import compute_readiness_score

        score = compute_readiness_score(
            conf_impl_correctness=0.8,
            conf_spec_understanding=0.8,
            conf_test_quality=0.8,
        )
        assert abs(score - 0.8) < 1e-9

    def test_mean_of_different_components(self):
        from bob3.readiness import compute_readiness_score

        score = compute_readiness_score(
            conf_impl_correctness=0.6,
            conf_spec_understanding=0.9,
            conf_test_quality=0.75,
        )
        expected = (0.6 + 0.9 + 0.75) / 3.0
        assert abs(score - expected) < 1e-9

    def test_all_zero_returns_zero(self):
        from bob3.readiness import compute_readiness_score

        score = compute_readiness_score(
            conf_impl_correctness=0.0,
            conf_spec_understanding=0.0,
            conf_test_quality=0.0,
        )
        assert score == 0.0

    def test_all_one_returns_one(self):
        from bob3.readiness import compute_readiness_score

        score = compute_readiness_score(
            conf_impl_correctness=1.0,
            conf_spec_understanding=1.0,
            conf_test_quality=1.0,
        )
        assert abs(score - 1.0) < 1e-9

    def test_negative_component_raises(self):
        from bob3.readiness import compute_readiness_score

        with pytest.raises(ValueError):
            compute_readiness_score(
                conf_impl_correctness=-0.1,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_above_one_raises(self):
        from bob3.readiness import compute_readiness_score

        with pytest.raises(ValueError):
            compute_readiness_score(
                conf_impl_correctness=1.01,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_nan_raises(self):
        from bob3.readiness import compute_readiness_score

        with pytest.raises(ValueError):
            compute_readiness_score(
                conf_impl_correctness=math.nan,
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_boolean_raises(self):
        from bob3.readiness import compute_readiness_score

        with pytest.raises(ValueError):
            compute_readiness_score(
                conf_impl_correctness=True,  # type: ignore[arg-type]
                conf_spec_understanding=0.5,
                conf_test_quality=0.5,
            )

    def test_result_is_finite(self):
        from bob3.readiness import compute_readiness_score

        score = compute_readiness_score(
            conf_impl_correctness=0.7,
            conf_spec_understanding=0.8,
            conf_test_quality=0.9,
        )
        assert math.isfinite(score)

    def test_delegates_to_derive_readiness_score(self):
        """compute_readiness_score and derive_readiness_score must agree."""
        from bob3.readiness import compute_readiness_score, derive_readiness_score

        kwargs = dict(
            conf_impl_correctness=0.75,
            conf_spec_understanding=0.85,
            conf_test_quality=0.65,
        )
        assert compute_readiness_score(**kwargs) == derive_readiness_score(**kwargs)


class TestRestoreBaselineConfidence:
    """restore_baseline_confidence must re-seed a feature's confidence from assess_feature_confidence."""

    def _make_feature(self, db_mod, project_id: str) -> str:
        """Create a minimal feature and return its ID."""
        fid = str(uuid.uuid4())
        db_mod.create_feature(
            project_id=project_id,
            feature_id=fid,
            name="test-restore-baseline",
            description="standalone feature for restore test",
            acceptance_criteria='["File exists: src/foo.py"]',
            risk_category="low",
            spec_quality_score=0.95,
        )
        return fid

    def _get_project(self, db_mod) -> str:
        projects = db_mod.list_projects()
        if projects:
            return projects[0].id
        return db_mod.create_project("test-project", "test").id

    def test_returns_false_for_missing_feature(self):
        from bob3.readiness import restore_baseline_confidence

        result = restore_baseline_confidence(str(uuid.uuid4()))
        assert result is False

    def test_returns_true_for_existing_feature(self):
        import bob3.db as db_mod
        from bob3.readiness import restore_baseline_confidence

        project_id = self._get_project(db_mod)
        fid = self._make_feature(db_mod, project_id)
        try:
            result = restore_baseline_confidence(fid)
            assert result is True
        finally:
            # Clean up: don't leave dangling test rows
            try:
                db_mod.update_feature(fid, status="completed")
            except Exception:
                pass

    def test_updates_readiness_score(self):
        import bob3.db as db_mod
        from bob3.readiness import restore_baseline_confidence

        project_id = self._get_project(db_mod)
        fid = self._make_feature(db_mod, project_id)
        try:
            # First decay the readiness down to 0.1 to simulate ratchet
            db_mod.update_feature(fid, readiness_score=0.1)
            feature_before = db_mod.get_feature(fid)
            assert feature_before is not None
            assert abs(feature_before.readiness_score - 0.1) < 1e-9

            # Restore should push it back up from spec_quality_score
            restore_baseline_confidence(fid)
            feature_after = db_mod.get_feature(fid)
            assert feature_after is not None
            # spec_quality_score=0.95 * 0.92 (standalone) = 0.874
            assert feature_after.readiness_score > 0.1
        finally:
            try:
                db_mod.update_feature(fid, status="completed")
            except Exception:
                pass


class TestSeedReadinessOnReadyFeatures:
    """seed_readiness_on_ready_features must seed all ready features at 0.0."""

    def test_importable(self):
        from bob3.run_loop import seed_readiness_on_ready_features  # noqa: F401

    def test_returns_int(self):
        """With a dummy project ID that has no features, should return 0."""
        from bob3.run_loop import seed_readiness_on_ready_features

        result = seed_readiness_on_ready_features(str(uuid.uuid4()))
        assert isinstance(result, int)
        assert result == 0

    def test_seeds_zero_readiness_ready_features(self):
        """Ready features with readiness_score=0.0 should be seeded."""
        import bob3.db as db_mod
        from bob3.run_loop import seed_readiness_on_ready_features

        projects = db_mod.list_projects()
        if projects:
            project_id = projects[0].id
        else:
            project_id = db_mod.create_project("test-seed-project", "test").id

        fid = str(uuid.uuid4())
        db_mod.create_feature(
            project_id=project_id,
            feature_id=fid,
            name="seed-readiness-test-feature",
            description="standalone feature for seed readiness test",
            acceptance_criteria='["File exists: src/bar.py"]',
            risk_category="low",
            spec_quality_score=0.95,
        )
        try:
            # Force status=ready and readiness_score=0.0
            db_mod.update_feature(fid, status="ready", readiness_score=0.0)
            feature_before = db_mod.get_feature(fid)
            assert feature_before is not None
            assert feature_before.status == "ready"
            assert feature_before.readiness_score == 0.0

            seeded = seed_readiness_on_ready_features(project_id)
            assert seeded >= 1

            feature_after = db_mod.get_feature(fid)
            assert feature_after is not None
            assert feature_after.readiness_score > 0.0
        finally:
            try:
                db_mod.update_feature(fid, status="completed")
            except Exception:
                pass
