"""Tests for F029: Validation integrity tracking (assertion count, coverage).

Tests track_validation_integrity() function that monitors assertion counts and
coverage percentages to detect when tests are weakened (validation gaming).
"""

import os
import pytest

from bob3.db import (
    create_feature,
    create_project,
    create_task,
    get_task,
    init_database,
    track_validation_integrity,
    get_validation_integrity_violations,
    update_task,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    path = tmp_path / "test_f029.db"
    os.environ["BOB3_DATABASE_PATH"] = str(path)
    init_database(db_path=path)
    yield path
    os.environ.pop("BOB3_DATABASE_PATH", None)


@pytest.fixture
def project_and_task(db_path):
    """Create a project, feature, and validation task for testing."""
    project = create_project(name="test-project", workspace_path="/tmp/test")
    feature = create_feature(project_id=project.id, name="test-feature")
    task = create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="validation",
        title="test-validation-task",
    )
    return project, feature, task


class TestTrackValidationIntegrity:
    """Tests for the track_validation_integrity() function."""

    def test_step1_function_exists(self, project_and_task):
        """Step 1: track_validation_integrity() function exists and is callable."""
        _, _, task = project_and_task
        result = track_validation_integrity(
            task_id=task.id,
            assertion_count=10,
        )
        assert result is not None

    def test_step2_stores_original_assertion_count(self, project_and_task):
        """Step 2: Stores original_assertion_count when first called."""
        _, _, task = project_and_task

        result = track_validation_integrity(
            task_id=task.id,
            assertion_count=10,
        )

        assert result["original_assertion_count"] == 10
        assert result["current_assertion_count"] == 10

        # Verify persisted to database
        updated = get_task(task.id)
        assert updated.original_assertion_count == 10
        assert updated.current_assertion_count == 10

    def test_step3_updates_current_assertion_count(self, project_and_task):
        """Step 3: Updates current_assertion_count on each modification."""
        _, _, task = project_and_task

        # First call sets original
        track_validation_integrity(task_id=task.id, assertion_count=10)

        # Second call updates current but keeps original
        result = track_validation_integrity(task_id=task.id, assertion_count=12)

        assert result["original_assertion_count"] == 10
        assert result["current_assertion_count"] == 12

        updated = get_task(task.id)
        assert updated.original_assertion_count == 10
        assert updated.current_assertion_count == 12

    def test_step4_detect_violation_current_less_than_original(self, project_and_task):
        """Step 4: Detect violations when current < original."""
        _, _, task = project_and_task

        track_validation_integrity(task_id=task.id, assertion_count=10)
        result = track_validation_integrity(task_id=task.id, assertion_count=5)

        assert result["violation"] is True
        assert result["original_assertion_count"] == 10
        assert result["current_assertion_count"] == 5

    def test_step5_create_test_with_10_reduce_to_5(self, project_and_task):
        """Step 5: Create test with 10 assertions, reduce to 5, verify violation."""
        _, _, task = project_and_task

        # Create with 10 assertions
        result1 = track_validation_integrity(task_id=task.id, assertion_count=10)
        assert result1["violation"] is False
        assert result1["original_assertion_count"] == 10

        # Reduce to 5 assertions
        result2 = track_validation_integrity(task_id=task.id, assertion_count=5)
        assert result2["violation"] is True
        assert result2["current_assertion_count"] == 5
        assert result2["original_assertion_count"] == 10

    def test_no_violation_when_count_increases(self, project_and_task):
        """No violation when assertion count increases."""
        _, _, task = project_and_task

        track_validation_integrity(task_id=task.id, assertion_count=10)
        result = track_validation_integrity(task_id=task.id, assertion_count=15)

        assert result["violation"] is False
        assert result["current_assertion_count"] == 15

    def test_no_violation_when_count_stays_same(self, project_and_task):
        """No violation when assertion count stays the same."""
        _, _, task = project_and_task

        track_validation_integrity(task_id=task.id, assertion_count=10)
        result = track_validation_integrity(task_id=task.id, assertion_count=10)

        assert result["violation"] is False

    def test_coverage_percent_tracking(self, project_and_task):
        """track_validation_integrity() tracks coverage percentages."""
        _, _, task = project_and_task

        result = track_validation_integrity(
            task_id=task.id,
            assertion_count=10,
            coverage_percent=95.0,
        )

        assert result["original_coverage_percent"] == 95.0
        assert result["current_coverage_percent"] == 95.0

        updated = get_task(task.id)
        assert updated.original_coverage_percent == 95.0
        assert updated.current_coverage_percent == 95.0

    def test_coverage_violation_when_drops_more_than_5(self, project_and_task):
        """Violation when coverage drops by more than 5 percentage points."""
        _, _, task = project_and_task

        track_validation_integrity(
            task_id=task.id, assertion_count=10, coverage_percent=95.0
        )
        result = track_validation_integrity(
            task_id=task.id, assertion_count=10, coverage_percent=85.0
        )

        assert result["violation"] is True
        assert result["original_coverage_percent"] == 95.0
        assert result["current_coverage_percent"] == 85.0

    def test_no_coverage_violation_within_tolerance(self, project_and_task):
        """No violation when coverage drops by 5 or less."""
        _, _, task = project_and_task

        track_validation_integrity(
            task_id=task.id, assertion_count=10, coverage_percent=95.0
        )
        result = track_validation_integrity(
            task_id=task.id, assertion_count=10, coverage_percent=90.0
        )

        assert result["violation"] is False

    def test_nonexistent_task_returns_none(self, db_path):
        """Returns None for non-existent task."""
        result = track_validation_integrity(
            task_id="nonexistent", assertion_count=10
        )
        assert result is None

    def test_assertion_only_no_coverage(self, project_and_task):
        """Works when only assertion_count is provided (no coverage)."""
        _, _, task = project_and_task

        result = track_validation_integrity(task_id=task.id, assertion_count=10)

        assert result["original_assertion_count"] == 10
        assert result["current_assertion_count"] == 10
        assert result["original_coverage_percent"] is None
        assert result["current_coverage_percent"] is None

    def test_multiple_updates_tracks_correctly(self, project_and_task):
        """Multiple updates track original correctly through changes."""
        _, _, task = project_and_task

        track_validation_integrity(task_id=task.id, assertion_count=10)
        track_validation_integrity(task_id=task.id, assertion_count=15)
        track_validation_integrity(task_id=task.id, assertion_count=12)
        result = track_validation_integrity(task_id=task.id, assertion_count=8)

        # Original should still be 10 (from the first call)
        assert result["original_assertion_count"] == 10
        assert result["current_assertion_count"] == 8
        assert result["violation"] is True


