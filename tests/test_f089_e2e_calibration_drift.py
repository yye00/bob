"""Tests for F089: End-to-end test - Calibration drift detection.

End-to-end integration test that exercises the full calibration drift
detection workflow:

Step 1: Execute 20 tasks with confidence 0.8-0.9
Step 2: Simulate only 10 passing (50% pass rate, expected 85%)
Step 3: Verify calibration drift calculated as -0.35
Step 4: Verify calibration alert created with direction=overconfident
Step 5: Verify alert is visible in status command
"""

import json
import uuid
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from bob3.db import (
    calculate_calibration_drift,
    check_and_create_calibration_alert,
    connect,
    create_calibration_alert,
    create_feature,
    create_or_update_calibration,
    create_project,
    create_task,
    get_calibration,
    init_database,
    list_calibration_alerts,
    record_calibration_result,
    update_task,
)
from bob3.models import CalibrationAlert, CalibrationData


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    db_path = tmp_path / "bob3.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    init_database()
    return db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    return create_project(
        name="Calibration Drift E2E",
        workspace_path="/tmp/calibration-drift-e2e",
    )


@pytest.fixture
def feature(project):
    """Create a test feature."""
    return create_feature(
        project_id=project.id,
        name="Test Feature for Calibration",
        description="Feature used to test calibration drift detection",
        acceptance_criteria=json.dumps(["All calibration tests pass"]),
        status="executing",
    )


@pytest.fixture
def tasks_20(project, feature):
    """Create 20 tasks with confidence 0.8-0.9 and task_class set."""
    tasks = []
    for i in range(20):
        task = create_task(
            project_id=project.id,
            feature_id=feature.id,
            type="implementation",
            title=f"Task {i + 1} - calibration test",
            task_class="greenfield_impl",
            status="pending",
        )
        # Set confidence to 0.85 (within 0.8-0.9 bucket)
        update_task(task.id, conf_impl_correctness=0.85)
        tasks.append(task)
    return tasks


# ============================================================
# Step 1: Execute 20 tasks with confidence 0.8-0.9
# ============================================================


class TestStep1Execute20Tasks:
    """Step 1: Create and execute 20 tasks with confidence in 0.8-0.9 bucket."""

    def test_20_tasks_created(self, tasks_20):
        """Verify 20 tasks exist."""
        assert len(tasks_20) == 20

    def test_tasks_have_correct_task_class(self, tasks_20):
        """All tasks have task_class='greenfield_impl'."""
        for task in tasks_20:
            assert task.task_class == "greenfield_impl"

    def test_tasks_in_correct_confidence_bucket(self, tasks_20):
        """All tasks should map to the 0.8-0.9 confidence bucket."""
        from bob3.db import _confidence_to_bucket, get_task

        for task in tasks_20:
            updated = get_task(task.id)
            bucket = _confidence_to_bucket(updated.conf_impl_correctness)
            assert bucket == "0.8-0.9", (
                f"Task {task.id} confidence {updated.conf_impl_correctness} "
                f"mapped to bucket {bucket}, expected 0.8-0.9"
            )

    def test_record_20_calibration_results(self, project, tasks_20):
        """Record calibration results for all 20 tasks: first 10 pass, last 10 fail."""
        from bob3.db import get_task

        for i, task in enumerate(tasks_20):
            passed = i < 10  # First 10 pass, last 10 fail
            record_calibration_result(task_id=task.id, passed=passed)

        # Verify calibration data reflects 20 attempts
        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal is not None
        assert cal.total_attempts == 20
        assert cal.total_passes == 10
        assert cal.total_failures == 10
        assert cal.empirical_pass_rate == pytest.approx(0.5)


# ============================================================
# Step 2: Simulate only 10 passing (50% pass rate, expected 85%)
# ============================================================


class TestStep2SimulatePassRate:
    """Step 2: With 10/20 passing, empirical rate = 0.5, expected = 0.85."""

    def test_empirical_pass_rate_is_50_percent(self, project, tasks_20):
        """After recording 10 pass + 10 fail, empirical rate should be 0.5."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal.empirical_pass_rate == pytest.approx(0.5)

    def test_expected_pass_rate_is_85_percent(self, project, tasks_20):
        """The expected pass rate for bucket 0.8-0.9 should be 0.85 (midpoint)."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is not None
        assert result["expected_pass_rate"] == pytest.approx(0.85)

    def test_sample_size_is_20(self, project, tasks_20):
        """Sample size should be 20 after recording all results."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result["sample_size"] == 20


# ============================================================
# Step 3: Verify calibration drift calculated as -0.35
# ============================================================


class TestStep3VerifyDrift:
    """Step 3: drift = empirical(0.5) - expected(0.85) = -0.35."""

    def test_drift_is_minus_0_35(self, project, tasks_20):
        """Drift should be 0.5 - 0.85 = -0.35."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is not None
        assert result["drift"] == pytest.approx(-0.35)

    def test_drift_persisted_in_database(self, project, tasks_20):
        """Drift value should be stored in the calibration_data table."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal.drift == pytest.approx(-0.35)

    def test_drift_exceeds_threshold(self, project, tasks_20):
        """Absolute drift of 0.35 exceeds the 0.15 threshold."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert abs(result["drift"]) > 0.15


