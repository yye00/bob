"""Tests for AC: snapshot_baseline_confidence at creation captures original component triple.

Error/boundary: missing column raises ValueError.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database
    init_database()
    return p


@pytest.fixture()
def project_id(db_path):
    from bob3.db import create_project
    project = create_project(name="Baseline Snapshot Test", workspace_path="/tmp/test-bsn")
    return project.id


class TestSnapshotBaselineConfidence:
    """snapshot_baseline_confidence captures the creation-time triple."""

    def test_importable(self):
        from bob3.db.readiness_recompute import snapshot_baseline_confidence
        assert callable(snapshot_baseline_confidence)

    def test_snapshot_captures_components(self, db_path, project_id):
        from bob3.db import create_feature
        from bob3.db.readiness_recompute import (
            snapshot_baseline_confidence,
            get_baseline_confidence,
        )

        feature = create_feature(
            project_id=project_id,
            name="Snapshot feature",
            conf_spec_understanding=0.75,
            conf_impl_correctness=0.80,
            conf_test_adequacy=0.70,
        )
        snapshot_baseline_confidence(feature.id)

        baseline = get_baseline_confidence(feature.id)
        assert baseline is not None
        assert abs(baseline["conf_spec_understanding"] - 0.75) < 1e-9
        assert abs(baseline["conf_impl_correctness"] - 0.80) < 1e-9
        assert abs(baseline["conf_test_adequacy"] - 0.70) < 1e-9

    def test_snapshot_for_missing_feature_raises_value_error(self, db_path):
        from bob3.db.readiness_recompute import snapshot_baseline_confidence

        with pytest.raises(ValueError, match="baseline"):
            snapshot_baseline_confidence("nonexistent-feature-id")

    def test_snapshot_idempotent_second_call_overwrites(self, db_path, project_id):
        """Calling snapshot twice: second call updates the stored baseline."""
        from bob3.db import create_feature, update_feature
        from bob3.db.readiness_recompute import (
            snapshot_baseline_confidence,
            get_baseline_confidence,
        )

        feature = create_feature(
            project_id=project_id,
            name="Overwrite baseline feature",
            conf_spec_understanding=0.80,
            conf_impl_correctness=0.80,
            conf_test_adequacy=0.80,
        )
        snapshot_baseline_confidence(feature.id)

        # Update components then snapshot again
        update_feature(
            feature.id,
            conf_spec_understanding=0.60,
            conf_impl_correctness=0.60,
            conf_test_adequacy=0.60,
        )
        snapshot_baseline_confidence(feature.id)

        baseline = get_baseline_confidence(feature.id)
        # Should reflect the updated values, not the original
        assert abs(baseline["conf_spec_understanding"] - 0.60) < 1e-9

    def test_get_baseline_returns_none_when_not_snapshotted(self, db_path, project_id):
        from bob3.db import create_feature
        from bob3.db.readiness_recompute import get_baseline_confidence

        feature = create_feature(
            project_id=project_id,
            name="No snapshot feature",
        )
        baseline = get_baseline_confidence(feature.id)
        assert baseline is None

    def test_restore_uses_snapshotted_values(self, db_path, project_id):
        from bob3.db import create_feature, update_feature, get_feature
        from bob3.db.readiness_recompute import (
            snapshot_baseline_confidence,
            restore_baseline_confidence,
        )

        feature = create_feature(
            project_id=project_id,
            name="Restore uses snapshot",
            conf_spec_understanding=0.90,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.88,
        )
        snapshot_baseline_confidence(feature.id)

        # Decay
        update_feature(
            feature.id,
            conf_spec_understanding=0.50,
            conf_impl_correctness=0.50,
            conf_test_adequacy=0.50,
        )

        restore_baseline_confidence(feature.id)

        restored = get_feature(feature.id)
        assert abs(restored.conf_spec_understanding - 0.90) < 1e-9
        assert abs(restored.conf_impl_correctness - 0.85) < 1e-9
        assert abs(restored.conf_test_adequacy - 0.88) < 1e-9

    def test_snapshot_zero_values(self, db_path, project_id):
        from bob3.db import create_feature
        from bob3.db.readiness_recompute import (
            snapshot_baseline_confidence,
            get_baseline_confidence,
        )

        feature = create_feature(
            project_id=project_id,
            name="Zero conf feature",
        )
        snapshot_baseline_confidence(feature.id)

        baseline = get_baseline_confidence(feature.id)
        assert baseline is not None
        assert baseline["conf_spec_understanding"] == 0.0
        assert baseline["conf_impl_correctness"] == 0.0
        assert baseline["conf_test_adequacy"] == 0.0
