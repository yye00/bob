"""Tests for F013: Database CRUD operations for tasks table."""

import json
import pathlib
import sqlite3
import time
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


@pytest.fixture()
def feature_id(db_path, project_id):
    """Create a feature and return its ID for use as a foreign key."""
    from bob.db import create_feature

    feature = create_feature(
        project_id=project_id,
        name="Test Feature",
    )
    return feature.id


# ============================================================
# Step 1: create_task()
# ============================================================


class TestCreateTask:
    """create_task() inserts a new task and returns it."""

    def test_create_task_returns_task_model(self, db_path, project_id, feature_id):
        from bob.db import create_task
        from bob.models import Task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Implement module",
        )
        assert isinstance(task, Task)

    def test_create_task_sets_id(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="ID task",
        )
        assert task.id is not None
        assert len(task.id) > 0

    def test_create_task_persists_to_database(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Persisted Task",
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT title, feature_id, project_id, type FROM tasks WHERE id = ?",
                (task.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "Persisted Task"
            assert row[1] == feature_id
            assert row[2] == project_id
            assert row[3] == "implementation"
        finally:
            conn.close()

    def test_create_task_with_optional_fields(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="validation",
            title="Full Task",
            subtype="numerical",
            task_class="test_writing",
            description="A detailed task",
            acceptance_criteria=json.dumps(["check output", "verify format"]),
            expected_outputs=json.dumps(["output.txt"]),
            verify_script="pytest tests/",
        )
        assert task.subtype == "numerical"
        assert task.task_class == "test_writing"
        assert task.description == "A detailed task"
        assert task.acceptance_criteria == json.dumps(["check output", "verify format"])
        assert task.expected_outputs == json.dumps(["output.txt"])
        assert task.verify_script == "pytest tests/"

    def test_create_task_default_status_is_pending(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Default Status",
        )
        assert task.status == "pending"

    def test_create_task_default_confidences(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Confidence Task",
        )
        assert task.conf_spec_understanding == 0.0
        assert task.conf_impl_correctness == 0.0
        assert task.conf_test_adequacy == 0.0
        assert task.readiness_score == 0.0

    def test_create_task_default_attempts(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Attempts Task",
        )
        assert task.attempts == 0
        assert task.max_attempts == 5

    def test_create_task_sets_timestamps(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Timestamp Task",
        )
        assert task.created_at is not None
        assert task.updated_at is not None

    def test_create_task_with_explicit_id(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Explicit ID",
            task_id="T001",
        )
        assert task.id == "T001"

    def test_create_task_default_flaky_fields(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="validation",
            title="Flaky Test",
        )
        assert task.is_flaky is False
        assert task.flaky_pass_rate is None

    def test_create_task_default_human_authored(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="validation",
            title="Human Authored",
        )
        assert task.is_human_authored is False


# ============================================================
# Step 2: get_task()
# ============================================================


class TestGetTask:
    """get_task() retrieves a task by ID."""

    def test_get_task_returns_task(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task
        from bob.models import Task

        created = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Get Me",
        )
        fetched = get_task(created.id)
        assert isinstance(fetched, Task)

    def test_get_task_has_correct_fields(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task

        created = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="validation",
            title="Detail Task",
            subtype="algorithmic",
            description="Some desc",
        )
        fetched = get_task(created.id)
        assert fetched.title == "Detail Task"
        assert fetched.feature_id == feature_id
        assert fetched.project_id == project_id
        assert fetched.type == "validation"
        assert fetched.subtype == "algorithmic"
        assert fetched.description == "Some desc"

    def test_get_task_not_found_returns_none(self, db_path):
        from bob.db import get_task

        result = get_task("nonexistent-id")
        assert result is None

    def test_get_task_preserves_id(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task

        created = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="ID Test",
        )
        fetched = get_task(created.id)
        assert fetched.id == created.id


# ============================================================
# Step 3: update_task()
# ============================================================


class TestUpdateTask:
    """update_task() modifies existing task fields."""

    def test_update_task_changes_title(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Old Title",
        )
        update_task(task.id, title="New Title")
        fetched = get_task(task.id)
        assert fetched.title == "New Title"

    def test_update_task_changes_status(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Status Test",
        )
        update_task(task.id, status="completed")
        fetched = get_task(task.id)
        assert fetched.status == "completed"

    def test_update_task_changes_description(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Desc Test",
        )
        update_task(task.id, description="Updated desc")
        fetched = get_task(task.id)
        assert fetched.description == "Updated desc"

    def test_update_task_changes_confidence(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Conf Test",
        )
        update_task(
            task.id,
            conf_spec_understanding=0.8,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.9,
        )
        fetched = get_task(task.id)
        assert fetched.conf_spec_understanding == 0.8
        assert fetched.conf_impl_correctness == 0.7
        assert fetched.conf_test_adequacy == 0.9

    def test_update_task_changes_readiness(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Readiness Test",
        )
        update_task(task.id, readiness_score=0.85)
        fetched = get_task(task.id)
        assert fetched.readiness_score == 0.85

    def test_update_task_changes_attempts(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Attempts Test",
        )
        update_task(task.id, attempts=3)
        fetched = get_task(task.id)
        assert fetched.attempts == 3

    def test_update_task_changes_flaky_status(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="validation",
            title="Flaky Test",
        )
        update_task(task.id, is_flaky=True, flaky_pass_rate=0.6)
        fetched = get_task(task.id)
        assert fetched.is_flaky is True
        assert fetched.flaky_pass_rate == 0.6

    def test_update_task_changes_validation_integrity(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="validation",
            title="Integrity Test",
        )
        update_task(
            task.id,
            is_human_authored=True,
            original_assertion_count=10,
            current_assertion_count=8,
            original_coverage_percent=95.0,
            current_coverage_percent=90.0,
        )
        fetched = get_task(task.id)
        assert fetched.is_human_authored is True
        assert fetched.original_assertion_count == 10
        assert fetched.current_assertion_count == 8
        assert fetched.original_coverage_percent == 95.0
        assert fetched.current_coverage_percent == 90.0

    def test_update_task_returns_updated_task(self, db_path, project_id, feature_id):
        from bob.db import create_task, update_task
        from bob.models import Task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Return Test",
        )
        updated = update_task(task.id, title="Updated")
        assert isinstance(updated, Task)
        assert updated.title == "Updated"

    def test_update_task_not_found_returns_none(self, db_path):
        from bob.db import update_task

        result = update_task("nonexistent-id", title="Ghost")
        assert result is None

    def test_update_task_updates_timestamp(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="TS Test",
        )
        original_updated = task.updated_at
        time.sleep(0.05)
        update_task(task.id, title="TS Updated")
        fetched = get_task(task.id)
        assert fetched.updated_at >= original_updated

    def test_update_task_multiple_fields(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Multi Test",
        )
        update_task(
            task.id,
            title="Multi Updated",
            status="completed",
            description="Done",
            attempts=2,
        )
        fetched = get_task(task.id)
        assert fetched.title == "Multi Updated"
        assert fetched.status == "completed"
        assert fetched.description == "Done"
        assert fetched.attempts == 2


# ============================================================
# Step 4: list_tasks() with filtering by feature/status
# ============================================================


class TestListTasks:
    """list_tasks() returns tasks with optional filtering."""

    def test_list_tasks_empty(self, db_path, project_id, feature_id):
        from bob.db import list_tasks

        tasks = list_tasks(feature_id=feature_id)
        assert tasks == []

    def test_list_tasks_returns_all_for_feature(self, db_path, project_id, feature_id):
        from bob.db import create_task, list_tasks

        create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Task A",
        )
        create_task(
            feature_id=feature_id, project_id=project_id,
            type="validation", title="Task B",
        )
        create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Task C",
        )

        tasks = list_tasks(feature_id=feature_id)
        assert len(tasks) == 3
        titles = {t.title for t in tasks}
        assert titles == {"Task A", "Task B", "Task C"}

    def test_list_tasks_returns_task_models(self, db_path, project_id, feature_id):
        from bob.db import create_task, list_tasks
        from bob.models import Task

        create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Model Test",
        )
        tasks = list_tasks(feature_id=feature_id)
        assert all(isinstance(t, Task) for t in tasks)

    def test_list_tasks_filter_by_status(self, db_path, project_id, feature_id):
        from bob.db import create_task, update_task, list_tasks

        t1 = create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Pending Task",
        )
        t2 = create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Completed Task",
        )
        update_task(t2.id, status="completed")

        pending = list_tasks(feature_id=feature_id, status="pending")
        assert len(pending) == 1
        assert pending[0].title == "Pending Task"

        completed = list_tasks(feature_id=feature_id, status="completed")
        assert len(completed) == 1
        assert completed[0].title == "Completed Task"

    def test_list_tasks_filter_by_feature_only(self, db_path, project_id):
        from bob.db import create_feature, create_task, list_tasks

        f1 = create_feature(project_id=project_id, name="Feature 1")
        f2 = create_feature(project_id=project_id, name="Feature 2")

        create_task(
            feature_id=f1.id, project_id=project_id,
            type="implementation", title="Task F1",
        )
        create_task(
            feature_id=f2.id, project_id=project_id,
            type="implementation", title="Task F2",
        )

        tasks_f1 = list_tasks(feature_id=f1.id)
        assert len(tasks_f1) == 1
        assert tasks_f1[0].title == "Task F1"

        tasks_f2 = list_tasks(feature_id=f2.id)
        assert len(tasks_f2) == 1
        assert tasks_f2[0].title == "Task F2"

    def test_list_tasks_by_project(self, db_path, project_id, feature_id):
        from bob.db import create_task, list_tasks

        create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Task A",
        )
        create_task(
            feature_id=feature_id, project_id=project_id,
            type="validation", title="Task B",
        )

        tasks = list_tasks(project_id=project_id)
        assert len(tasks) == 2

    def test_list_tasks_by_project_and_status(self, db_path, project_id, feature_id):
        from bob.db import create_task, update_task, list_tasks

        t1 = create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Pending",
        )
        t2 = create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Done",
        )
        update_task(t2.id, status="completed")

        tasks = list_tasks(project_id=project_id, status="pending")
        assert len(tasks) == 1
        assert tasks[0].title == "Pending"

    def test_list_tasks_ordered_by_creation_time(self, db_path, project_id, feature_id):
        from bob.db import create_task, list_tasks

        create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="First",
        )
        time.sleep(0.01)
        create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Second",
        )
        time.sleep(0.01)
        create_task(
            feature_id=feature_id, project_id=project_id,
            type="implementation", title="Third",
        )

        tasks = list_tasks(feature_id=feature_id)
        assert tasks[0].title == "First"
        assert tasks[1].title == "Second"
        assert tasks[2].title == "Third"

    def test_list_tasks_requires_feature_or_project(self, db_path):
        from bob.db import list_tasks

        with pytest.raises(ValueError):
            list_tasks()