class TestGetValidationIntegrityViolations:
    """Tests for get_validation_integrity_violations()."""

    def test_returns_empty_list_no_violations(self, project_and_task):
        """Returns empty list when no violations exist."""
        project, _, task = project_and_task

        track_validation_integrity(task_id=task.id, assertion_count=10)

        violations = get_validation_integrity_violations(project_id=project.id)
        assert violations == []

    def test_returns_tasks_with_assertion_violations(self, project_and_task):
        """Returns tasks where current_assertion_count < original."""
        project, feature, task = project_and_task

        track_validation_integrity(task_id=task.id, assertion_count=10)
        track_validation_integrity(task_id=task.id, assertion_count=5)

        violations = get_validation_integrity_violations(project_id=project.id)
        assert len(violations) == 1
        assert violations[0].id == task.id
        assert violations[0].original_assertion_count == 10
        assert violations[0].current_assertion_count == 5

    def test_returns_tasks_with_coverage_violations(self, project_and_task):
        """Returns tasks where coverage dropped more than 5 points."""
        project, _, task = project_and_task

        track_validation_integrity(
            task_id=task.id, assertion_count=10, coverage_percent=95.0
        )
        track_validation_integrity(
            task_id=task.id, assertion_count=10, coverage_percent=85.0
        )

        violations = get_validation_integrity_violations(project_id=project.id)
        assert len(violations) == 1

    def test_excludes_non_violation_tasks(self, project_and_task):
        """Does not include tasks that are within bounds."""
        project, feature, _ = project_and_task

        task1 = create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="task-ok",
        )
        task2 = create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="validation",
            title="task-violated",
        )

        # task1: no violation (assertions increased)
        track_validation_integrity(task_id=task1.id, assertion_count=10)
        track_validation_integrity(task_id=task1.id, assertion_count=15)

        # task2: violation (assertions decreased)
        track_validation_integrity(task_id=task2.id, assertion_count=10)
        track_validation_integrity(task_id=task2.id, assertion_count=3)

        violations = get_validation_integrity_violations(project_id=project.id)
        assert len(violations) == 1
        assert violations[0].id == task2.id