# ============================================================
# Step 4: Verify calibration alert created with direction=overconfident
# ============================================================


class TestStep4VerifyAlert:
    """Step 4: Alert created with direction='overconfident' for drift=-0.35."""

    def test_alert_created_for_drift(self, project, tasks_20):
        """check_and_create_calibration_alert should create alert for drift=-0.35."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert is not None
        assert isinstance(alert, CalibrationAlert)

    def test_alert_direction_overconfident(self, project, tasks_20):
        """Alert direction should be 'overconfident' (negative drift)."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert.direction == "overconfident"

    def test_alert_drift_amount(self, project, tasks_20):
        """Alert drift_amount should be -0.35."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert.drift_amount == pytest.approx(-0.35)

    def test_alert_sample_size(self, project, tasks_20):
        """Alert sample_size should be 20."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert.sample_size == 20

    def test_alert_persisted_in_database(self, project, tasks_20):
        """Alert should be stored in calibration_alerts table."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT id, direction, drift_amount, sample_size "
                "FROM calibration_alerts WHERE id = ?",
                (alert.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[1] == "overconfident"
        assert row[2] == pytest.approx(-0.35)
        assert row[3] == 20

    def test_alert_in_list(self, project, tasks_20):
        """Alert should appear in list_calibration_alerts."""
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        alerts = list_calibration_alerts(project_id=project.id)
        assert len(alerts) >= 1
        assert any(a.id == alert.id for a in alerts)


# ============================================================
# Step 5: Verify alert is visible in status command
# ============================================================


class TestStep5AlertVisibleInStatus:
    """Step 5: Calibration alert is visible in the status command output."""

    def test_status_shows_calibration_alert(self, tmp_db, project, tasks_20):
        """Status command output should contain the calibration alert info."""
        from bob3.cli import main

        # Record calibration results and create alert
        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status"],
            env={"BOB3_DATABASE_PATH": str(tmp_db)},
        )
        assert result.exit_code == 0, f"status command failed: {result.output}"
        output = result.output.lower()
        assert "overconfident" in output, (
            f"Expected 'overconfident' in status output: {result.output}"
        )

    def test_status_shows_drift_amount(self, tmp_db, project, tasks_20):
        """Status command output should include the drift amount."""
        from bob3.cli import main

        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status"],
            env={"BOB3_DATABASE_PATH": str(tmp_db)},
        )
        assert result.exit_code == 0, f"status command failed: {result.output}"
        assert "-0.35" in result.output, (
            f"Expected drift '-0.35' in status output: {result.output}"
        )

    def test_status_shows_calibration_alerts_heading(self, tmp_db, project, tasks_20):
        """Status command output should include 'Calibration Alerts' heading."""
        from bob3.cli import main

        for i, task in enumerate(tasks_20):
            record_calibration_result(task_id=task.id, passed=(i < 10))

        check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status"],
            env={"BOB3_DATABASE_PATH": str(tmp_db)},
        )
        assert result.exit_code == 0, f"status command failed: {result.output}"
        assert "calibration alert" in result.output.lower(), (
            f"Expected 'Calibration Alert' in status output: {result.output}"
        )

    def test_no_alerts_section_when_no_drift(self, tmp_db, project, feature):
        """Status command should not show calibration alerts if none exist."""
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status"],
            env={"BOB3_DATABASE_PATH": str(tmp_db)},
        )
        assert result.exit_code == 0, f"status command failed: {result.output}"
        assert "calibration alert" not in result.output.lower(), (
            f"Unexpected 'Calibration Alert' in status output with no alerts: {result.output}"
        )


# ============================================================
# Full E2E integration: All 5 steps in one test
# ============================================================


class TestFullE2ECalibrationDriftDetection:
    """Full end-to-end: all 5 acceptance criteria in one comprehensive test."""

    def test_complete_calibration_drift_detection_workflow(
        self, tmp_db, project, feature, tasks_20
    ):
        """Complete E2E: 20 tasks -> 10 pass -> drift -0.35 -> alert -> visible in status."""
        from bob3.cli import main

        # ---- Step 1: Execute 20 tasks with confidence 0.8-0.9 ----
        assert len(tasks_20) == 20
        for task in tasks_20:
            assert task.task_class == "greenfield_impl"

        # ---- Step 2: Simulate only 10 passing (50% pass rate, expected 85%) ----
        for i, task in enumerate(tasks_20):
            passed = i < 10
            record_calibration_result(task_id=task.id, passed=passed)

        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal is not None
        assert cal.total_attempts == 20
        assert cal.total_passes == 10
        assert cal.total_failures == 10
        assert cal.empirical_pass_rate == pytest.approx(0.5)

        # ---- Step 3: Verify calibration drift calculated as -0.35 ----
        drift_result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert drift_result is not None
        assert drift_result["empirical_pass_rate"] == pytest.approx(0.5)
        assert drift_result["expected_pass_rate"] == pytest.approx(0.85)
        assert drift_result["drift"] == pytest.approx(-0.35)
        assert drift_result["sample_size"] == 20

        # Verify drift persisted
        cal_after = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal_after.drift == pytest.approx(-0.35)

        # ---- Step 4: Verify calibration alert created with direction=overconfident ----
        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert is not None
        assert isinstance(alert, CalibrationAlert)
        assert alert.direction == "overconfident"
        assert alert.drift_amount == pytest.approx(-0.35)
        assert alert.sample_size == 20
        assert alert.task_class == "greenfield_impl"
        assert alert.confidence_bucket == "0.8-0.9"
        assert alert.project_id == project.id
        assert alert.acknowledged is False

        # Verify alert persisted in database
        with connect() as conn:
            cursor = conn.execute(
                "SELECT id, direction, drift_amount, sample_size, acknowledged "
                "FROM calibration_alerts WHERE id = ?",
                (alert.id,),
            )
            row = cursor.fetchone()
        assert row is not None
        assert row[1] == "overconfident"
        assert row[2] == pytest.approx(-0.35)
        assert row[3] == 20
        assert row[4] == 0  # Not acknowledged

        # Verify alert in list
        alerts = list_calibration_alerts(project_id=project.id)
        assert len(alerts) >= 1
        assert any(a.id == alert.id for a in alerts)

        # ---- Step 5: Verify alert is visible in status command ----
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["status"],
            env={"BOB3_DATABASE_PATH": str(tmp_db)},
        )
        assert result.exit_code == 0, f"status command failed: {result.output}"

        output = result.output
        output_lower = output.lower()

        # Alert heading visible
        assert "calibration alert" in output_lower, (
            f"Expected 'Calibration Alert' in status output: {output}"
        )
        # Direction visible
        assert "overconfident" in output_lower, (
            f"Expected 'overconfident' in status output: {output}"
        )
        # Drift amount visible
        assert "-0.35" in output, (
            f"Expected drift '-0.35' in status output: {output}"
        )
        # Task class visible
        assert "greenfield_impl" in output, (
            f"Expected 'greenfield_impl' in status output: {output}"
        )
        # Confidence bucket visible
        assert "0.8-0.9" in output, (
            f"Expected '0.8-0.9' in status output: {output}"
        )
        # Sample size visible
        assert "20" in output, (
            f"Expected sample size '20' in status output: {output}"
        )

    def test_e2e_with_direct_calibration_seeding(self, tmp_db, project, feature):
        """Alternative E2E: seed calibration directly without tasks, verify full workflow."""
        from bob3.cli import main

        # Step 1 & 2: Seed 20 attempts directly (10 pass, 10 fail)
        for _ in range(10):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
            )
        for _ in range(10):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=False,
            )

        # Step 3: Verify drift = -0.35
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result["drift"] == pytest.approx(-0.35)

        # Step 4: Create alert
        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert is not None
        assert alert.direction == "overconfident"
        assert alert.drift_amount == pytest.approx(-0.35)

        # Step 5: Verify visible in status
        runner = CliRunner()
        status_result = runner.invoke(
            main,
            ["status"],
            env={"BOB3_DATABASE_PATH": str(tmp_db)},
        )
        assert status_result.exit_code == 0
        assert "overconfident" in status_result.output.lower()
        assert "-0.35" in status_result.output

    def test_e2e_calibration_view_shows_drift(self, tmp_db, project, feature):
        """Verify the calibration_drift_summary view reflects the drift data."""
        # Seed data
        for _ in range(10):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
            )
        for _ in range(10):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=False,
            )

        # Calculate drift to persist it
        calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        # Query the view
        with connect() as conn:
            cursor = conn.execute(
                "SELECT task_class, confidence_bucket, empirical_pass_rate, "
                "expected_pass_rate, drift, total_attempts, status "
                "FROM calibration_drift_summary "
                "WHERE task_class = 'greenfield_impl' "
                "AND confidence_bucket = '0.8-0.9'"
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == "greenfield_impl"
        assert row[1] == "0.8-0.9"
        assert row[2] == pytest.approx(0.5)  # empirical_pass_rate
        # Note: expected_pass_rate in view uses the stored value, not bucket midpoint
        assert row[4] == pytest.approx(-0.35)  # drift
        assert row[5] == 20  # total_attempts
        assert row[6] == "overconfident"  # status from view
