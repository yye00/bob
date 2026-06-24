"""Tests for AC: 2 successive failures decay components; baseline restore returns readiness.

After 2 failures, components decay. A subsequent restore_baseline_confidence
must return readiness to the original value.
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
    project = create_project(name="Decay No Ratchet Test", workspace_path="/tmp/test-dnr")
    return project.id


class TestDecayNoRatchet:
    """Decay lowers components; restore_baseline brings readiness back."""

    def test_snapshot_then_restore_returns_original_readiness(self, db_path, project_id):
        from bob.db import create_feature, update_feature
        from bob.db.readiness_recompute import (
            compute_live_readiness,
            snapshot_baseline_confidence,
            restore_baseline_confidence,
        )

        feature = create_feature(
            project_id=project_id,
            name="Decay restore test",
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )
        # Snapshot baseline at creation
        snapshot_baseline_confidence(feature.id)

        # Simulate 2 failures: decay components (not readiness_score itself)
        decay = 0.15
        update_feature(
            feature.id,
            conf_spec_understanding=max(0.0, 0.85 - decay),
            conf_impl_correctness=max(0.0, 0.85 - decay),
            conf_test_adequacy=max(0.0, 0.85 - decay),
        )
        decayed_readiness = compute_live_readiness(feature.id)
        expected_decayed = (0.70 + 0.70 + 0.70) / 3
        assert abs(decayed_readiness - expected_decayed) < 1e-9

        # Second failure
        update_feature(
            feature.id,
            conf_spec_understanding=max(0.0, 0.70 - decay),
            conf_impl_correctness=max(0.0, 0.70 - decay),
            conf_test_adequacy=max(0.0, 0.70 - decay),
        )
        doubly_decayed = compute_live_readiness(feature.id)
        expected_doubly = (0.55 + 0.55 + 0.55) / 3
        assert abs(doubly_decayed - expected_doubly) < 1e-9

        # Now restore baseline
        restore_baseline_confidence(feature.id)
        restored_readiness = compute_live_readiness(feature.id)
        # Should be back to original mean(0.85, 0.85, 0.85)
        assert abs(restored_readiness - 0.85) < 1e-9

    def test_decay_components_readiness_drops_monotonically(self, db_path, project_id):
        from bob.db import create_feature, update_feature
        from bob.db.readiness_recompute import compute_live_readiness

        feature = create_feature(
            project_id=project_id,
            name="Monotonic decay feature",
            conf_spec_understanding=0.9,
            conf_impl_correctness=0.9,
            conf_test_adequacy=0.9,
        )
        r0 = compute_live_readiness(feature.id)
        assert abs(r0 - 0.9) < 1e-9

        # First decay
        update_feature(
            feature.id,
            conf_spec_understanding=0.75,
            conf_impl_correctness=0.75,
            conf_test_adequacy=0.75,
        )
        r1 = compute_live_readiness(feature.id)
        assert r1 < r0

        # Second decay
        update_feature(
            feature.id,
            conf_spec_understanding=0.60,
            conf_impl_correctness=0.60,
            conf_test_adequacy=0.60,
        )
        r2 = compute_live_readiness(feature.id)
        assert r2 < r1

    def test_restore_after_no_snapshot_raises_value_error(self, db_path, project_id):
        from bob.db import create_feature
        from bob.db.readiness_recompute import restore_baseline_confidence

        feature = create_feature(
            project_id=project_id,
            name="No snapshot feature",
        )
        # No snapshot stored — should raise ValueError
        with pytest.raises(ValueError, match="baseline"):
            restore_baseline_confidence(feature.id)

    def test_restore_for_missing_feature_raises_value_error(self, db_path):
        from bob.db.readiness_recompute import restore_baseline_confidence

        with pytest.raises(ValueError):
            restore_baseline_confidence("nonexistent-id")

    def test_readiness_not_ratcheted_after_infra_restore(self, db_path, project_id):
        """After restore, live readiness == original, not the ratcheted value."""
        from bob.db import create_feature, update_feature
        from bob.db.readiness_recompute import (
            compute_live_readiness,
            snapshot_baseline_confidence,
            restore_baseline_confidence,
        )

        feature = create_feature(
            project_id=project_id,
            name="Infra ratchet escape",
            conf_spec_understanding=0.80,
            conf_impl_correctness=0.80,
            conf_test_adequacy=0.80,
        )
        snapshot_baseline_confidence(feature.id)

        # Simulate decay from failures
        update_feature(
            feature.id,
            conf_spec_understanding=0.50,
            conf_impl_correctness=0.50,
            conf_test_adequacy=0.50,
            # Also write a low readiness_score to the DB column (like old code did)
            readiness_score=0.35,
        )

        # Before restore: live readiness is from components (0.50), not readiness_score
        live_before = compute_live_readiness(feature.id)
        assert abs(live_before - 0.50) < 1e-9

        # After restore: live readiness is from baseline (0.80)
        restore_baseline_confidence(feature.id)
        live_after = compute_live_readiness(feature.id)
        assert abs(live_after - 0.80) < 1e-9
