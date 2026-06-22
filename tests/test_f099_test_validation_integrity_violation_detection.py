"""Tests for F099: Test validation integrity violation detection.

End-to-end test that:
1. Creates a validation task with 15 assertions.
2. Records original_assertion_count=15.
3. Modifies the test to have only 8 assertions.
4. Updates current_assertion_count=8.
5. Verifies test_integrity_violations view shows this test.
6. Verifies an alert/warning is generated.
"""

import json
import os

import pytest

from bob3.db import (
    create_feature,
    create_project,
    create_task,
    get_task,
    get_validation_integrity_violations,
    init_database,
    query_execution_logs,
    query_test_integrity_violations_view,
    track_validation_integrity,
    update_task,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    path = tmp_path / "test_f099.db"
    os.environ["BOB3_DATABASE_PATH"] = str(path)
    init_database(db_path=path)
    yield path
    os.environ.pop("BOB3_DATABASE_PATH", None)


@pytest.fixture
def project_id(db_path):
    """Create a project and return its ID."""
    project = create_project(name="integrity-project", workspace_path="/tmp/f099")
    return project.id


@pytest.fixture
def feature_id(project_id):
    """Create a feature and return its ID."""
    feature = create_feature(project_id=project_id, name="integrity-feature")
    return feature.id


@pytest.fixture
def validation_task(feature_id, project_id):
    """Create a validation task."""
    return create_task(
        feature_id=feature_id,
        project_id=project_id,
        type="validation",
        title="Validate data processing pipeline",
    )


class TestValidationIntegrityViolationDetection:
    """End-to-end test for validation integrity violation detection (F099)."""

    def test_step1_create_validation_task_with_15_assertions(self, validation_task, project_id):
        """Step 1: Create validation task with 15 assertions."""
        result = track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )
        assert result is not None
        assert result["original_assertion_count"] == 15
        assert result["current_assertion_count"] == 15
        assert result["violation"] is False

    def test_step2_record_original_assertion_count_15(self, validation_task, project_id):
        """Step 2: Record original_assertion_count=15."""
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )

        task = get_task(validation_task.id)
        assert task.original_assertion_count == 15

    def test_step3_modify_test_to_have_8_assertions(self, validation_task, project_id):
        """Step 3: Modify test to have only 8 assertions."""
        # First set original to 15
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )

        # Then reduce to 8
        result = track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=8,
        )
        assert result["current_assertion_count"] == 8
        assert result["original_assertion_count"] == 15

    def test_step4_update_current_assertion_count_8(self, validation_task, project_id):
        """Step 4: Update current_assertion_count=8."""
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=8,
        )

        task = get_task(validation_task.id)
        assert task.original_assertion_count == 15
        assert task.current_assertion_count == 8

    def test_step5_verify_test_integrity_violations_view_shows_task(
        self, validation_task, project_id, feature_id
    ):
        """Step 5: Verify test_integrity_violations view shows this test."""
        # Set original to 15
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )
        # Reduce to 8
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=8,
        )

        # Check the SQL view
        violations_view = query_test_integrity_violations_view(project_id)
        assert len(violations_view) >= 1
        task_ids = [v["id"] for v in violations_view]
        assert validation_task.id in task_ids

        found = next(v for v in violations_view if v["id"] == validation_task.id)
        assert found["original_assertion_count"] == 15
        assert found["current_assertion_count"] == 8
        assert found["feature_name"] == "integrity-feature"

        # Also check the model-based query
        violations_model = get_validation_integrity_violations(project_id=project_id)
        assert len(violations_model) >= 1
        model_ids = [v.id for v in violations_model]
        assert validation_task.id in model_ids

    def test_step6_verify_alert_or_warning_is_generated(
        self, validation_task, project_id
    ):
        """Step 6: Verify alert or warning is generated."""
        # Set original to 15
        result1 = track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )
        assert result1["violation"] is False

        # Reduce to 8 - should trigger a violation AND a warning
        result2 = track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=8,
        )
        assert result2["violation"] is True

        # Verify a warning was logged
        logs = query_execution_logs(
            project_id=project_id,
            level="warning",
        )
        assert len(logs) >= 1

        # Find the integrity violation warning
        violation_logs = [
            log for log in logs if "integrity" in log.event.lower()
        ]
        assert len(violation_logs) >= 1

        log = violation_logs[0]
        assert log.level == "warning"
        assert validation_task.id in log.details

    def test_full_flow_end_to_end(self, validation_task, project_id, feature_id):
        """Full end-to-end flow: create with 15, reduce to 8, verify violation + alert."""
        # Step 1 & 2: Create with 15 assertions, record original
        result = track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )
        assert result["original_assertion_count"] == 15
        assert result["violation"] is False

        task = get_task(validation_task.id)
        assert task.original_assertion_count == 15
        assert task.current_assertion_count == 15

        # Step 3 & 4: Reduce to 8 assertions
        result = track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=8,
        )
        assert result["original_assertion_count"] == 15
        assert result["current_assertion_count"] == 8
        assert result["violation"] is True

        task = get_task(validation_task.id)
        assert task.original_assertion_count == 15
        assert task.current_assertion_count == 8

        # Step 5: Verify test_integrity_violations view shows the task
        violations_view = query_test_integrity_violations_view(project_id)
        assert len(violations_view) >= 1
        task_ids = [v["id"] for v in violations_view]
        assert validation_task.id in task_ids

        violations_model = get_validation_integrity_violations(project_id=project_id)
        assert len(violations_model) >= 1
        model_ids = [v.id for v in violations_model]
        assert validation_task.id in model_ids

        # Step 6: Verify warning was generated
        logs = query_execution_logs(project_id=project_id, level="warning")
        violation_logs = [
            log for log in logs if "integrity" in log.event.lower()
        ]
        assert len(violation_logs) >= 1
        assert violation_logs[0].level == "warning"

    def test_no_warning_when_no_violation(self, validation_task, project_id):
        """No warning is generated when assertions increase or stay the same."""
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=20,
        )

        logs = query_execution_logs(project_id=project_id, level="warning")
        violation_logs = [
            log for log in logs if "integrity" in log.event.lower()
        ]
        assert len(violation_logs) == 0

    def test_violation_not_in_view_when_no_decrease(self, validation_task, project_id):
        """Task does not appear in violations view when assertions stay the same."""
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )
        track_validation_integrity(
            task_id=validation_task.id,
            assertion_count=15,
        )

        violations_view = query_test_integrity_violations_view(project_id)
        task_ids = [v["id"] for v in violations_view]
        assert validation_task.id not in task_ids
