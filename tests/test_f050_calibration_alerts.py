"""Tests for F050: Implement calibration alert creation for large drift."""

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
def project(db_path):
    """Create a test project for foreign key references."""
    from bob.db import create_project

    return create_project(
        name="Calibration Alert Test",
        workspace_path="/tmp/cal-alert-test",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature."""
    from bob.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Test Feature",
        status="executing",
    )


def _seed_calibration(project, task_class, confidence_bucket, passes, failures, expected_pass_rate=None):
    """Helper to seed a calibration record with specific pass/fail counts."""
    from bob.db import create_or_update_calibration

    for _ in range(passes):
        create_or_update_calibration(
            project_id=project.id,
            task_class=task_class,
            confidence_bucket=confidence_bucket,
            passed=True,
            expected_pass_rate=expected_pass_rate,
        )
    for _ in range(failures):
        create_or_update_calibration(
            project_id=project.id,
            task_class=task_class,
            confidence_bucket=confidence_bucket,
            passed=False,
            expected_pass_rate=expected_pass_rate,
        )


# ============================================================
# Step 1: create_calibration_alert() function exists
# ============================================================


class TestCreateCalibrationAlertExists:
    """Step 1: create_calibration_alert() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob.db import create_calibration_alert

        assert callable(create_calibration_alert)

    def test_returns_calibration_alert_model(self, project, feature):
        from bob.db import create_calibration_alert
        from bob.models import CalibrationAlert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )
        assert isinstance(alert, CalibrationAlert)


# ============================================================
# Step 2: Trigger when |drift| > 0.15
# ============================================================


class TestDriftThresholdTriggering:
    """Step 2: Alert is triggered when |drift| > 0.15."""

    def test_alert_created_for_large_negative_drift(self, project, feature):
        """Drift of -0.25 (|drift| > 0.15) should create alert."""
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )
        assert alert is not None
        assert alert.drift_amount == pytest.approx(-0.25)

    def test_alert_created_for_large_positive_drift(self, project, feature):
        """Drift of 0.35 (|drift| > 0.15) should create alert."""
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
            drift_amount=0.35,
            direction="underconfident",
            sample_size=10,
        )
        assert alert is not None
        assert alert.drift_amount == pytest.approx(0.35)

    def test_alert_has_correct_sample_size(self, project, feature):
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=20,
        )
        assert alert.sample_size == 20


# ============================================================
# Step 3: Set direction (overconfident or underconfident)
# ============================================================


class TestAlertDirection:
    """Step 3: Alert direction is correctly set."""

    def test_overconfident_direction(self, project, feature):
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )
        assert alert.direction == "overconfident"

    def test_underconfident_direction(self, project, feature):
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
            drift_amount=0.35,
            direction="underconfident",
            sample_size=10,
        )
        assert alert.direction == "underconfident"


# ============================================================
# Step 4: Store in calibration_alerts table
# ============================================================


class TestAlertStoredInDatabase:
    """Step 4: Alert is persisted in the calibration_alerts table."""

    def test_alert_persisted_and_retrievable(self, project, feature):
        from bob.db import connect, create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT id, project_id, task_class, confidence_bucket, "
                "drift_amount, direction, sample_size, acknowledged "
                "FROM calibration_alerts WHERE id = ?",
                (alert.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == alert.id
        assert row[1] == project.id
        assert row[2] == "greenfield_impl"
        assert row[3] == "0.8-0.9"
        assert row[4] == pytest.approx(-0.25)
        assert row[5] == "overconfident"
        assert row[6] == 10
        assert row[7] == 0  # acknowledged defaults to False

    def test_alert_defaults_acknowledged_false(self, project, feature):
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )
        assert alert.acknowledged is False

    def test_alert_defaults_action_taken_none(self, project, feature):
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )
        assert alert.action_taken is None

    def test_multiple_alerts_can_be_stored(self, project, feature):
        from bob.db import connect, create_calibration_alert

        create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )
        create_calibration_alert(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.5-0.6",
            drift_amount=0.35,
            direction="underconfident",
            sample_size=15,
        )

        with connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM calibration_alerts")
            count = cursor.fetchone()[0]
        assert count == 2

    def test_alert_has_created_at_timestamp(self, project, feature):
        from bob.db import create_calibration_alert

        alert = create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            drift_amount=-0.25,
            direction="overconfident",
            sample_size=10,
        )
        assert alert.created_at is not None


