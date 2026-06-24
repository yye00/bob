"""Tests for F027: Task execution attempt tracking and max attempts enforcement."""

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
# Step 1: increment_task_attempts()
# ============================================================


class TestIncrementTaskAttempts:
    """increment_task_attempts() increments the attempts counter for a task."""

    def test_increment_from_zero(self, db_path, project_id, feature_id):
        from bob.db import create_task, increment_task_attempts, get_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Attempt Task",
        )
        assert task.attempts == 0

        result = increment_task_attempts(task.id)
        assert result is not None
        assert result.attempts == 1

    def test_increment_multiple_times(self, db_path, project_id, feature_id):
        from bob.db import create_task, increment_task_attempts, get_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Multi Attempt",
        )

        for i in range(1, 4):
            result = increment_task_attempts(task.id)
            assert result.attempts == i

        fetched = get_task(task.id)
        assert fetched.attempts == 3

    def test_increment_persists_to_database(self, db_path, project_id, feature_id):
        from bob.db import create_task, increment_task_attempts, get_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Persist Attempt",
        )
        increment_task_attempts(task.id)
        increment_task_attempts(task.id)

        fetched = get_task(task.id)
        assert fetched.attempts == 2

    def test_increment_returns_updated_task(self, db_path, project_id, feature_id):
        from bob.db import create_task, increment_task_attempts
        from bob.models import Task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Return Check",
        )
        result = increment_task_attempts(task.id)
        assert isinstance(result, Task)

    def test_increment_nonexistent_task_returns_none(self, db_path):
        from bob.db import increment_task_attempts

        result = increment_task_attempts("nonexistent-id")
        assert result is None

    def test_increment_updates_timestamp(self, db_path, project_id, feature_id):
        import time
        from bob.db import create_task, increment_task_attempts

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="TS Attempt",
        )
        original_updated = task.updated_at
        time.sleep(0.05)
        result = increment_task_attempts(task.id)
        assert result.updated_at >= original_updated


# ============================================================
# Step 2: check_task_attempt_limit()
# ============================================================


class TestCheckTaskAttemptLimit:
    """check_task_attempt_limit() checks if a task has exceeded its max attempts."""

    def test_within_limit_returns_false(self, db_path, project_id, feature_id):
        from bob.db import create_task, check_task_attempt_limit

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Under Limit",
        )
        exceeded = check_task_attempt_limit(task.id)
        assert exceeded is False

    def test_at_limit_returns_true(self, db_path, project_id, feature_id):
        from bob.db import create_task, update_task, check_task_attempt_limit

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="At Limit",
        )
        # max_attempts defaults to 5, set attempts to 5
        update_task(task.id, attempts=5)
        exceeded = check_task_attempt_limit(task.id)
        assert exceeded is True

    def test_over_limit_returns_true(self, db_path, project_id, feature_id):
        from bob.db import create_task, update_task, check_task_attempt_limit

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Over Limit",
        )
        update_task(task.id, attempts=7)
        exceeded = check_task_attempt_limit(task.id)
        assert exceeded is True

    def test_one_below_limit_returns_false(self, db_path, project_id, feature_id):
        from bob.db import create_task, update_task, check_task_attempt_limit

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Just Under",
        )
        update_task(task.id, attempts=4)
        exceeded = check_task_attempt_limit(task.id)
        assert exceeded is False

    def test_custom_max_attempts(self, db_path, project_id, feature_id):
        from bob.db import create_task, update_task, check_task_attempt_limit

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Custom Max",
        )
        update_task(task.id, max_attempts=3, attempts=3)
        exceeded = check_task_attempt_limit(task.id)
        assert exceeded is True

    def test_nonexistent_task_returns_none(self, db_path):
        from bob.db import check_task_attempt_limit

        result = check_task_attempt_limit("nonexistent-id")
        assert result is None


# ============================================================
# Step 3: Execute task 5 times, verify 6th attempt triggers failure
# ============================================================


class TestMaxAttemptsEnforcement:
    """Integration test: 5 attempts OK, 6th exceeds the limit."""

    def test_five_attempts_ok_sixth_exceeds(self, db_path, project_id, feature_id):
        from bob.db import (
            create_task,
            increment_task_attempts,
            check_task_attempt_limit,
        )

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Max Attempts Test",
        )
        assert task.max_attempts == 5

        # Execute 5 times - all within limit
        for i in range(1, 6):
            result = increment_task_attempts(task.id)
            assert result.attempts == i
            if i < 5:
                assert check_task_attempt_limit(task.id) is False

        # After 5 attempts, we've hit the limit
        assert check_task_attempt_limit(task.id) is True

        # 6th attempt increments but limit is still exceeded
        result = increment_task_attempts(task.id)
        assert result.attempts == 6
        assert check_task_attempt_limit(task.id) is True

    def test_custom_limit_enforcement(self, db_path, project_id, feature_id):
        from bob.db import (
            create_task,
            update_task,
            increment_task_attempts,
            check_task_attempt_limit,
        )

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Custom Limit Test",
        )
        update_task(task.id, max_attempts=3)

        # 3 attempts within limit
        for i in range(1, 4):
            increment_task_attempts(task.id)
            if i < 3:
                assert check_task_attempt_limit(task.id) is False

        # At limit
        assert check_task_attempt_limit(task.id) is True


# ============================================================
# Step 4: Verify attempts counter updates correctly
# ============================================================


class TestAttemptsCounterAccuracy:
    """Verify the attempts counter is accurate after various operations."""

    def test_counter_starts_at_zero(self, db_path, project_id, feature_id):
        from bob.db import create_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Zero Start",
        )
        assert task.attempts == 0

    def test_counter_increments_by_one_each_time(self, db_path, project_id, feature_id):
        from bob.db import create_task, increment_task_attempts, get_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Counter Accuracy",
        )

        for expected in range(1, 8):
            increment_task_attempts(task.id)
            fetched = get_task(task.id)
            assert fetched.attempts == expected

    def test_counter_survives_other_updates(self, db_path, project_id, feature_id):
        from bob.db import create_task, increment_task_attempts, update_task, get_task

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="Counter Survives",
        )
        increment_task_attempts(task.id)
        increment_task_attempts(task.id)

        # Update other fields - should not affect attempts
        update_task(task.id, status="executing", description="In progress")

        fetched = get_task(task.id)
        assert fetched.attempts == 2
        assert fetched.status == "executing"
        assert fetched.description == "In progress"

    def test_counter_matches_database(self, db_path, project_id, feature_id):
        import sqlite3
        from bob.db import create_task, increment_task_attempts

        task = create_task(
            feature_id=feature_id,
            project_id=project_id,
            type="implementation",
            title="DB Match",
        )
        for _ in range(4):
            increment_task_attempts(task.id)

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT attempts FROM tasks WHERE id = ?", (task.id,)
            )
            row = cursor.fetchone()
            assert row[0] == 4
        finally:
            conn.close()
