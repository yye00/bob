"""Tests for F048: Calibration data recording after task execution."""

import pathlib

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
        name="Calibration Recording Test",
        workspace_path="/tmp/cal-rec-test",
    )


@pytest.fixture()
def feature(project):
    """Create a test feature."""
    from bob3.db import create_feature

    return create_feature(
        project_id=project.id,
        name="Test Feature",
        status="executing",
    )


def _make_task(project, feature, *, task_class="greenfield_impl", confidence=0.85):
    """Helper to create a task with specific class and confidence."""
    from bob3.db import create_task, update_task

    task = create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="implementation",
        title=f"Test task ({task_class})",
        task_class=task_class,
    )
    update_task(task.id, conf_impl_correctness=confidence)
    return task


# ============================================================
# Step 1: record_calibration_result() function exists
# ============================================================


class TestRecordCalibrationResultExists:
    """Step 1: record_calibration_result() is importable and callable."""

    def test_function_is_importable(self, db_path):
        from bob3.db import record_calibration_result

        assert callable(record_calibration_result)

    def test_returns_calibration_data_model(self, project, feature):
        from bob3.db import record_calibration_result
        from bob3.models import CalibrationData

        task = _make_task(project, feature)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert isinstance(result, CalibrationData)


# ============================================================
# Step 2: Identify task_class and confidence_bucket
# ============================================================


class TestTaskClassAndConfidenceBucket:
    """Step 2: record_calibration_result identifies task_class and confidence_bucket."""

    def test_uses_task_class_from_task(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, task_class="refactor", confidence=0.75)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.task_class == "refactor"

    def test_confidence_bucket_from_impl_correctness(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, confidence=0.85)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.confidence_bucket == "0.8-0.9"

    def test_confidence_bucket_low(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, confidence=0.35)
        result = record_calibration_result(task_id=task.id, passed=False)
        assert result.confidence_bucket == "0.3-0.4"

    def test_confidence_bucket_high(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, confidence=0.95)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.confidence_bucket == "0.9-1.0"

    def test_confidence_bucket_zero(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, confidence=0.0)
        result = record_calibration_result(task_id=task.id, passed=False)
        assert result.confidence_bucket == "0.0-0.1"

    def test_confidence_bucket_one(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, confidence=1.0)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.confidence_bucket == "0.9-1.0"

    def test_confidence_bucket_boundary_0_5(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, confidence=0.5)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.confidence_bucket == "0.5-0.6"

    def test_raises_for_nonexistent_task(self, db_path):
        from bob3.db import record_calibration_result

        with pytest.raises(ValueError, match="not found"):
            record_calibration_result(task_id="nonexistent-id", passed=True)

    def test_raises_for_missing_task_class(self, project, feature):
        from bob3.db import create_task, record_calibration_result

        task = create_task(
            feature_id=feature.id,
            project_id=project.id,
            type="implementation",
            title="No class task",
            task_class=None,
        )
        with pytest.raises(ValueError, match="task_class"):
            record_calibration_result(task_id=task.id, passed=True)


# ============================================================
# Step 3: Update total_attempts, total_passes, total_failures
# ============================================================


class TestCounterUpdates:
    """Step 3: record_calibration_result updates attempt/pass/failure counters."""

    def test_single_pass_updates_counters(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.total_attempts == 1
        assert result.total_passes == 1
        assert result.total_failures == 0

    def test_single_fail_updates_counters(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature)
        result = record_calibration_result(task_id=task.id, passed=False)
        assert result.total_attempts == 1
        assert result.total_passes == 0
        assert result.total_failures == 1

    def test_multiple_results_accumulate(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature)
        record_calibration_result(task_id=task.id, passed=True)
        record_calibration_result(task_id=task.id, passed=True)
        result = record_calibration_result(task_id=task.id, passed=False)
        assert result.total_attempts == 3
        assert result.total_passes == 2
        assert result.total_failures == 1


# ============================================================
# Step 4: Calculate empirical_pass_rate
# ============================================================


class TestEmpiricalPassRate:
    """Step 4: record_calibration_result calculates empirical_pass_rate correctly."""

    def test_pass_rate_single_pass(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.empirical_pass_rate == pytest.approx(1.0)

    def test_pass_rate_single_fail(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature)
        result = record_calibration_result(task_id=task.id, passed=False)
        assert result.empirical_pass_rate == pytest.approx(0.0)

    def test_pass_rate_mixed(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature)
        for _ in range(3):
            record_calibration_result(task_id=task.id, passed=True)
        result = record_calibration_result(task_id=task.id, passed=False)
        assert result.empirical_pass_rate == pytest.approx(0.75)


# ============================================================
# Step 5 & 6: Record 10 greenfield_impl tasks, 7 pass, 3 fail
#              => empirical_pass_rate = 0.7
# ============================================================


class TestAcceptanceCriteria:
    """Steps 5-6: Record 10 greenfield_impl tasks with 0.8-0.9 confidence,
    7 pass, 3 fail, verify empirical_pass_rate = 0.7."""

    def test_ten_tasks_seven_pass_three_fail(self, project, feature):
        from bob3.db import get_calibration, record_calibration_result

        task = _make_task(
            project, feature, task_class="greenfield_impl", confidence=0.85,
        )

        # Record 7 passes
        for _ in range(7):
            record_calibration_result(task_id=task.id, passed=True)

        # Record 3 failures
        for _ in range(3):
            record_calibration_result(task_id=task.id, passed=False)

        # Verify final state
        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal is not None
        assert cal.total_attempts == 10
        assert cal.total_passes == 7
        assert cal.total_failures == 3
        assert cal.empirical_pass_rate == pytest.approx(0.7)

    def test_ten_tasks_from_different_task_objects(self, project, feature):
        """Record results from 10 different task objects with same class/confidence."""
        from bob3.db import create_task, get_calibration, record_calibration_result, update_task

        results = [True] * 7 + [False] * 3
        for i, passed in enumerate(results):
            task = create_task(
                feature_id=feature.id,
                project_id=project.id,
                type="implementation",
                title=f"Greenfield task {i}",
                task_class="greenfield_impl",
            )
            update_task(task.id, conf_impl_correctness=0.85)
            record_calibration_result(task_id=task.id, passed=passed)

        cal = get_calibration(
            project_id=project.id,
            task_class="greenfield_impl",
            confidence_bucket="0.8-0.9",
        )
        assert cal is not None
        assert cal.total_attempts == 10
        assert cal.total_passes == 7
        assert cal.total_failures == 3
        assert cal.empirical_pass_rate == pytest.approx(0.7)

    def test_sets_expected_pass_rate_from_confidence(self, project, feature):
        """expected_pass_rate should be set from the midpoint of the confidence bucket."""
        from bob3.db import record_calibration_result

        task = _make_task(project, feature, confidence=0.85)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.expected_pass_rate == pytest.approx(0.85)

    def test_project_id_set_correctly(self, project, feature):
        from bob3.db import record_calibration_result

        task = _make_task(project, feature)
        result = record_calibration_result(task_id=task.id, passed=True)
        assert result.project_id == project.id
