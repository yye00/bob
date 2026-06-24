"""Tests for F023: Query for features_ready view (respects dependencies and readiness)."""

import pathlib

import pytest


WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database

    init_database()
    return p


@pytest.fixture()
def project_id(db_path):
    """Create a project and return its ID for use as a foreign key."""
    from bob.db import create_project

    project = create_project(
        name="Ready Features Test Project",
        workspace_path="/tmp/test-ready-features",
    )
    return project.id


def _make_ready_feature(project_id, name, priority=100, risk_category="medium"):
    """Helper to create a feature that meets readiness thresholds.

    Sets status='ready', high confidence scores, and computes readiness.
    """
    from bob.db import calculate_readiness, create_feature, update_feature

    feature = create_feature(
        project_id=project_id,
        name=name,
        priority=priority,
        risk_category=risk_category,
        status="ready",
    )
    update_feature(
        feature.id,
        conf_spec_understanding=0.95,
        conf_impl_correctness=0.95,
        conf_test_adequacy=0.95,
    )
    calculate_readiness(feature.id)
    return feature


# ============================================================
# Step 1: get_ready_features() function exists and uses view
# ============================================================


class TestGetReadyFeaturesExists:
    """get_ready_features() is importable and callable."""

    def test_get_ready_features_importable(self):
        from bob.db import get_ready_features

        assert callable(get_ready_features)

    def test_get_ready_features_returns_list(self, db_path, project_id):
        from bob.db import get_ready_features

        result = get_ready_features(project_id)
        assert isinstance(result, list)

    def test_get_ready_features_returns_feature_models(self, db_path, project_id):
        from bob.db import get_ready_features

        _make_ready_feature(project_id, "Ready Feature")
        result = get_ready_features(project_id)
        assert len(result) == 1

        from bob.models import Feature

        assert isinstance(result[0], Feature)

    def test_get_ready_features_empty_project(self, db_path, project_id):
        from bob.db import get_ready_features

        result = get_ready_features(project_id)
        assert result == []


# ============================================================
# Step 2 & 3: Feature chain A->B->C where only A is ready
# ============================================================


class TestDependencyChain:
    """Create feature chain A->B->C where only A is ready."""

    def test_chain_only_a_returned(self, db_path, project_id):
        """A has no deps, B depends on A, C depends on B.
        Only A should be returned as ready."""
        from bob.db import add_feature_dependency, get_ready_features

        feat_a = _make_ready_feature(project_id, "Feature A", priority=10)
        feat_b = _make_ready_feature(project_id, "Feature B", priority=20)
        feat_c = _make_ready_feature(project_id, "Feature C", priority=30)

        # B depends on A, C depends on B
        add_feature_dependency(feature_id=feat_b.id, depends_on_feature_id=feat_a.id)
        add_feature_dependency(feature_id=feat_c.id, depends_on_feature_id=feat_b.id)

        ready = get_ready_features(project_id)
        ready_ids = [f.id for f in ready]

        assert feat_a.id in ready_ids
        assert feat_b.id not in ready_ids
        assert feat_c.id not in ready_ids

    def test_chain_only_a_returned_count(self, db_path, project_id):
        """Exactly one feature should be returned."""
        from bob.db import add_feature_dependency, get_ready_features

        feat_a = _make_ready_feature(project_id, "Feature A")
        feat_b = _make_ready_feature(project_id, "Feature B")
        feat_c = _make_ready_feature(project_id, "Feature C")

        add_feature_dependency(feature_id=feat_b.id, depends_on_feature_id=feat_a.id)
        add_feature_dependency(feature_id=feat_c.id, depends_on_feature_id=feat_b.id)

        ready = get_ready_features(project_id)
        assert len(ready) == 1
        assert ready[0].id == feat_a.id

    def test_feature_not_ready_status_excluded(self, db_path, project_id):
        """Features with status != 'ready' are excluded even with no deps."""
        from bob.db import (
            calculate_readiness,
            create_feature,
            get_ready_features,
            update_feature,
        )

        # Feature with 'pending' status despite high readiness
        feature = create_feature(
            project_id=project_id,
            name="Pending Feature",
            status="pending",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.95,
            conf_impl_correctness=0.95,
            conf_test_adequacy=0.95,
        )
        calculate_readiness(feature.id)

        ready = get_ready_features(project_id)
        assert len(ready) == 0

    def test_feature_below_threshold_excluded(self, db_path, project_id):
        """Features below readiness threshold are excluded."""
        from bob.db import (
            calculate_readiness,
            create_feature,
            get_ready_features,
            update_feature,
        )

        feature = create_feature(
            project_id=project_id,
            name="Low Readiness",
            status="ready",
            risk_category="medium",
        )
        update_feature(
            feature.id,
            conf_spec_understanding=0.5,
            conf_impl_correctness=0.5,
            conf_test_adequacy=0.5,
        )
        calculate_readiness(feature.id)

        ready = get_ready_features(project_id)
        assert len(ready) == 0


