"""Tests for F019: Database operations for calibration_data table."""

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
        name="Calibration Test Project",
        workspace_path="/tmp/cal-test",
    )


# ============================================================
# Step 1: create_or_update_calibration()
# ============================================================


class TestCreateOrUpdateCalibration:
    """Step 1: create_or_update_calibration() inserts or updates a calibration record."""

    def test_create_calibration_returns_model(self, project):
        from bob3.db import create_or_update_calibration
        from bob3.models import CalibrationData

        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        assert isinstance(cal, CalibrationData)

    def test_create_calibration_sets_id(self, project):
        from bob3.db import create_or_update_calibration

        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        assert cal.id is not None
        assert len(cal.id) > 0

    def test_create_calibration_initial_pass(self, project):
        from bob3.db import create_or_update_calibration

        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        assert cal.total_attempts == 1
        assert cal.total_passes == 1
        assert cal.total_failures == 0
        assert cal.empirical_pass_rate == 1.0

    def test_create_calibration_initial_fail(self, project):
        from bob3.db import create_or_update_calibration

        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=False,
        )
        assert cal.total_attempts == 1
        assert cal.total_passes == 0
        assert cal.total_failures == 1
        assert cal.empirical_pass_rate == 0.0

    def test_update_calibration_increments_counters(self, project):
        from bob3.db import create_or_update_calibration

        # First attempt - pass
        create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        # Second attempt - pass
        create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        # Third attempt - fail
        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=False,
        )
        assert cal.total_attempts == 3
        assert cal.total_passes == 2
        assert cal.total_failures == 1

    def test_update_calibration_empirical_pass_rate(self, project):
        from bob3.db import create_or_update_calibration

        create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.7-0.8",
            passed=True,
        )
        create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.7-0.8",
            passed=True,
        )
        create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.7-0.8",
            passed=False,
        )
        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.7-0.8",
            passed=True,
        )
        # 3 passes out of 4
        assert cal.empirical_pass_rate == pytest.approx(0.75)

    def test_calibration_persists_to_database(self, db_path, project):
        from bob3.db import create_or_update_calibration

        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="bug_fix",
            confidence_bucket="0.9-1.0",
            passed=True,
        )

        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(
                "SELECT task_class, confidence_bucket, total_attempts, total_passes "
                "FROM calibration_data WHERE id = ?",
                (cal.id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "bug_fix"
            assert row[1] == "0.9-1.0"
            assert row[2] == 1
            assert row[3] == 1
        finally:
            conn.close()

    def test_calibration_separate_buckets_are_independent(self, project):
        from bob3.db import create_or_update_calibration

        cal_low = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
            passed=True,
        )
        cal_high = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.9-1.0",
            passed=False,
        )
        assert cal_low.total_attempts == 1
        assert cal_low.total_passes == 1
        assert cal_high.total_attempts == 1
        assert cal_high.total_failures == 1

    def test_calibration_separate_task_classes_are_independent(self, project):
        from bob3.db import create_or_update_calibration

        cal_impl = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        cal_refactor = create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.8-0.9",
            passed=False,
        )
        assert cal_impl.total_passes == 1
        assert cal_impl.total_failures == 0
        assert cal_refactor.total_passes == 0
        assert cal_refactor.total_failures == 1

    def test_calibration_with_expected_pass_rate(self, project):
        from bob3.db import create_or_update_calibration

        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
            expected_pass_rate=0.85,
        )
        assert cal.expected_pass_rate == 0.85

    def test_calibration_sets_last_updated(self, project):
        from bob3.db import create_or_update_calibration

        cal = create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        assert cal.last_updated is not None

    def test_calibration_without_project(self, db_path):
        from bob3.db import create_or_update_calibration

        cal = create_or_update_calibration(
            project_id=None,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        assert cal.project_id is None
        assert cal.total_attempts == 1


# ============================================================
# Step 2: get_calibration()
# ============================================================


class TestGetCalibration:
    """Step 2: get_calibration() retrieves calibration data by composite key."""

    def test_get_calibration_returns_model(self, project):
        from bob3.db import create_or_update_calibration, get_calibration
        from bob3.models import CalibrationData

        create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        result = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert isinstance(result, CalibrationData)

    def test_get_calibration_correct_fields(self, project):
        from bob3.db import create_or_update_calibration, get_calibration

        create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.7-0.8",
            passed=True,
            expected_pass_rate=0.75,
        )
        create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.7-0.8",
            passed=False,
        )

        result = get_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.7-0.8",
        )
        assert result.task_class == "refactor"
        assert result.confidence_bucket == "0.7-0.8"
        assert result.total_attempts == 2
        assert result.total_passes == 1
        assert result.total_failures == 1
        assert result.empirical_pass_rate == pytest.approx(0.5)
        assert result.expected_pass_rate == 0.75

    def test_get_calibration_not_found_returns_none(self, db_path):
        from bob3.db import get_calibration

        result = get_calibration(
            project_id="nonexistent",
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is None

    def test_get_calibration_wrong_bucket_returns_none(self, project):
        from bob3.db import create_or_update_calibration, get_calibration

        create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
        )
        result = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
        )
        assert result is None

    def test_get_calibration_without_project(self, db_path):
        from bob3.db import create_or_update_calibration, get_calibration

        create_or_update_calibration(
            project_id=None,
            task_class="bug_fix",
            confidence_bucket="0.9-1.0",
            passed=True,
        )
        result = get_calibration(
            project_id=None,
            task_class="bug_fix",
            confidence_bucket="0.9-1.0",
        )
        assert result is not None
        assert result.project_id is None
        assert result.total_attempts == 1


