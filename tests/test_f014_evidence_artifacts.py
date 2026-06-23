"""Tests for F014: Database CRUD operations for evidence_artifacts table."""

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
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database

    init_database()
    return p


@pytest.fixture()
def project(db_path):
    """Create a test project for foreign key references."""
    from bob3.db import create_project

    return create_project(
        name="Evidence Test Project",
        workspace_path="/tmp/evidence-test",
    )


@pytest.fixture()
def feature(db_path, project):
    """Create a test feature for foreign key references."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Evidence Test Feature",
    )


@pytest.fixture()
def task(db_path, project, feature):
    """Create a test task for foreign key references."""
    from bob3.db import create_task

    return create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="implementation",
        title="Evidence Test Task",
    )


# ============================================================
# Step 1: create_evidence()
# ============================================================


class TestCreateEvidence:
    """Step 1: create_evidence() inserts a new evidence artifact and returns it."""

    def test_create_evidence_returns_evidence_model(self, project, feature, task):
        from bob3.db import create_evidence
        from bob3.models import EvidenceArtifact

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"stdout": "All tests passed"}),
        )
        assert isinstance(evidence, EvidenceArtifact)

    def test_create_evidence_sets_id(self, project, feature, task):
        from bob3.db import create_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"result": "ok"}),
        )
        assert evidence.id is not None
        assert len(evidence.id) > 0

    def test_create_evidence_persists_to_database(self, db_path, project, feature, task):
        from bob3.db import create_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"persisted": True}),
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT type, content FROM evidence_artifacts WHERE id = ?",
                (evidence.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "test_output"
            assert json.loads(row[1]) == {"persisted": True}
        finally:
            conn.close()

    def test_create_evidence_with_all_optional_fields(self, project, feature, task):
        from bob3.db import create_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="build_output",
            content=json.dumps({"log": "build succeeded"}),
            attempt_number=2,
            output_hash="abc123",
            reproducible=True,
            is_current=True,
            iteration_created=3,
            environment_fingerprint=json.dumps({"python": "3.13"}),
            environment_matches_current=True,
        )
        assert evidence.attempt_number == 2
        assert evidence.output_hash == "abc123"
        assert evidence.reproducible is True
        assert evidence.is_current is True
        assert evidence.iteration_created == 3
        assert evidence.environment_fingerprint == json.dumps({"python": "3.13"})
        assert evidence.environment_matches_current is True

    def test_create_evidence_without_feature_or_task(self, project):
        from bob3.db import create_evidence

        evidence = create_evidence(
            project_id=project.id,
            type="project_level",
            content=json.dumps({"info": "project-level evidence"}),
        )
        assert evidence.feature_id is None
        assert evidence.task_id is None

    def test_create_evidence_default_is_current_true(self, project, feature):
        from bob3.db import create_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"status": "pass"}),
        )
        assert evidence.is_current is True

    def test_create_evidence_sets_timestamp(self, project, feature):
        from bob3.db import create_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"ts": "test"}),
        )
        assert evidence.created_at is not None

    def test_create_evidence_with_custom_id(self, project, feature):
        from bob3.db import create_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"custom": True}),
            evidence_id="custom-evidence-id-123",
        )
        assert evidence.id == "custom-evidence-id-123"


# ============================================================
# Step 2: get_evidence()
# ============================================================


class TestGetEvidence:
    """Step 2: get_evidence() retrieves an evidence artifact by ID."""

    def test_get_evidence_returns_evidence(self, project, feature, task):
        from bob3.db import create_evidence, get_evidence
        from bob3.models import EvidenceArtifact

        created = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"data": "get test"}),
        )
        fetched = get_evidence(created.id)
        assert isinstance(fetched, EvidenceArtifact)

    def test_get_evidence_has_correct_fields(self, project, feature, task):
        from bob3.db import create_evidence, get_evidence

        created = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="build_log",
            content=json.dumps({"log": "success"}),
            attempt_number=1,
            output_hash="hash123",
        )
        fetched = get_evidence(created.id)
        assert fetched.project_id == project.id
        assert fetched.feature_id == feature.id
        assert fetched.task_id == task.id
        assert fetched.type == "build_log"
        assert json.loads(fetched.content) == {"log": "success"}
        assert fetched.attempt_number == 1
        assert fetched.output_hash == "hash123"

    def test_get_evidence_not_found_returns_none(self, db_path):
        from bob3.db import get_evidence

        result = get_evidence("nonexistent-evidence-id")
        assert result is None

    def test_get_evidence_preserves_id(self, project, feature):
        from bob3.db import create_evidence, get_evidence

        created = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"id_test": True}),
        )
        fetched = get_evidence(created.id)
        assert fetched.id == created.id

    def test_get_evidence_boolean_fields(self, project, feature):
        from bob3.db import create_evidence, get_evidence

        created = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({}),
            is_current=False,
            reproducible=True,
            environment_matches_current=False,
        )
        fetched = get_evidence(created.id)
        assert fetched.is_current is False
        assert fetched.reproducible is True
        assert fetched.environment_matches_current is False


# ============================================================
# Step 3: update_evidence()
# ============================================================


class TestUpdateEvidence:
    """Step 3: update_evidence() modifies existing evidence fields."""

    def test_update_evidence_changes_is_current(self, project, feature):
        from bob3.db import create_evidence, get_evidence, update_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"data": "original"}),
            is_current=True,
        )
        update_evidence(evidence.id, is_current=False)
        fetched = get_evidence(evidence.id)
        assert fetched.is_current is False

    def test_update_evidence_changes_verification_fields(self, project, feature):
        from bob3.db import create_evidence, get_evidence, update_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"data": "verify"}),
        )
        now = datetime.now().isoformat()
        update_evidence(
            evidence.id,
            verification_passed=True,
            verification_run_at=now,
            output_hash="verified-hash",
        )
        fetched = get_evidence(evidence.id)
        assert fetched.verification_passed is True
        assert fetched.output_hash == "verified-hash"

    def test_update_evidence_changes_environment_match(self, project, feature):
        from bob3.db import create_evidence, get_evidence, update_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({}),
            environment_matches_current=True,
        )
        update_evidence(evidence.id, environment_matches_current=False)
        fetched = get_evidence(evidence.id)
        assert fetched.environment_matches_current is False

    def test_update_evidence_returns_updated_model(self, project, feature):
        from bob3.db import create_evidence, update_evidence
        from bob3.models import EvidenceArtifact

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({}),
        )
        updated = update_evidence(evidence.id, is_current=False)
        assert isinstance(updated, EvidenceArtifact)
        assert updated.is_current is False

    def test_update_evidence_not_found_returns_none(self, db_path):
        from bob3.db import update_evidence

        result = update_evidence("nonexistent-id", is_current=False)
        assert result is None

    def test_update_evidence_multiple_fields(self, project, feature):
        from bob3.db import create_evidence, get_evidence, update_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({}),
        )
        update_evidence(
            evidence.id,
            is_current=False,
            reproducible=True,
            output_hash="multi-update-hash",
        )
        fetched = get_evidence(evidence.id)
        assert fetched.is_current is False
        assert fetched.reproducible is True
        assert fetched.output_hash == "multi-update-hash"


# ============================================================
# Step 4: query_evidence() with filtering
# ============================================================


class TestQueryEvidence:
    """Step 4: query_evidence() supports filtering by feature, task, and is_current."""

    def test_query_evidence_by_feature_id(self, project, feature, task):
        from bob3.db import create_evidence, query_evidence

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"f": 1}),
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="build_log",
            content=json.dumps({"f": 2}),
        )

        results = query_evidence(feature_id=feature.id)
        assert len(results) == 2

    def test_query_evidence_by_task_id(self, project, feature, task):
        from bob3.db import create_evidence, query_evidence

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"t": 1}),
        )
        # Evidence without task_id should not appear
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="build_log",
            content=json.dumps({"t": 2}),
        )

        results = query_evidence(task_id=task.id)
        assert len(results) == 1
        assert json.loads(results[0].content) == {"t": 1}

    def test_query_evidence_by_is_current(self, project, feature):
        from bob3.db import create_evidence, update_evidence, query_evidence

        e1 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"current": True}),
            is_current=True,
        )
        e2 = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"current": False}),
            is_current=False,
        )

        current = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current) == 1
        assert current[0].id == e1.id

        not_current = query_evidence(feature_id=feature.id, is_current=False)
        assert len(not_current) == 1
        assert not_current[0].id == e2.id

    def test_query_evidence_by_project_id(self, project, feature):
        from bob3.db import create_evidence, query_evidence

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"p": 1}),
        )

        results = query_evidence(project_id=project.id)
        assert len(results) == 1

    def test_query_evidence_combined_filters(self, project, feature, task):
        from bob3.db import create_evidence, query_evidence

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"combo": 1}),
            is_current=True,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            task_id=task.id,
            type="test_output",
            content=json.dumps({"combo": 2}),
            is_current=False,
        )

        results = query_evidence(
            feature_id=feature.id,
            task_id=task.id,
            is_current=True,
        )
        assert len(results) == 1
        assert json.loads(results[0].content) == {"combo": 1}

    def test_query_evidence_empty_result(self, project):
        from bob3.db import query_evidence

        results = query_evidence(project_id=project.id)
        assert results == []

    def test_query_evidence_requires_at_least_one_filter(self, db_path):
        from bob3.db import query_evidence

        with pytest.raises(ValueError):
            query_evidence()

    def test_query_evidence_returns_evidence_models(self, project, feature):
        from bob3.db import create_evidence, query_evidence
        from bob3.models import EvidenceArtifact

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"model": True}),
        )
        results = query_evidence(feature_id=feature.id)
        assert all(isinstance(e, EvidenceArtifact) for e in results)


# ============================================================
# Step 5-6: Evidence creation/retrieval and is_current flag handling
# ============================================================


class TestEvidenceIsCurrentHandling:
    """Steps 5-6: Verify evidence creation, retrieval, and is_current flag behavior."""

    def test_is_current_default_is_true(self, project, feature):
        from bob3.db import create_evidence, get_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"default": True}),
        )
        fetched = get_evidence(evidence.id)
        assert fetched.is_current is True

    def test_mark_evidence_not_current(self, project, feature):
        from bob3.db import create_evidence, get_evidence, update_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"stale": True}),
            is_current=True,
        )
        update_evidence(evidence.id, is_current=False)
        fetched = get_evidence(evidence.id)
        assert fetched.is_current is False

    def test_create_evidence_as_not_current(self, project, feature):
        from bob3.db import create_evidence, get_evidence

        evidence = create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"not_current": True}),
            is_current=False,
        )
        fetched = get_evidence(evidence.id)
        assert fetched.is_current is False

    def test_filter_current_evidence_for_feature(self, project, feature):
        from bob3.db import create_evidence, query_evidence

        # Create multiple evidence, some current, some not
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"version": 1}),
            is_current=False,
            iteration_created=1,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"version": 2}),
            is_current=False,
            iteration_created=2,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"version": 3}),
            is_current=True,
            iteration_created=3,
        )

        current = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current) == 1
        assert json.loads(current[0].content) == {"version": 3}

        all_evidence = query_evidence(feature_id=feature.id)
        assert len(all_evidence) == 3

    def test_multiple_current_evidence_allowed(self, project, feature):
        from bob3.db import create_evidence, query_evidence

        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="test_output",
            content=json.dumps({"type": "test"}),
            is_current=True,
        )
        create_evidence(
            project_id=project.id,
            feature_id=feature.id,
            type="build_log",
            content=json.dumps({"type": "build"}),
            is_current=True,
        )

        current = query_evidence(feature_id=feature.id, is_current=True)
        assert len(current) == 2