# ============================================================
# Step 4: Mark A complete, verify B becomes ready
# ============================================================


class TestCompletionUnblocks:
    """When A is completed, B should become ready (if it meets thresholds)."""

    def test_completing_a_makes_b_ready(self, db_path, project_id):
        """After A is completed, B (which depends on A) should appear in ready list."""
        from bob.db import add_feature_dependency, get_ready_features, update_feature

        feat_a = _make_ready_feature(project_id, "Feature A", priority=10)
        feat_b = _make_ready_feature(project_id, "Feature B", priority=20)
        feat_c = _make_ready_feature(project_id, "Feature C", priority=30)

        add_feature_dependency(feature_id=feat_b.id, depends_on_feature_id=feat_a.id)
        add_feature_dependency(feature_id=feat_c.id, depends_on_feature_id=feat_b.id)

        # Initially only A is ready
        ready = get_ready_features(project_id)
        assert len(ready) == 1
        assert ready[0].id == feat_a.id

        # Complete A
        update_feature(feat_a.id, status="completed")

        # Now B should be ready (its dependency A is completed)
        ready = get_ready_features(project_id)
        ready_ids = [f.id for f in ready]
        assert feat_b.id in ready_ids
        # C should still not be ready (depends on B which is not completed)
        assert feat_c.id not in ready_ids

    def test_completing_a_and_b_makes_c_ready(self, db_path, project_id):
        """After both A and B completed, C should appear in ready list."""
        from bob.db import add_feature_dependency, get_ready_features, update_feature

        feat_a = _make_ready_feature(project_id, "Feature A", priority=10)
        feat_b = _make_ready_feature(project_id, "Feature B", priority=20)
        feat_c = _make_ready_feature(project_id, "Feature C", priority=30)

        add_feature_dependency(feature_id=feat_b.id, depends_on_feature_id=feat_a.id)
        add_feature_dependency(feature_id=feat_c.id, depends_on_feature_id=feat_b.id)

        # Complete A and B
        update_feature(feat_a.id, status="completed")
        update_feature(feat_b.id, status="completed")

        # Now C should be ready
        ready = get_ready_features(project_id)
        ready_ids = [f.id for f in ready]
        assert feat_c.id in ready_ids

    def test_multiple_dependencies_all_must_be_complete(self, db_path, project_id):
        """Feature with multiple deps only becomes ready when ALL deps complete."""
        from bob.db import add_feature_dependency, get_ready_features, update_feature

        feat_a = _make_ready_feature(project_id, "Feature A", priority=10)
        feat_b = _make_ready_feature(project_id, "Feature B", priority=20)
        feat_d = _make_ready_feature(project_id, "Feature D", priority=40)

        # D depends on both A and B
        add_feature_dependency(feature_id=feat_d.id, depends_on_feature_id=feat_a.id)
        add_feature_dependency(feature_id=feat_d.id, depends_on_feature_id=feat_b.id)

        # Complete only A
        update_feature(feat_a.id, status="completed")

        # D should NOT be ready (B is not completed)
        ready = get_ready_features(project_id)
        ready_ids = [f.id for f in ready]
        assert feat_d.id not in ready_ids

        # Complete B too
        update_feature(feat_b.id, status="completed")

        # Now D should be ready
        ready = get_ready_features(project_id)
        ready_ids = [f.id for f in ready]
        assert feat_d.id in ready_ids


# ============================================================
# Step 5: Verify ordering by priority works
# ============================================================