# ============================================================
# Step 3: calculate_drift()
# ============================================================


class TestCalculateDrift:
    """Step 3: calculate_drift() computes drift between empirical and expected rates."""

    def test_drift_overconfident(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # Expected pass rate 0.85, but empirical is lower
        for _ in range(7):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
                expected_pass_rate=0.85,
            )
        for _ in range(3):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=False,
                expected_pass_rate=0.85,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        # empirical = 0.7, expected = 0.85, drift = 0.7 - 0.85 = -0.15
        assert result is not None
        assert result["empirical_pass_rate"] == pytest.approx(0.7)
        assert result["expected_pass_rate"] == pytest.approx(0.85)
        assert result["drift"] == pytest.approx(-0.15)
        assert result["direction"] == "overconfident"

    def test_drift_underconfident(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # Expected pass rate 0.5, but empirical is higher
        for _ in range(9):
            create_or_update_calibration(
                project_id=project.id,
                task_class="bug_fix",
                confidence_bucket="0.4-0.5",
                passed=True,
                expected_pass_rate=0.45,
            )
        for _ in range(1):
            create_or_update_calibration(
                project_id=project.id,
                task_class="bug_fix",
                confidence_bucket="0.4-0.5",
                passed=False,
                expected_pass_rate=0.45,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="bug_fix",
            confidence_bucket="0.4-0.5",
        )
        # empirical = 0.9, expected = 0.45, drift = 0.9 - 0.45 = 0.45
        assert result is not None
        assert result["empirical_pass_rate"] == pytest.approx(0.9)
        assert result["expected_pass_rate"] == pytest.approx(0.45)
        assert result["drift"] == pytest.approx(0.45)
        assert result["direction"] == "underconfident"

    def test_drift_calibrated(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # Expected and empirical roughly match
        for _ in range(8):
            create_or_update_calibration(
                project_id=project.id,
                task_class="refactor",
                confidence_bucket="0.8-0.9",
                passed=True,
                expected_pass_rate=0.85,
            )
        for _ in range(2):
            create_or_update_calibration(
                project_id=project.id,
                task_class="refactor",
                confidence_bucket="0.8-0.9",
                passed=False,
                expected_pass_rate=0.85,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.8-0.9",
        )
        # empirical = 0.8, expected = 0.85, drift = -0.05
        assert result is not None
        assert result["drift"] == pytest.approx(-0.05)
        assert result["direction"] == "calibrated"

    def test_drift_not_found_returns_none(self, db_path):
        from bob3.db import calculate_drift

        result = calculate_drift(
            project_id="nonexistent",
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result is None

    def test_drift_no_expected_rate_returns_none(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # Create calibration without expected_pass_rate
        create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
            passed=True,
        )
        result = calculate_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
        )
        assert result is None

    def test_drift_persisted_to_database(self, db_path, project):
        from bob3.db import create_or_update_calibration, calculate_drift, get_calibration

        for _ in range(8):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
                expected_pass_rate=0.85,
            )
        for _ in range(2):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=False,
                expected_pass_rate=0.85,
            )

        calculate_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )

        # Verify drift was persisted
        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal.drift == pytest.approx(-0.05)

    def test_drift_returns_sample_size(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        for _ in range(5):
            create_or_update_calibration(
                project_id=project.id,
                task_class="test_writing",
                confidence_bucket="0.6-0.7",
                passed=True,
                expected_pass_rate=0.65,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="test_writing",
            confidence_bucket="0.6-0.7",
        )
        assert result["sample_size"] == 5


# ============================================================
# Step 4: Calibration tracking lifecycle
# ============================================================


class TestCalibrationTracking:
    """Step 4: Test calibration tracking across multiple task completions."""

    def test_tracking_multiple_task_classes(self, project):
        from bob3.db import create_or_update_calibration, get_calibration

        # Track greenfield_impl
        for _ in range(5):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
            )

        # Track refactor
        for _ in range(3):
            create_or_update_calibration(
                project_id=project.id,
                task_class="refactor",
                confidence_bucket="0.8-0.9",
                passed=True,
            )
        create_or_update_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.8-0.9",
            passed=False,
        )

        impl = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        refactor = get_calibration(
            project_id=project.id,
            task_class="refactor",
            confidence_bucket="0.8-0.9",
        )

        assert impl.total_attempts == 5
        assert impl.empirical_pass_rate == pytest.approx(1.0)
        assert refactor.total_attempts == 4
        assert refactor.empirical_pass_rate == pytest.approx(0.75)

    def test_tracking_multiple_confidence_buckets(self, project):
        from bob3.db import create_or_update_calibration, get_calibration

        # Low confidence bucket - more failures
        for _ in range(3):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.5-0.6",
                passed=True,
            )
        for _ in range(2):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.5-0.6",
                passed=False,
            )

        # High confidence bucket - more passes
        for _ in range(9):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.9-1.0",
                passed=True,
            )
        create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.9-1.0",
            passed=False,
        )

        low = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.5-0.6",
        )
        high = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.9-1.0",
        )

        assert low.empirical_pass_rate == pytest.approx(0.6)
        assert high.empirical_pass_rate == pytest.approx(0.9)

    def test_tracking_zero_pass_rate(self, project):
        from bob3.db import create_or_update_calibration

        for _ in range(5):
            cal = create_or_update_calibration(
                project_id=project.id,
                task_class="infrastructure",
                confidence_bucket="0.5-0.6",
                passed=False,
            )
        assert cal.empirical_pass_rate == pytest.approx(0.0)
        assert cal.total_failures == 5

    def test_tracking_perfect_pass_rate(self, project):
        from bob3.db import create_or_update_calibration

        for _ in range(10):
            cal = create_or_update_calibration(
                project_id=project.id,
                task_class="test_writing",
                confidence_bucket="0.9-1.0",
                passed=True,
            )
        assert cal.empirical_pass_rate == pytest.approx(1.0)
        assert cal.total_passes == 10