# ============================================================
# Step 5: Acceptance test - drift of -0.25, verify alert with
#          direction='overconfident'
# ============================================================


class TestAcceptanceCriteria:
    """Step 5: Create drift of -0.25, verify alert created with direction='overconfident'."""

    def test_overconfident_alert_from_drift_minus_0_25(self, project, feature):
        """End-to-end: seed calibration data with drift=-0.25, create alert, verify."""
        from bob.db import calculate_calibration_drift, create_calibration_alert

        # Seed data: 6 pass, 4 fail => empirical = 0.6
        # bucket 0.8-0.9 => expected midpoint = 0.85
        # drift = 0.6 - 0.85 = -0.25
        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)

        drift_result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert drift_result is not None
        assert drift_result["drift"] == pytest.approx(-0.25)
        assert drift_result["direction"] == "overconfident"

        # Now create the alert based on drift result
        alert = create_calibration_alert(
            project_id=project.id,
            task_class=drift_result.get("task_class", "greenfield_impl"),
            confidence_bucket="0.8-0.9",
            drift_amount=drift_result["drift"],
            direction=drift_result["direction"],
            sample_size=drift_result["sample_size"],
        )

        assert alert.drift_amount == pytest.approx(-0.25)
        assert alert.direction == "overconfident"
        assert alert.sample_size == 10
        assert alert.task_class == "greenfield_impl"
        assert alert.confidence_bucket == "0.8-0.9"
        assert alert.project_id == project.id

    def test_check_and_create_alert_for_large_drift(self, project, feature):
        """Test the integrated check_and_create_calibration_alert function."""
        from bob.db import check_and_create_calibration_alert

        # Seed data: 6 pass, 4 fail => empirical = 0.6
        # bucket 0.8-0.9 => expected midpoint = 0.85
        # drift = 0.6 - 0.85 = -0.25 (|drift| > 0.15)
        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert is not None
        assert alert.drift_amount == pytest.approx(-0.25)
        assert alert.direction == "overconfident"

    def test_no_alert_for_small_drift(self, project, feature):
        """Drift within threshold (|drift| <= 0.15) should NOT create alert."""
        from bob.db import check_and_create_calibration_alert

        # 8 pass, 2 fail => empirical = 0.8
        # bucket 0.8-0.9 => expected = 0.85
        # drift = 0.8 - 0.85 = -0.05 (|drift| <= 0.15)
        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 8, 2)

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert is None

    def test_alert_for_underconfident_drift(self, project, feature):
        """Large positive drift should create underconfident alert."""
        from bob.db import check_and_create_calibration_alert

        # 9 pass, 1 fail => empirical = 0.9
        # bucket 0.5-0.6 => expected = 0.55
        # drift = 0.9 - 0.55 = 0.35 (|drift| > 0.15)
        _seed_calibration(project, "greenfield_impl", "0.5-0.6", 9, 1)

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
        )
        assert alert is not None
        assert alert.drift_amount == pytest.approx(0.35)
        assert alert.direction == "underconfident"

    def test_no_alert_for_nonexistent_calibration(self, db_path):
        """No alert if calibration data doesn't exist."""
        from bob.db import check_and_create_calibration_alert

        alert = check_and_create_calibration_alert(
            project_id="nonexistent",
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert alert is None

    def test_no_alert_for_drift_within_threshold(self, project, feature):
        """Drift of ~0.05 (well within threshold) should NOT trigger alert."""
        from bob.db import check_and_create_calibration_alert

        # 8 pass, 2 fail => empirical = 0.8
        # bucket 0.7-0.8 => expected = 0.75
        # drift = 0.8 - 0.75 = 0.05 (|drift| <= 0.15)
        _seed_calibration(project, "greenfield_impl", "0.7-0.8", 8, 2)

        alert = check_and_create_calibration_alert(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.7-0.8",
        )
        assert alert is None
