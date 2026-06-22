"""Tests for bob3.run_loop.readiness_seed_sweep (feature a892281e).

Verifies that:
- readiness_seed_sweep is importable and callable from bob3.run_loop
- It seeds readiness_score for ready features at 0.0 using assess_feature_confidence
- It skips features that already have a non-zero readiness_score
- It skips features that are not in 'ready' status
- It returns the count of features actually seeded
- It is idempotent (calling twice does not double-count or corrupt)
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database with initialized schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database

    init_database()
    return p


@pytest.fixture()
def project_id(db_path):
    """Create a project and return its ID."""
    from bob3.db import create_project

    project = create_project(
        name="SeedSweep Test Project",
        workspace_path="/tmp/test-seed-sweep",
    )
    return project.id


class TestReadinessSeedSweepImport:
    """readiness_seed_sweep must be importable from bob3.run_loop."""

    def test_importable(self):
        from bob3.run_loop import readiness_seed_sweep

        assert callable(readiness_seed_sweep)

    def test_accepts_project_id_string(self, db_path, project_id):
        from bob3.run_loop import readiness_seed_sweep

        result = readiness_seed_sweep(project_id)
        assert isinstance(result, int)

    def test_returns_zero_when_no_ready_features(self, db_path, project_id):
        from bob3.run_loop import readiness_seed_sweep

        result = readiness_seed_sweep(project_id)
        assert result == 0

    def test_returns_zero_for_unknown_project(self, db_path):
        from bob3.run_loop import readiness_seed_sweep

        result = readiness_seed_sweep("nonexistent-project-id-00000000")
        assert result == 0


class TestReadinessSeedSweepSeeding:
    """readiness_seed_sweep must seed features with readiness_score == 0.0."""

    def test_seeds_ready_feature_with_zero_readiness(self, db_path, project_id):
        from bob3.db import create_feature, get_feature
        from bob3.run_loop import readiness_seed_sweep

        # Create a ready feature with a good spec_quality_score but readiness at 0
        feature = create_feature(
            project_id=project_id,
            name="High Quality Ready Feature",
            status="ready",
            readiness_score=0.0,
            spec_quality_score=0.95,
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
        )

        seeded = readiness_seed_sweep(project_id)
        assert seeded >= 1

        updated = get_feature(feature.id)
        assert updated is not None
        assert updated.readiness_score > 0.0

    def test_skips_feature_with_nonzero_readiness(self, db_path, project_id):
        from bob3.db import create_feature, get_feature
        from bob3.run_loop import readiness_seed_sweep

        # Feature already has readiness seeded — sweep must skip it
        feature = create_feature(
            project_id=project_id,
            name="Already Seeded Feature",
            status="ready",
            readiness_score=0.85,
            spec_quality_score=0.95,
        )

        seeded = readiness_seed_sweep(project_id)
        assert seeded == 0

        # readiness_score must not change
        updated = get_feature(feature.id)
        assert updated is not None
        assert abs(updated.readiness_score - 0.85) < 1e-9

    def test_skips_pending_features(self, db_path, project_id):
        from bob3.db import create_feature, get_feature
        from bob3.run_loop import readiness_seed_sweep

        feature = create_feature(
            project_id=project_id,
            name="Pending Feature",
            status="pending",
            readiness_score=0.0,
            spec_quality_score=0.95,
        )

        seeded = readiness_seed_sweep(project_id)
        assert seeded == 0

        updated = get_feature(feature.id)
        assert updated is not None
        assert updated.readiness_score == 0.0

    def test_skips_executing_features(self, db_path, project_id):
        from bob3.db import create_feature, get_feature
        from bob3.run_loop import readiness_seed_sweep

        feature = create_feature(
            project_id=project_id,
            name="Executing Feature",
            status="executing",
            readiness_score=0.0,
            spec_quality_score=0.95,
        )

        seeded = readiness_seed_sweep(project_id)
        assert seeded == 0

        updated = get_feature(feature.id)
        assert updated is not None
        assert updated.readiness_score == 0.0

    def test_skips_completed_features(self, db_path, project_id):
        from bob3.db import create_feature, get_feature
        from bob3.run_loop import readiness_seed_sweep

        feature = create_feature(
            project_id=project_id,
            name="Completed Feature",
            status="completed",
            readiness_score=0.0,
            spec_quality_score=0.95,
        )

        seeded = readiness_seed_sweep(project_id)
        assert seeded == 0

        updated = get_feature(feature.id)
        assert updated is not None
        assert updated.readiness_score == 0.0

    def test_seeds_multiple_features_at_once(self, db_path, project_id):
        from bob3.db import create_feature, get_feature
        from bob3.run_loop import readiness_seed_sweep

        features = []
        for i in range(3):
            f = create_feature(
                project_id=project_id,
                name=f"MultiSeed Feature {i}",
                status="ready",
                readiness_score=0.0,
                spec_quality_score=0.95,
                acceptance_criteria=json.dumps([f"AC{i}_1", f"AC{i}_2", f"AC{i}_3"]),
            )
            features.append(f)

        seeded = readiness_seed_sweep(project_id)
        assert seeded >= 3

        for f in features:
            updated = get_feature(f.id)
            assert updated is not None
            assert updated.readiness_score > 0.0

    def test_idempotent_second_call_returns_zero(self, db_path, project_id):
        from bob3.db import create_feature
        from bob3.run_loop import readiness_seed_sweep

        create_feature(
            project_id=project_id,
            name="Idempotent Feature",
            status="ready",
            readiness_score=0.0,
            spec_quality_score=0.95,
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
        )

        first = readiness_seed_sweep(project_id)
        assert first >= 1

        second = readiness_seed_sweep(project_id)
        assert second == 0

    def test_only_seeds_features_for_given_project(self, db_path, project_id):
        from bob3.db import create_feature, create_project, get_feature
        from bob3.run_loop import readiness_seed_sweep

        other_project = create_project(
            name="Other Project",
            workspace_path="/tmp/other-project",
        )

        other_feature = create_feature(
            project_id=other_project.id,
            name="Other Project Feature",
            status="ready",
            readiness_score=0.0,
            spec_quality_score=0.95,
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
        )

        seeded = readiness_seed_sweep(project_id)
        assert seeded == 0

        other_updated = get_feature(other_feature.id)
        assert other_updated is not None
        assert other_updated.readiness_score == 0.0


class TestAssessFeatureConfidenceImport:
    """bob3.feature_assessment.assess_feature_confidence must be importable."""

    def test_importable(self):
        from bob3.feature_assessment import assess_feature_confidence

        assert callable(assess_feature_confidence)

    def test_returns_dict_with_readiness_key(self, db_path, project_id):
        from bob3.db import create_feature
        from bob3.feature_assessment import assess_feature_confidence

        feature = create_feature(
            project_id=project_id,
            name="Assess Test Feature",
            status="ready",
            spec_quality_score=0.95,
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
        )

        result = assess_feature_confidence(feature.id)
        assert isinstance(result, dict)
        assert "readiness_score" in result

    def test_standalone_feature_gets_high_readiness_from_spec_quality(self, db_path, project_id):
        from bob3.db import create_feature
        from bob3.feature_assessment import assess_feature_confidence

        feature = create_feature(
            project_id=project_id,
            name="Standalone High Quality Feature",
            description="Standalone feature with no integration keywords.",
            status="ready",
            spec_quality_score=0.95,
            acceptance_criteria=json.dumps(["AC1", "AC2", "AC3"]),
        )

        result = assess_feature_confidence(feature.id)
        # 0.95 * 0.92 = 0.874 for standalone
        assert result["readiness_score"] >= 0.80

    def test_nonexistent_feature_returns_zero_readiness(self, db_path):
        from bob3.feature_assessment import assess_feature_confidence

        result = assess_feature_confidence("nonexistent-feature-id")
        assert result["readiness_score"] == 0.0


class TestRunLoopIntegration:
    """Integration: readiness_seed_sweep is exposed in bob3.run_loop public API."""

    def test_readiness_seed_sweep_in_run_loop_module(self):
        import bob3.run_loop as rl

        assert hasattr(rl, "readiness_seed_sweep"), (
            "bob3.run_loop must export readiness_seed_sweep as a public function"
        )
        assert callable(rl.readiness_seed_sweep)

    def test_assess_feature_confidence_in_feature_assessment_module(self):
        import bob3.feature_assessment as fa

        assert hasattr(fa, "assess_feature_confidence"), (
            "bob3.feature_assessment must export assess_feature_confidence"
        )
        assert callable(fa.assess_feature_confidence)