# ============================================================
# Step 5: Drift calculations accuracy
# ============================================================


class TestDriftCalculations:
    """Step 5: Verify drift calculations are correct."""

    def test_zero_drift_when_perfectly_calibrated(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # 80% pass rate matches 80% expected
        for _ in range(80):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
                expected_pass_rate=0.80,
            )
        for _ in range(20):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=False,
                expected_pass_rate=0.80,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result["drift"] == pytest.approx(0.0)
        assert result["direction"] == "calibrated"

    def test_large_overconfidence_drift(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # Expected 90% but only 40% pass
        for _ in range(4):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.9-1.0",
                passed=True,
                expected_pass_rate=0.90,
            )
        for _ in range(6):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.9-1.0",
                passed=False,
                expected_pass_rate=0.90,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.9-1.0",
        )
        # drift = 0.4 - 0.9 = -0.5
        assert result["drift"] == pytest.approx(-0.5)
        assert result["direction"] == "overconfident"

    def test_large_underconfidence_drift(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # Expected 30% but actually 90% pass
        for _ in range(9):
            create_or_update_calibration(
                project_id=project.id,
                task_class="bug_fix",
                confidence_bucket="0.3-0.4",
                passed=True,
                expected_pass_rate=0.30,
            )
        create_or_update_calibration(
            project_id=project.id,
            task_class="bug_fix",
            confidence_bucket="0.3-0.4",
            passed=False,
            expected_pass_rate=0.30,
        )

        result = calculate_drift(
            project_id=project.id,
            task_class="bug_fix",
            confidence_bucket="0.3-0.4",
        )
        # drift = 0.9 - 0.3 = 0.6
        assert result["drift"] == pytest.approx(0.6)
        assert result["direction"] == "underconfident"

    def test_drift_threshold_boundaries(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # drift = 0.10 is within calibrated range (abs(drift) <= 0.15)
        # empirical = 0.80, expected = 0.70 => drift = 0.10
        for _ in range(80):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=True,
                expected_pass_rate=0.70,
            )
        for _ in range(20):
            create_or_update_calibration(
                project_id=project.id,
                task_class="greenfield_impl",
                confidence_bucket="0.8-0.9",
                passed=False,
                expected_pass_rate=0.70,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert result["drift"] == pytest.approx(0.10)
        assert result["direction"] == "calibrated"

    def test_drift_just_over_threshold_is_underconfident(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        # drift = 0.20 is above threshold (> 0.15)
        # empirical = 0.90, expected = 0.70 => drift = 0.20
        for _ in range(90):
            create_or_update_calibration(
                project_id=project.id,
                task_class="bug_fix",
                confidence_bucket="0.6-0.7",
                passed=True,
                expected_pass_rate=0.70,
            )
        for _ in range(10):
            create_or_update_calibration(
                project_id=project.id,
                task_class="bug_fix",
                confidence_bucket="0.6-0.7",
                passed=False,
                expected_pass_rate=0.70,
            )

        result = calculate_drift(
            project_id=project.id,
            task_class="bug_fix",
            confidence_bucket="0.6-0.7",
        )
        assert result["drift"] == pytest.approx(0.20)
        assert result["direction"] == "underconfident"

    def test_drift_calculation_with_single_attempt(self, project):
        from bob3.db import create_or_update_calibration, calculate_drift

        create_or_update_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
            passed=True,
            expected_pass_rate=0.85,
        )

        result = calculate_drift(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        # empirical = 1.0, expected = 0.85, drift = 0.15
        assert result is not None
        assert result["drift"] == pytest.approx(0.15)
        assert result["sample_size"] == 1


# ============================================================
# R4-004: create_or_update_calibration must be CALLED from the
# orchestrator after every feature execution.
#
# Before this fix the calibration_data table was empty in production
# because nothing in the orchestration loop wrote to it. Drift detection
# (F050) had no inputs and ``show-calibration`` was vacuous.
# ============================================================


class TestCalibrationWiredIntoOrchestrator:
    """R4-004: Orchestrator must call create_or_update_calibration."""

    @pytest.mark.asyncio
    async def test_orchestrator_records_calibration_on_success(self, project):
        """A feature that lands cleanly must produce a 'passed' calibration row."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_calibration,
            get_feature,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import (
            OrchestrationLoop,
            _DEFAULT_TASK_CLASS_FEATURE,
        )

        f = create_feature(
            project_id=project.id,
            name="Calibrated success",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.85,
            conf_impl_correctness=0.85,
            conf_test_adequacy=0.85,
            readiness_score=0.85,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=100,
                num_turns=1,
                total_cost_usd=0.05,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.run_verification_checklist",
            return_value={"passed": True, "summary": "ok", "checks": []},
        ), patch(
            "bob3.orchestrator.run_loop.git_commit_feature",
            return_value="deadbeef",
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            return_value=None,  # skip regression detection
        ):
            await loop.execute_feature(feature)

        # conf_impl_correctness=0.85 lands in the "0.8-0.9" bucket.
        cal = get_calibration(
            project_id=project.id,
            task_class=_DEFAULT_TASK_CLASS_FEATURE,
            confidence_bucket="0.8-0.9",
        )
        assert cal is not None, (
            "execute_feature must call create_or_update_calibration on "
            "every feature; calibration_data table is empty (R4-004 "
            "wire-up missing)."
        )
        assert cal.total_attempts == 1
        assert cal.total_passes == 1
        assert cal.total_failures == 0
        assert cal.empirical_pass_rate == pytest.approx(1.0)
        assert cal.expected_pass_rate == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_orchestrator_records_calibration_on_verification_failure(
        self, project
    ):
        """A feature whose verification fails must produce a 'failed' row."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_calibration,
            get_feature,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import (
            OrchestrationLoop,
            _DEFAULT_TASK_CLASS_FEATURE,
        )

        f = create_feature(
            project_id=project.id,
            name="Calibrated fail",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.7,
            conf_impl_correctness=0.7,
            conf_test_adequacy=0.7,
            readiness_score=0.85,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=100,
                num_turns=1,
                total_cost_usd=0.05,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.run_verification_checklist",
            return_value={
                "passed": False,
                "summary": "tests failed",
                "checks": [],
            },
        ), patch(
            "bob3.orchestrator.run_loop.git_commit_feature",
            return_value="deadbeef",
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            return_value=None,
        ):
            await loop.execute_feature(feature)

        # conf_impl_correctness=0.7 lands in the "0.7-0.8" bucket.
        cal = get_calibration(
            project_id=project.id,
            task_class=_DEFAULT_TASK_CLASS_FEATURE,
            confidence_bucket="0.7-0.8",
        )
        assert cal is not None
        assert cal.total_attempts == 1
        assert cal.total_passes == 0
        assert cal.total_failures == 1
        assert cal.empirical_pass_rate == pytest.approx(0.0)
        assert cal.expected_pass_rate == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_orchestrator_records_calibration_on_subagent_error(
        self, project
    ):
        """A feature whose sub-agent errors out must still record calibration."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_calibration,
            get_feature,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import (
            OrchestrationLoop,
            _DEFAULT_TASK_CLASS_FEATURE,
        )

        f = create_feature(
            project_id=project.id,
            name="Subagent error",
            status="ready",
            priority=10,
            risk_category="medium",
        )
        update_feature(
            f.id,
            conf_spec_understanding=0.6,
            conf_impl_correctness=0.6,
            conf_test_adequacy=0.6,
            readiness_score=0.9,
        )
        feature = get_feature(f.id)

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="",
                is_error=True,
                error_message="boom",
                duration_ms=50,
                num_turns=1,
                total_cost_usd=0.01,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        with patch(
            "bob3.orchestrator.run_loop.spawn_sub_agent",
            new_callable=AsyncMock,
            side_effect=mock_spawn,
        ), patch(
            "bob3.orchestrator.run_loop.git_get_status",
            return_value={"sha": "abc123"},
        ), patch(
            "bob3.orchestrator.run_loop.capture_pytest_snapshot",
            return_value=None,
        ):
            await loop.execute_feature(feature)

        cal = get_calibration(
            project_id=project.id,
            task_class=_DEFAULT_TASK_CLASS_FEATURE,
            confidence_bucket="0.6-0.7",
        )
        assert cal is not None, (
            "Calibration row must be written even when the sub-agent "
            "errors; the feature confidence was a wrong prediction."
        )
        assert cal.total_failures == 1
        assert cal.total_passes == 0

    @pytest.mark.asyncio
    async def test_orchestrator_calibration_accumulates_across_features(
        self, project
    ):
        """Two features in the same bucket should produce one row with two attempts."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from bob3.db import (
            create_feature,
            get_calibration,
            get_feature,
            update_feature,
        )
        from bob3.orchestrator.claude_executor import (
            ExecutionResult,
            SpawnResult,
        )
        from bob3.orchestrator.run_loop import (
            OrchestrationLoop,
            _DEFAULT_TASK_CLASS_FEATURE,
        )

        loop = OrchestrationLoop(project_id=project.id, workspace="/tmp/w")

        async def mock_spawn(*args, **kwargs):
            res = ExecutionResult(
                text="done",
                is_error=False,
                duration_ms=10,
                num_turns=1,
                total_cost_usd=0.01,
            )
            agent_run = MagicMock()
            agent_run.id = str(uuid.uuid4())
            return SpawnResult(execution_result=res, agent_run=agent_run)

        for i, vp in enumerate([True, False]):
            f = create_feature(
                project_id=project.id,
                name=f"Feature {i}",
                status="ready",
                priority=10,
                risk_category="medium",
            )
            update_feature(
                f.id,
                conf_spec_understanding=0.85,
                conf_impl_correctness=0.85,
                conf_test_adequacy=0.85,
                readiness_score=0.85,
            )
            feature = get_feature(f.id)
            with patch(
                "bob3.orchestrator.run_loop.spawn_sub_agent",
                new_callable=AsyncMock,
                side_effect=mock_spawn,
            ), patch(
                "bob3.orchestrator.run_loop.run_verification_checklist",
                return_value={
                    "passed": vp,
                    "summary": "ok" if vp else "bad",
                    "checks": [],
                },
            ), patch(
                "bob3.orchestrator.run_loop.git_commit_feature",
                return_value=f"sha{i}",
            ), patch(
                "bob3.orchestrator.run_loop.git_get_status",
                return_value={"sha": f"pre{i}"},
            ), patch(
                "bob3.orchestrator.run_loop.capture_pytest_snapshot",
                return_value=None,
            ):
                await loop.execute_feature(feature)

        cal = get_calibration(
            project_id=project.id,
            task_class=_DEFAULT_TASK_CLASS_FEATURE,
            confidence_bucket="0.8-0.9",
        )
        assert cal is not None
        assert cal.total_attempts == 2
        assert cal.total_passes == 1
        assert cal.total_failures == 1
        assert cal.empirical_pass_rate == pytest.approx(0.5)
