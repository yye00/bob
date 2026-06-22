"""Tests for F123: Cascade Update Dependent Features.

When a feature completes, auto-transition pending features to 'ready'
if ALL their dependencies are completed AND their readiness_score meets
the threshold for their risk_category.
"""

import pathlib

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database

    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Create a test project."""
    from bob3.db import create_project

    return create_project(name="Test Project", workspace_path="/tmp/test")


def _create_feature(project_id, feature_id, *, status="pending", risk_category="medium",
                     readiness_score=0.0, name=None):
    """Helper to create a feature with specific attributes."""
    from bob3.db import create_feature, update_feature

    feat = create_feature(
        project_id=project_id,
        name=name or f"Feature {feature_id}",
        description="Test feature",
        risk_category=risk_category,
    )
    # Overwrite the auto-generated ID with our deterministic one
    import sqlite3
    import os
    db_path = os.environ["BOB3_DATABASE_PATH"]
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE features SET id = ? WHERE id = ?", (feature_id, feat.id))
    conn.commit()
    conn.close()

    update_feature(feature_id, status=status, readiness_score=readiness_score)
    from bob3.db import get_feature
    return get_feature(feature_id)


def _add_dependency(feature_id, depends_on_id):
    """Helper to add a dependency between features."""
    from bob3.db import add_feature_dependency

    add_feature_dependency(feature_id=feature_id, depends_on_feature_id=depends_on_id)


class TestCascadeUpdateDependents:
    """Step 1-7: cascade_update_dependents() in db.py."""

    def test_function_exists(self, db_path):
        """Step 1: Function exists in db.py."""
        from bob3.db import cascade_update_dependents

        assert callable(cascade_update_dependents)

    def test_returns_list(self, project):
        """Step 7: Returns a list of feature IDs that were transitioned."""
        from bob3.db import cascade_update_dependents

        result = cascade_update_dependents("nonexistent-feature")
        assert isinstance(result, list)

    def test_single_dep_completed_transitions_to_ready(self, project):
        """Step 8: Feature A depends on B, B completes -> A becomes ready.

        A has readiness_score=0.85 (>= 0.80 medium threshold).
        B is completed.
        After cascade, A should become 'ready'.
        """
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        feat_a = _create_feature(project.id, "F_A", status="pending",
                                  readiness_score=0.85, risk_category="medium")
        _add_dependency("F_A", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "ready"

    def test_partial_deps_stays_pending(self, project):
        """Step 9: Feature A depends on B and C, only B completes -> A stays pending."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        feat_c = _create_feature(project.id, "F_C", status="pending")
        feat_a = _create_feature(project.id, "F_A", status="pending",
                                  readiness_score=0.85, risk_category="medium")
        _add_dependency("F_A", "F_B")
        _add_dependency("F_A", "F_C")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" not in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "pending"

    def test_all_deps_completed_transitions_to_ready(self, project):
        """Step 10: Feature A depends on B and C, both complete -> A becomes ready."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        feat_c = _create_feature(project.id, "F_C", status="completed")
        feat_a = _create_feature(project.id, "F_A", status="pending",
                                  readiness_score=0.85, risk_category="medium")
        _add_dependency("F_A", "F_B")
        _add_dependency("F_A", "F_C")

        transitioned = cascade_update_dependents("F_C")

        assert "F_A" in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "ready"

    def test_readiness_below_threshold_stays_pending(self, project):
        """Step 4: Readiness below threshold -> stays pending (not transitioned)."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        # readiness 0.5 is below medium threshold of 0.80
        feat_a = _create_feature(project.id, "F_A", status="pending",
                                  readiness_score=0.5, risk_category="medium")
        _add_dependency("F_A", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" not in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "pending"

    def test_low_risk_threshold(self, project):
        """Step 4: Low risk features need readiness >= 0.70."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        feat_a = _create_feature(project.id, "F_A", status="pending",
                                  readiness_score=0.72, risk_category="low")
        _add_dependency("F_A", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "ready"

    def test_high_risk_threshold(self, project):
        """Step 4: High risk features need readiness >= 0.90."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        # 0.85 is above medium but below high
        feat_a = _create_feature(project.id, "F_A", status="pending",
                                  readiness_score=0.85, risk_category="high")
        _add_dependency("F_A", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" not in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "pending"

    def test_critical_risk_threshold(self, project):
        """Step 4: Critical risk features need readiness >= 0.95."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        feat_a = _create_feature(project.id, "F_A", status="pending",
                                  readiness_score=0.96, risk_category="critical")
        _add_dependency("F_A", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "ready"

    def test_no_dependents_returns_empty(self, project):
        """Step 2: No dependents -> returns empty list."""
        from bob3.db import cascade_update_dependents

        feat_b = _create_feature(project.id, "F_B", status="completed")
        transitioned = cascade_update_dependents("F_B")
        assert transitioned == []

    def test_already_completed_not_transitioned(self, project):
        """Already completed features are not re-transitioned."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        feat_a = _create_feature(project.id, "F_A", status="completed",
                                  readiness_score=0.85, risk_category="medium")
        _add_dependency("F_A", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" not in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "completed"

    def test_multiple_dependents_transitioned(self, project):
        """Multiple dependent features can be transitioned at once."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        feat_a1 = _create_feature(project.id, "F_A1", status="pending",
                                   readiness_score=0.85, risk_category="medium")
        feat_a2 = _create_feature(project.id, "F_A2", status="pending",
                                   readiness_score=0.90, risk_category="medium")
        _add_dependency("F_A1", "F_B")
        _add_dependency("F_A2", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A1" in transitioned
        assert "F_A2" in transitioned

    def test_only_pending_features_transitioned(self, project):
        """Only 'pending' status features are candidates for transition."""
        from bob3.db import cascade_update_dependents, get_feature

        feat_b = _create_feature(project.id, "F_B", status="completed")
        # executing features should not be touched
        feat_a = _create_feature(project.id, "F_A", status="executing",
                                  readiness_score=0.85, risk_category="medium")
        _add_dependency("F_A", "F_B")

        transitioned = cascade_update_dependents("F_B")

        assert "F_A" not in transitioned
        updated_a = get_feature("F_A")
        assert updated_a.status == "executing"
