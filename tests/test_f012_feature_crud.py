"""Tests for F012: Database CRUD operations for features table."""

import json
import pathlib
import sqlite3
from datetime import datetime

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
        name="Test Project",
        workspace_path="/tmp/test",
    )
    return project.id


# ============================================================
# Step 1: create_feature()
# ============================================================


class TestCreateFeature:
    """create_feature() inserts a new feature and returns it."""

    def test_create_feature_returns_feature_model(self, db_path, project_id):
        from bob.db import create_feature
        from bob.models import Feature

        feature = create_feature(
            project_id=project_id,
            name="Test Feature",
        )
        assert isinstance(feature, Feature)

    def test_create_feature_sets_id(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="ID Feature",
        )
        assert feature.id is not None
        assert len(feature.id) > 0

    def test_create_feature_persists_to_database(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="Persisted Feature",
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT name, project_id FROM features WHERE id = ?",
                (feature.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "Persisted Feature"
            assert row[1] == project_id
        finally:
            conn.close()

    def test_create_feature_with_optional_fields(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="Full Feature",
            description="A detailed feature",
            acceptance_criteria=json.dumps(["criterion 1", "criterion 2"]),
            priority=50,
            risk_category="high",
        )
        assert feature.description == "A detailed feature"
        assert feature.acceptance_criteria == json.dumps(["criterion 1", "criterion 2"])
        assert feature.priority == 50
        assert feature.risk_category == "high"

    def test_create_feature_default_status_is_pending(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="Default Status",
        )
        assert feature.status == "pending"

    def test_create_feature_default_priority(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="Default Priority",
        )
        assert feature.priority == 100

    def test_create_feature_sets_timestamps(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="Timestamp Feature",
        )
        assert feature.created_at is not None
        assert feature.updated_at is not None

    def test_create_feature_with_parent(self, db_path, project_id):
        from bob.db import create_feature

        parent = create_feature(
            project_id=project_id,
            name="Parent Feature",
        )
        child = create_feature(
            project_id=project_id,
            name="Child Feature",
            parent_feature_id=parent.id,
            decomposition_depth=1,
        )
        assert child.parent_feature_id == parent.id
        assert child.decomposition_depth == 1

    def test_create_feature_with_explicit_id(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="Explicit ID",
            feature_id="F001",
        )
        assert feature.id == "F001"

    def test_create_feature_default_confidences(self, db_path, project_id):
        from bob.db import create_feature

        feature = create_feature(
            project_id=project_id,
            name="Confidence Feature",
        )
        assert feature.conf_spec_understanding == 0.0
        assert feature.conf_impl_correctness == 0.0
        assert feature.conf_test_adequacy == 0.0
        assert feature.readiness_score == 0.0


# ============================================================
# Step 2: get_feature()
# ============================================================


class TestGetFeature:
    """get_feature() retrieves a feature by ID."""

    def test_get_feature_returns_feature(self, db_path, project_id):
        from bob.db import create_feature, get_feature
        from bob.models import Feature

        created = create_feature(
            project_id=project_id,
            name="Get Me",
        )
        fetched = get_feature(created.id)
        assert isinstance(fetched, Feature)

    def test_get_feature_has_correct_fields(self, db_path, project_id):
        from bob.db import create_feature, get_feature

        created = create_feature(
            project_id=project_id,
            name="Detail Feature",
            description="Some desc",
            priority=25,
            risk_category="low",
        )
        fetched = get_feature(created.id)
        assert fetched.name == "Detail Feature"
        assert fetched.project_id == project_id
        assert fetched.description == "Some desc"
        assert fetched.priority == 25
        assert fetched.risk_category == "low"

    def test_get_feature_not_found_returns_none(self, db_path):
        from bob.db import get_feature

        result = get_feature("nonexistent-id")
        assert result is None

    def test_get_feature_preserves_id(self, db_path, project_id):
        from bob.db import create_feature, get_feature

        created = create_feature(
            project_id=project_id,
            name="ID Test",
        )
        fetched = get_feature(created.id)
        assert fetched.id == created.id


# ============================================================
# Step 3: update_feature()
# ============================================================


class TestUpdateFeature:
    """update_feature() modifies existing feature fields."""

    def test_update_feature_changes_name(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Old Name")
        update_feature(feature.id, name="New Name")
        fetched = get_feature(feature.id)
        assert fetched.name == "New Name"

    def test_update_feature_changes_status(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Status Test")
        update_feature(feature.id, status="ready")
        fetched = get_feature(feature.id)
        assert fetched.status == "ready"

    def test_update_feature_changes_description(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Desc Test")
        update_feature(feature.id, description="Updated desc")
        fetched = get_feature(feature.id)
        assert fetched.description == "Updated desc"

    def test_update_feature_changes_priority(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Priority Test")
        update_feature(feature.id, priority=10)
        fetched = get_feature(feature.id)
        assert fetched.priority == 10

    def test_update_feature_changes_confidence(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Conf Test")
        update_feature(
            feature.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.9,
        )
        fetched = get_feature(feature.id)
        assert fetched.conf_spec_understanding == 0.8
        assert fetched.conf_impl_correctness == 0.7
        assert fetched.conf_test_adequacy == 0.9

    def test_update_feature_changes_readiness(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Readiness Test")
        update_feature(feature.id, readiness_score=0.85)
        fetched = get_feature(feature.id)
        assert fetched.readiness_score == 0.85

    def test_update_feature_returns_updated_feature(self, db_path, project_id):
        from bob.db import create_feature, update_feature
        from bob.models import Feature

        feature = create_feature(project_id=project_id, name="Return Test")
        updated = update_feature(feature.id, name="Updated")
        assert isinstance(updated, Feature)
        assert updated.name == "Updated"

    def test_update_feature_not_found_returns_none(self, db_path):
        from bob.db import update_feature

        result = update_feature("nonexistent-id", name="Ghost")
        assert result is None

    def test_update_feature_updates_timestamp(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature
        import time

        feature = create_feature(project_id=project_id, name="TS Test")
        original_updated = feature.updated_at
        time.sleep(0.05)
        update_feature(feature.id, name="TS Updated")
        fetched = get_feature(feature.id)
        assert fetched.updated_at >= original_updated

    def test_update_feature_multiple_fields(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Multi Test")
        update_feature(
            feature.id,
            name="Multi Updated",
            status="completed",
            description="Done",
            priority=1,
        )
        fetched = get_feature(feature.id)
        assert fetched.name == "Multi Updated"
        assert fetched.status == "completed"
        assert fetched.description == "Done"
        assert fetched.priority == 1

    def test_update_feature_refinement_tracking(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Refine Test")
        update_feature(
            feature.id,
            refinement_attempts=2,
            last_improvement_type="spec_clarification",
            research_iterations=1,
        )
        fetched = get_feature(feature.id)
        assert fetched.refinement_attempts == 2
        assert fetched.last_improvement_type == "spec_clarification"
        assert fetched.research_iterations == 1

    def test_update_feature_size_limits(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Size Test")
        update_feature(
            feature.id,
            estimated_lines_of_code=200,
            estimated_files_touched=3,
            estimated_complexity=5,
            exceeds_size_limits=True,
            size_limit_justification="Approved by architect",
        )
        fetched = get_feature(feature.id)
        assert fetched.estimated_lines_of_code == 200
        assert fetched.estimated_files_touched == 3
        assert fetched.estimated_complexity == 5
        assert fetched.exceeds_size_limits is True
        assert fetched.size_limit_justification == "Approved by architect"

    def test_update_feature_completion_tracking(self, db_path, project_id):
        from bob.db import create_feature, get_feature, update_feature

        feature = create_feature(project_id=project_id, name="Completion Test")
        update_feature(
            feature.id,
            tasks_completed=3,
            tasks_total=5,
        )
        fetched = get_feature(feature.id)
        assert fetched.tasks_completed == 3
        assert fetched.tasks_total == 5


# ============================================================
# Step 4: list_features() with filtering
# ============================================================


class TestListFeatures:
    """list_features() returns features with optional filtering."""

    def test_list_features_empty(self, db_path, project_id):
        from bob.db import list_features

        features = list_features(project_id=project_id)
        assert features == []

    def test_list_features_returns_all_for_project(self, db_path, project_id):
        from bob.db import create_feature, list_features

        create_feature(project_id=project_id, name="Feature A")
        create_feature(project_id=project_id, name="Feature B")
        create_feature(project_id=project_id, name="Feature C")

        features = list_features(project_id=project_id)
        assert len(features) == 3
        names = {f.name for f in features}
        assert names == {"Feature A", "Feature B", "Feature C"}

    def test_list_features_returns_feature_models(self, db_path, project_id):
        from bob.db import create_feature, list_features
        from bob.models import Feature

        create_feature(project_id=project_id, name="Model Test")
        features = list_features(project_id=project_id)
        assert all(isinstance(f, Feature) for f in features)

    def test_list_features_filter_by_status(self, db_path, project_id):
        from bob.db import create_feature, update_feature, list_features

        f1 = create_feature(project_id=project_id, name="Pending Feature")
        f2 = create_feature(project_id=project_id, name="Ready Feature")
        update_feature(f2.id, status="ready")

        pending = list_features(project_id=project_id, status="pending")
        assert len(pending) == 1
        assert pending[0].name == "Pending Feature"

        ready = list_features(project_id=project_id, status="ready")
        assert len(ready) == 1
        assert ready[0].name == "Ready Feature"

    def test_list_features_ordered_by_priority(self, db_path, project_id):
        from bob.db import create_feature, list_features

        create_feature(project_id=project_id, name="Low Priority", priority=200)
        create_feature(project_id=project_id, name="High Priority", priority=10)
        create_feature(project_id=project_id, name="Medium Priority", priority=50)

        features = list_features(project_id=project_id)
        assert features[0].name == "High Priority"
        assert features[1].name == "Medium Priority"
        assert features[2].name == "Low Priority"

    def test_list_features_only_returns_project_features(self, db_path):
        from bob.db import create_feature, create_project, list_features

        p1 = create_project(name="Project 1", workspace_path="/tmp/p1")
        p2 = create_project(name="Project 2", workspace_path="/tmp/p2")
        create_feature(project_id=p1.id, name="Feature P1")
        create_feature(project_id=p2.id, name="Feature P2")

        features_p1 = list_features(project_id=p1.id)
        assert len(features_p1) == 1
        assert features_p1[0].name == "Feature P1"

    def test_list_features_filter_by_parent(self, db_path, project_id):
        from bob.db import create_feature, list_features

        parent = create_feature(project_id=project_id, name="Parent")
        create_feature(
            project_id=project_id,
            name="Child 1",
            parent_feature_id=parent.id,
        )
        create_feature(
            project_id=project_id,
            name="Child 2",
            parent_feature_id=parent.id,
        )
        create_feature(project_id=project_id, name="No Parent")

        children = list_features(
            project_id=project_id,
            parent_feature_id=parent.id,
        )
        assert len(children) == 2
        names = {f.name for f in children}
        assert names == {"Child 1", "Child 2"}


# ============================================================
# Step 5: Feature dependency tracking
# ============================================================


class TestFeatureDependencies:
    """Feature dependency tracking: add, list, and remove dependencies."""

    def test_add_feature_dependency(self, db_path, project_id):
        from bob.db import create_feature, add_feature_dependency

        f1 = create_feature(project_id=project_id, name="Feature 1")
        f2 = create_feature(project_id=project_id, name="Feature 2")

        add_feature_dependency(feature_id=f2.id, depends_on_feature_id=f1.id)

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT feature_id, depends_on_feature_id FROM feature_dependencies "
                "WHERE feature_id = ? AND depends_on_feature_id = ?",
                (f2.id, f1.id),
            )
            row = cursor.fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_get_feature_dependencies(self, db_path, project_id):
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_feature_dependencies,
        )

        f1 = create_feature(project_id=project_id, name="Dep A")
        f2 = create_feature(project_id=project_id, name="Dep B")
        f3 = create_feature(project_id=project_id, name="Depends on A and B")

        add_feature_dependency(feature_id=f3.id, depends_on_feature_id=f1.id)
        add_feature_dependency(feature_id=f3.id, depends_on_feature_id=f2.id)

        deps = get_feature_dependencies(f3.id)
        assert len(deps) == 2
        dep_ids = {d.depends_on_feature_id for d in deps}
        assert dep_ids == {f1.id, f2.id}

    def test_get_feature_dependencies_empty(self, db_path, project_id):
        from bob.db import create_feature, get_feature_dependencies

        feature = create_feature(project_id=project_id, name="No Deps")
        deps = get_feature_dependencies(feature.id)
        assert deps == []

    def test_get_feature_dependents(self, db_path, project_id):
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_feature_dependents,
        )

        f1 = create_feature(project_id=project_id, name="Base Feature")
        f2 = create_feature(project_id=project_id, name="Depends on Base 1")
        f3 = create_feature(project_id=project_id, name="Depends on Base 2")

        add_feature_dependency(feature_id=f2.id, depends_on_feature_id=f1.id)
        add_feature_dependency(feature_id=f3.id, depends_on_feature_id=f1.id)

        dependents = get_feature_dependents(f1.id)
        assert len(dependents) == 2
        dep_ids = {d.feature_id for d in dependents}
        assert dep_ids == {f2.id, f3.id}

    def test_remove_feature_dependency(self, db_path, project_id):
        from bob.db import (
            create_feature,
            add_feature_dependency,
            remove_feature_dependency,
            get_feature_dependencies,
        )

        f1 = create_feature(project_id=project_id, name="Base")
        f2 = create_feature(project_id=project_id, name="Dependent")
        add_feature_dependency(feature_id=f2.id, depends_on_feature_id=f1.id)

        remove_feature_dependency(feature_id=f2.id, depends_on_feature_id=f1.id)
        deps = get_feature_dependencies(f2.id)
        assert deps == []

    def test_dependency_returns_model(self, db_path, project_id):
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_feature_dependencies,
        )
        from bob.models import FeatureDependency

        f1 = create_feature(project_id=project_id, name="A")
        f2 = create_feature(project_id=project_id, name="B")
        add_feature_dependency(feature_id=f2.id, depends_on_feature_id=f1.id)

        deps = get_feature_dependencies(f2.id)
        assert all(isinstance(d, FeatureDependency) for d in deps)

    def test_duplicate_dependency_is_idempotent(self, db_path, project_id):
        from bob.db import (
            create_feature,
            add_feature_dependency,
            get_feature_dependencies,
        )

        f1 = create_feature(project_id=project_id, name="A")
        f2 = create_feature(project_id=project_id, name="B")
        add_feature_dependency(feature_id=f2.id, depends_on_feature_id=f1.id)
        add_feature_dependency(feature_id=f2.id, depends_on_feature_id=f1.id)

        deps = get_feature_dependencies(f2.id)
        assert len(deps) == 1


# ============================================================
# Step 7: Foreign key constraints
# ============================================================


class TestForeignKeyConstraints:
    """Verify foreign key constraints work."""

    def test_create_feature_with_invalid_project_id_fails(self, db_path):
        from bob.db import create_feature

        with pytest.raises(Exception):
            create_feature(
                project_id="nonexistent-project",
                name="Orphan Feature",
            )

    def test_create_feature_with_invalid_parent_fails(self, db_path, project_id):
        from bob.db import create_feature

        with pytest.raises(Exception):
            create_feature(
                project_id=project_id,
                name="Bad Parent Feature",
                parent_feature_id="nonexistent-parent",
            )

    def test_add_dependency_with_invalid_feature_fails(self, db_path, project_id):
        from bob.db import create_feature, add_feature_dependency

        feature = create_feature(project_id=project_id, name="Real Feature")
        with pytest.raises(Exception):
            add_feature_dependency(
                feature_id=feature.id,
                depends_on_feature_id="nonexistent-feature",
            )

    def test_add_dependency_with_invalid_dependent_fails(self, db_path, project_id):
        from bob.db import create_feature, add_feature_dependency

        feature = create_feature(project_id=project_id, name="Real Feature")
        with pytest.raises(Exception):
            add_feature_dependency(
                feature_id="nonexistent-feature",
                depends_on_feature_id=feature.id,
            )