class TestPriorityOrdering:
    """Ready features are returned ordered by priority (ascending)."""

    def test_ordering_by_priority_ascending(self, db_path, project_id):
        """Features should be ordered by priority (lower = higher priority)."""
        from bob.db import get_ready_features

        feat_high = _make_ready_feature(project_id, "High Priority", priority=10)
        feat_med = _make_ready_feature(project_id, "Medium Priority", priority=50)
        feat_low = _make_ready_feature(project_id, "Low Priority", priority=100)

        ready = get_ready_features(project_id)
        assert len(ready) == 3
        assert ready[0].id == feat_high.id
        assert ready[1].id == feat_med.id
        assert ready[2].id == feat_low.id

    def test_ordering_same_priority_by_created_at(self, db_path, project_id):
        """Features with same priority should be ordered by creation time."""
        import time

        from bob.db import get_ready_features

        feat_first = _make_ready_feature(project_id, "First Created", priority=50)
        time.sleep(0.01)  # Ensure different created_at
        feat_second = _make_ready_feature(project_id, "Second Created", priority=50)

        ready = get_ready_features(project_id)
        assert len(ready) == 2
        assert ready[0].id == feat_first.id
        assert ready[1].id == feat_second.id

    def test_ordering_mixed_priorities_with_deps(self, db_path, project_id):
        """Priority ordering is maintained even with dependency filtering."""
        from bob.db import add_feature_dependency, get_ready_features, update_feature

        feat_a = _make_ready_feature(project_id, "Feature A", priority=50)
        feat_b = _make_ready_feature(project_id, "Feature B", priority=10)
        feat_c = _make_ready_feature(project_id, "Feature C", priority=30)

        # B depends on A (so B is excluded)
        add_feature_dependency(feature_id=feat_b.id, depends_on_feature_id=feat_a.id)

        ready = get_ready_features(project_id)
        # Only A and C should be returned (B is blocked)
        assert len(ready) == 2
        # C (priority 30) before A (priority 50)
        assert ready[0].id == feat_c.id
        assert ready[1].id == feat_a.id


# ============================================================
# Edge cases: vetoed features, different risk categories
# ============================================================


class TestEdgeCases:
    """Edge cases for the features_ready view."""

    def test_vetoed_feature_excluded(self, db_path, project_id):
        """Features with active veto are excluded from ready list."""
        import uuid

        import sqlite3

        from bob.db import get_ready_features

        feat = _make_ready_feature(project_id, "Vetoed Feature")

        # Insert a veto review directly
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """INSERT INTO review_history
                   (id, project_id, feature_id, reviewer_id, veto_active)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), project_id, feat.id, "reviewer-1", True),
            )
            conn.commit()
        finally:
            conn.close()

        ready = get_ready_features(project_id)
        ready_ids = [f.id for f in ready]
        assert feat.id not in ready_ids

    def test_different_risk_categories(self, db_path, project_id):
        """Features with different risk categories use correct thresholds."""
        from bob.db import (
            calculate_readiness,
            create_feature,
            get_ready_features,
            update_feature,
        )

        # Low risk feature with 0.75 readiness (above 0.70 threshold)
        feat_low = create_feature(
            project_id=project_id,
            name="Low Risk",
            status="ready",
            risk_category="low",
            priority=10,
        )
        update_feature(
            feat_low.id,
            conf_spec_understanding=0.75,
            conf_impl_correctness=0.75,
            conf_test_adequacy=0.75,
        )
        calculate_readiness(feat_low.id)

        # High risk feature with 0.85 readiness (below 0.90 threshold)
        feat_high = create_feature(
            project_id=project_id,
            name="High Risk",
            status="ready",
            risk_category="high",
            priority=20,
        )
        update_feature(
            feat_high.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
        )
        calculate_readiness(feat_high.id)

        ready = get_ready_features(project_id)
        ready_ids = [f.id for f in ready]

        # Low risk is ready (0.75 >= 0.70)
        assert feat_low.id in ready_ids
        # High risk is NOT ready (0.85 < 0.90)
        assert feat_high.id not in ready_ids

    def test_scoped_to_project(self, db_path, project_id):
        """get_ready_features only returns features for the given project."""
        from bob.db import create_project, get_ready_features

        other_project = create_project(
            name="Other Project",
            workspace_path="/tmp/other-project",
        )
        _make_ready_feature(project_id, "My Feature", priority=10)
        _make_ready_feature(other_project.id, "Other Feature", priority=10)

        ready = get_ready_features(project_id)
        assert len(ready) == 1
        assert ready[0].name == "My Feature"

        ready_other = get_ready_features(other_project.id)
        assert len(ready_other) == 1
        assert ready_other[0].name == "Other Feature"