# ============================================================
# Step 5: Task CRUD integration
# ============================================================


class TestTaskCrudIntegration:
    """Integration tests for full task CRUD lifecycle."""

    def test_create_read_update_delete_lifecycle(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task, update_task, list_tasks

        # Create
        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Lifecycle Task",
            description="Initial description",
        )
        assert task.status == "pending"

        # Read
        fetched = get_task(task.id)
        assert fetched.title == "Lifecycle Task"

        # Update
        updated = update_task(task.id, status="completed", description="Final")
        assert updated.status == "completed"
        assert updated.description == "Final"

        # List
        tasks = list_tasks(feature_id=feature_id, status="completed")
        assert len(tasks) == 1
        assert tasks[0].id == task.id

    def test_multiple_tasks_per_feature(self, db_path, project_id, feature_id):
        from bob.db import create_task, list_tasks

        for i in range(5):
            create_task(
                feature_id=feature_id,
                project_id=project_id,
                type="implementation" if i % 2 == 0 else "validation",
                title=f"Task {i}",
            )

        tasks = list_tasks(feature_id=feature_id)
        assert len(tasks) == 5


# ============================================================
# Step 6: Verify task-feature relationships (foreign keys)
# ============================================================


class TestTaskFeatureRelationships:
    """Verify foreign key constraints between tasks and features/projects."""

    def test_create_task_with_invalid_feature_id_fails(self, db_path, project_id):
        from bob.db import create_task

        with pytest.raises(Exception):
            create_task(
                feature_id="nonexistent-feature",
                project_id=project_id,
                type="implementation",
                title="Orphan Task",
            )

    def test_create_task_with_invalid_project_id_fails(self, db_path, feature_id):
        from bob.db import create_task

        with pytest.raises(Exception):
            create_task(
                feature_id=feature_id,
                project_id="nonexistent-project",
                type="implementation",
                title="Bad Project Task",
            )

    def test_tasks_belong_to_correct_feature(self, db_path, project_id):
        from bob.db import create_feature, create_task, list_tasks

        f1 = create_feature(project_id=project_id, name="Feature 1")
        f2 = create_feature(project_id=project_id, name="Feature 2")

        create_task(
            feature_id=f1.id, project_id=project_id,
            type="implementation", title="F1 Task",
        )
        create_task(
            feature_id=f2.id, project_id=project_id,
            type="implementation", title="F2 Task",
        )

        f1_tasks = list_tasks(feature_id=f1.id)
        f2_tasks = list_tasks(feature_id=f2.id)

        assert len(f1_tasks) == 1
        assert f1_tasks[0].title == "F1 Task"
        assert len(f2_tasks) == 1
        assert f2_tasks[0].title == "F2 Task"

    def test_task_references_correct_project(self, db_path, project_id, feature_id):
        from bob.db import create_task, get_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Project Ref Task",
        )
        fetched = get_task(task.id)
        assert fetched.project_id == project_id
        assert fetched.feature_id == feature_id
