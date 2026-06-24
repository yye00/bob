"""Tests for F049: Implement calibration drift detection."""

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
        name="Drift Detection Test",
        workspace_path="/tmp/drift-test",
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

    # Seed passes
    for _ in range(passes):
        create_or_update_calibration(
            project_id=project.id,
            task_class=task_class,
            confidence_bucket=confidence_bucket,
            passed=True,
            expected_pass_rate=expected_pass_rate,
        )
    # Seed failures
    for _ in range(failures):
        create_or_update_calibration(
            project_id=project.id,
            task_class=task_class,
            confidence_bucket=confidence_bucket,
            passed=False,
            expected_pass_rate=expected_pass_rate,
        )


# ============================================================
# Step 1: calculate_calibration_drift() function exists
# ============================================================


class TestCalculateCalibrationDriftExists:
    """Step 1: calculate_calibration_drift() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob.db import calculate_calibration_drift

        assert callable(calculate_calibration_drift)


# ============================================================
# Step 2: drift = empirical_pass_rate - expected_pass_rate
# ============================================================


class TestDriftCalculation:
    """Step 2: drift = empirical_pass_rate - expected_pass_rate."""

    def test_drift_positive_when_overperforming(self, project, feature):
        """When empirical > expected, drift is positive (underconfident)."""
        from bob.db import calculate_calibration_drift

        # 9 pass, 1 fail => empirical = 0.9, expected midpoint of 0.5-0.6 = 0.55
        _seed_calibration(project, "greenfield_impl", "0.5-0.6", 9, 1)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
        )
        assert result is not None
        assert result["drift"] == pytest.approx(0.9 - 0.55)

    def test_drift_negative_when_underperforming(self, project, feature):
        """When empirical < expected, drift is negative (overconfident)."""
        from bob.db import calculate_calibration_drift

        # 3 pass, 7 fail => empirical = 0.3, expected midpoint of 0.8-0.9 = 0.85
        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 3, 7)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is not None
        assert result["drift"] == pytest.approx(0.3 - 0.85)

    def test_drift_zero_when_calibrated(self, project, feature):
        """When empirical equals expected, drift is zero."""
        from bob.db import calculate_calibration_drift

        # 85 pass, 15 fail => empirical = 0.85, midpoint of 0.8-0.9 = 0.85
        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 85, 15)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is not None
        assert result["drift"] == pytest.approx(0.0)


# ============================================================
# Step 3: expected_pass_rate based on confidence bucket midpoint
# ============================================================


class TestExpectedPassRateFromBucketMidpoint:
    """Step 3: expected_pass_rate is derived from confidence bucket midpoint."""

    def test_bucket_0_8_0_9_expected_0_85(self, project, feature):
        from bob.db import calculate_calibration_drift

        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 5, 5)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is not None
        assert result["expected_pass_rate"] == pytest.approx(0.85)

    def test_bucket_0_0_0_1_expected_0_05(self, project, feature):
        from bob.db import calculate_calibration_drift

        _seed_calibration(project, "greenfield_impl", "0.0-0.1", 5, 5)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.0-0.1",
        )
        assert result is not None
        assert result["expected_pass_rate"] == pytest.approx(0.05)

    def test_bucket_0_9_1_0_expected_0_95(self, project, feature):
        from bob.db import calculate_calibration_drift

        _seed_calibration(project, "greenfield_impl", "0.9-1.0", 5, 5)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.9-1.0",
        )
        assert result is not None
        assert result["expected_pass_rate"] == pytest.approx(0.95)

    def test_bucket_0_5_0_6_expected_0_55(self, project, feature):
        from bob.db import calculate_calibration_drift

        _seed_calibration(project, "greenfield_impl", "0.5-0.6", 5, 5)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
        )
        assert result is not None
        assert result["expected_pass_rate"] == pytest.approx(0.55)


# ============================================================
# Step 4: Acceptance test - confidence 0.8-0.9, empirical 0.6, drift = -0.25
# ============================================================


class TestAcceptanceCriteria:
    """Step 4: Confidence 0.8-0.9 (expected 0.85), empirical 0.6, drift = -0.25."""

    def test_drift_minus_0_25(self, project, feature):
        from bob.db import calculate_calibration_drift

        # 6 pass, 4 fail => empirical = 0.6
        # bucket 0.8-0.9 => expected midpoint = 0.85
        # drift = 0.6 - 0.85 = -0.25
        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is not None
        assert result["empirical_pass_rate"] == pytest.approx(0.6)
        assert result["expected_pass_rate"] == pytest.approx(0.85)
        assert result["drift"] == pytest.approx(-0.25)
        assert result["direction"] == "overconfident"

    def test_drift_direction_overconfident(self, project, feature):
        """Drift < -0.15 means overconfident."""
        from bob.db import calculate_calibration_drift

        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result["direction"] == "overconfident"

    def test_drift_direction_underconfident(self, project, feature):
        """Drift > 0.15 means underconfident."""
        from bob.db import calculate_calibration_drift

        # 9 pass, 1 fail => empirical = 0.9
        # bucket 0.5-0.6 => expected = 0.55
        # drift = 0.9 - 0.55 = 0.35
        _seed_calibration(project, "greenfield_impl", "0.5-0.6", 9, 1)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
        )
        assert result["direction"] == "underconfident"

    def test_drift_direction_calibrated(self, project, feature):
        """Drift between -0.15 and 0.15 means calibrated."""
        from bob.db import calculate_calibration_drift

        # 8 pass, 2 fail => empirical = 0.8
        # bucket 0.8-0.9 => expected = 0.85
        # drift = 0.8 - 0.85 = -0.05
        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 8, 2)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result["direction"] == "calibrated"

    def test_sample_size_included(self, project, feature):
        """Result includes sample_size (total_attempts)."""
        from bob.db import calculate_calibration_drift

        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result["sample_size"] == 10


# ============================================================
# Step 5: Verify drift is stored in calibration_data table
# ============================================================


class TestDriftStoredInDatabase:
    """Step 5: Drift value is persisted in the calibration_data table."""

    def test_drift_persisted_after_calculation(self, project, feature):
        from bob.db import calculate_calibration_drift, get_calibration

        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)
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
        assert cal is not None
        assert cal.drift == pytest.approx(-0.25)

    def test_drift_none_before_calculation(self, project, feature):
        """Before calling calculate_calibration_drift, drift should be None."""
        from bob.db import get_calibration

        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)
        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal is not None
        assert cal.drift is None

    def test_returns_none_for_nonexistent_record(self, db_path):
        """Returns None when no calibration record exists."""
        from bob.db import calculate_calibration_drift

        result = calculate_calibration_drift(
            project_id="nonexistent",
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is None

    def test_drift_updated_on_recalculation(self, project, feature):
        """Drift is updated when recalculated after more data."""
        from bob.db import calculate_calibration_drift, create_or_update_calibration, get_calibration

        _seed_calibration(project, "greenfield_impl", "0.8-0.9", 6, 4)
        calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        # Add more passes to change empirical rate
        for _ in range(10):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
            )

        # Recalculate drift
        result = calculate_calibration_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        # Now 16 pass, 4 fail => empirical = 0.8, expected = 0.85, drift = -0.05
        assert result is not None
        assert result["drift"] == pytest.approx(0.8 - 0.85)

        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal.drift == pytest.approx(0.8 - 0.85)
