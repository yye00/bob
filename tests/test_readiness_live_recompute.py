"""Tests for AC: compute_live_readiness ignores persisted readiness_score.

A feature whose conf_impl=0.9, conf_spec=0.9, conf_test=0.9 must read
readiness=0.9 even if the persisted readiness_score column is 0.1 (decayed).
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database
    init_database()
    return p


@pytest.fixture()
def project_id(db_path):
    from bob.db import create_project
    project = create_project(name="Live Readiness Test", workspace_path="/tmp/test-lr")
    return project.id


class TestComputeLiveReadinessIgnoresPersistedScore:
    """compute_live_readiness must derive from components, not stored value."""

    def test_importable(self):
        from bob.db.readiness_recompute import compute_live_readiness
        assert callable(compute_live_readiness)

    def test_live_readiness_equals_mean_of_components(self, db_path, project_id):
        from bob.db import create_feature, update_feature
        from bob.db.readiness_recompute import compute_live_readiness

        feature = create_feature(
            project_id=project_id,
            name="High-conf feature",
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
        )
        # Manually force the persisted readiness_score to a decayed value
        update_feature(feature.id, readiness_score=0.1)

        result = compute_live_readiness(feature.id)
        # Should be mean(0.9, 0.9, 0.9) = 0.9, NOT the stored 0.1
        assert abs(result - 0.9) < 1e-9

    def test_live_readiness_reflects_current_components(self, db_path, project_id):
        from bob.db import create_feature, update_feature
        from bob.db.readiness_recompute import compute_live_readiness

        feature = create_feature(
            project_id=project_id,
            name="Updated components feature",
            conf_spec_understanding=0.6,
            conf_impl_correctness=0.6,
            conf_test_adequacy=0.6,
        )
        update_feature(feature.id, readiness_score=0.1)

        result = compute_live_readiness(feature.id)
        expected = (0.6 + 0.6 + 0.6) / 3
        assert abs(result - expected) < 1e-9

    def test_live_readiness_mixed_components(self, db_path, project_id):
        from bob.db import create_feature
        from bob.db.readiness_recompute import compute_live_readiness

        feature = create_feature(
            project_id=project_id,
            name="Mixed components",
            conf_spec_understanding=0.4,
            conf_impl_correctness=0.8,
            conf_test_adequacy=0.6,
        )
        result = compute_live_readiness(feature.id)
        expected = (0.4 + 0.8 + 0.6) / 3
        assert abs(result - expected) < 1e-9

    def test_live_readiness_returns_none_for_missing_feature(self, db_path):
        from bob.db.readiness_recompute import compute_live_readiness

        result = compute_live_readiness("nonexistent-feature-id")
        assert result is None

    def test_live_readiness_zero_components(self, db_path, project_id):
        from bob.db import create_feature
        from bob.db.readiness_recompute import compute_live_readiness

        feature = create_feature(
            project_id=project_id,
            name="Zero confidence feature",
        )
        result = compute_live_readiness(feature.id)
        assert result == 0.0

    def test_live_readiness_ignores_persisted_when_components_updated(self, db_path, project_id):
        from bob.db import create_feature, update_feature
        from bob.db.readiness_recompute import compute_live_readiness

        feature = create_feature(
            project_id=project_id,
            name="Decayed readiness feature",
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
        )
        # Simulate a _decay_confidence_after_failure that only wrote readiness_score
        update_feature(feature.id, readiness_score=0.1)

        live = compute_live_readiness(feature.id)
        # Components are still 0.9, so live readiness should be 0.9
        assert abs(live - 0.9) < 1e-9
