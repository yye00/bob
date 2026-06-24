"""Tests for F028: Flaky test detection and tracking.

Tests record_test_run() and detect_flaky_test() functions that track
test execution history and identify flaky tests based on pass rate.
"""

import pathlib
import tempfile

import pytest

from bob.db import (
    create_feature,
    create_project,
    create_task,
    detect_flaky_test,
    init_database,
    record_test_run,
)
from bob.models import FlakyTestRun


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for testing."""
    path = tmp_path / "test_f028.db"
    import os
    os.environ["BOB_DATABASE_PATH"] = str(path)
    init_database(db_path=path)
    yield path
    os.environ.pop("BOB_DATABASE_PATH", None)


@pytest.fixture
def project_and_task(db_path):
    """Create a project, feature, and task for testing."""
    project = create_project(name="test-project", workspace_path="/tmp/test")
    feature = create_feature(project_id=project.id, name="test-feature")
    task = create_task(
        feature_id=feature.id,
        project_id=project.id,
        type="validation",
        title="test-task",
    )
    return project, feature, task


class TestRecordTestRun:
    """Tests for the record_test_run() function."""

    def test_record_passing_run(self, project_and_task):
        """Step 1: record_test_run() inserts a row into flaky_test_runs."""
        _, _, task = project_and_task
        run = record_test_run(task_id=task.id, run_number=1, passed=True)

        assert isinstance(run, FlakyTestRun)
        assert run.task_id == task.id
        assert run.run_number == 1
        assert run.passed is True
        assert run.id is not None

    def test_record_failing_run(self, project_and_task):
        """record_test_run() records a failing run."""
        _, _, task = project_and_task
        run = record_test_run(task_id=task.id, run_number=1, passed=False)

        assert run.passed is False

    def test_record_with_output_and_duration(self, project_and_task):
        """record_test_run() stores optional output and duration."""
        _, _, task = project_and_task
        run = record_test_run(
            task_id=task.id,
            run_number=1,
            passed=True,
            output="All tests passed",
            duration_ms=1234,
        )

        assert run.output == "All tests passed"
        assert run.duration_ms == 1234

    def test_record_multiple_runs(self, project_and_task):
        """record_test_run() records multiple runs for the same task."""
        _, _, task = project_and_task
        run1 = record_test_run(task_id=task.id, run_number=1, passed=True)
        run2 = record_test_run(task_id=task.id, run_number=2, passed=False)
        run3 = record_test_run(task_id=task.id, run_number=3, passed=True)

        assert run1.run_number == 1
        assert run2.run_number == 2
        assert run3.run_number == 3
        assert run1.id != run2.id != run3.id

    def test_record_run_nonexistent_task(self, db_path):
        """record_test_run() raises ValueError for non-existent task."""
        with pytest.raises(ValueError, match="not found"):
            record_test_run(task_id="nonexistent", run_number=1, passed=True)


class TestDetectFlakyTest:
    """Tests for the detect_flaky_test() function."""

    def test_alternating_pass_fail_is_flaky(self, project_and_task):
        """Step 5/6: Alternating pass/fail results trigger flaky detection."""
        _, _, task = project_and_task

        # Record alternating results: P, F, P, F, P, F, P, F, P, F
        for i in range(1, 11):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i % 2 == 1)
            )

        result = detect_flaky_test(task_id=task.id)

        assert result is not None
        assert result["is_flaky"] is True
        assert result["pass_rate"] == pytest.approx(0.5, abs=0.01)

    def test_all_passing_is_not_flaky(self, project_and_task):
        """All passing runs should NOT be flaky."""
        _, _, task = project_and_task

        for i in range(1, 11):
            record_test_run(task_id=task.id, run_number=i, passed=True)

        result = detect_flaky_test(task_id=task.id)

        assert result["is_flaky"] is False
        assert result["pass_rate"] == pytest.approx(1.0)

    def test_all_failing_is_not_flaky(self, project_and_task):
        """All failing runs should NOT be flaky (it's just broken)."""
        _, _, task = project_and_task

        for i in range(1, 11):
            record_test_run(task_id=task.id, run_number=i, passed=False)

        result = detect_flaky_test(task_id=task.id)

        assert result["is_flaky"] is False
        assert result["pass_rate"] == pytest.approx(0.0)

    def test_pass_rate_at_lower_boundary(self, project_and_task):
        """Pass rate of exactly 0.2 should be considered flaky."""
        _, _, task = project_and_task

        # 2 passes out of 10 = 0.2 pass rate
        for i in range(1, 11):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i <= 2)
            )

        result = detect_flaky_test(task_id=task.id)

        assert result["is_flaky"] is True
        assert result["pass_rate"] == pytest.approx(0.2)

    def test_pass_rate_at_upper_boundary(self, project_and_task):
        """Pass rate of exactly 0.8 should be considered flaky."""
        _, _, task = project_and_task

        # 8 passes out of 10 = 0.8 pass rate
        for i in range(1, 11):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i <= 8)
            )

        result = detect_flaky_test(task_id=task.id)

        assert result["is_flaky"] is True
        assert result["pass_rate"] == pytest.approx(0.8)

    def test_pass_rate_below_lower_boundary(self, project_and_task):
        """Pass rate below 0.2 should NOT be flaky (just failing)."""
        _, _, task = project_and_task

        # 1 pass out of 10 = 0.1 pass rate
        for i in range(1, 11):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i == 1)
            )

        result = detect_flaky_test(task_id=task.id)

        assert result["is_flaky"] is False
        assert result["pass_rate"] == pytest.approx(0.1)

    def test_pass_rate_above_upper_boundary(self, project_and_task):
        """Pass rate above 0.8 should NOT be flaky (mostly passing)."""
        _, _, task = project_and_task

        # 9 passes out of 10 = 0.9 pass rate
        for i in range(1, 11):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i <= 9)
            )

        result = detect_flaky_test(task_id=task.id)

        assert result["is_flaky"] is False
        assert result["pass_rate"] == pytest.approx(0.9)

    def test_detect_uses_last_n_runs(self, project_and_task):
        """Step 3: detect_flaky_test() only considers the last N runs."""
        _, _, task = project_and_task

        # First 10 runs: all passing
        for i in range(1, 11):
            record_test_run(task_id=task.id, run_number=i, passed=True)

        # Next 10 runs: alternating (these are the last 10)
        for i in range(11, 21):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i % 2 == 1)
            )

        result = detect_flaky_test(task_id=task.id, last_n=10)

        assert result["is_flaky"] is True
        assert result["pass_rate"] == pytest.approx(0.5, abs=0.01)
        assert result["total_runs"] == 10

    def test_detect_updates_task_flaky_flag(self, project_and_task):
        """Step 4: detect_flaky_test() sets is_flaky flag on the task."""
        _, _, task = project_and_task

        for i in range(1, 11):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i % 2 == 1)
            )

        result = detect_flaky_test(task_id=task.id)

        # Verify the task was updated in the database
        from bob.db import get_task
        updated_task = get_task(task.id)
        assert updated_task.is_flaky is True
        assert updated_task.flaky_pass_rate == pytest.approx(0.5, abs=0.01)

    def test_detect_clears_flaky_flag_when_stable(self, project_and_task):
        """detect_flaky_test() clears is_flaky when test becomes stable."""
        _, _, task = project_and_task

        # All passing = stable
        for i in range(1, 11):
            record_test_run(task_id=task.id, run_number=i, passed=True)

        result = detect_flaky_test(task_id=task.id)

        from bob.db import get_task
        updated_task = get_task(task.id)
        assert updated_task.is_flaky is False

    def test_detect_nonexistent_task(self, db_path):
        """detect_flaky_test() returns None for non-existent task."""
        result = detect_flaky_test(task_id="nonexistent")
        assert result is None

    def test_detect_no_runs(self, project_and_task):
        """detect_flaky_test() with no runs returns not flaky."""
        _, _, task = project_and_task
        result = detect_flaky_test(task_id=task.id)

        assert result["is_flaky"] is False
        assert result["pass_rate"] == 0.0
        assert result["total_runs"] == 0

    def test_default_last_n_is_10(self, project_and_task):
        """Default window for flaky detection is 10 runs."""
        _, _, task = project_and_task

        # Record 15 runs: first 5 pass, next 10 alternate
        for i in range(1, 6):
            record_test_run(task_id=task.id, run_number=i, passed=True)
        for i in range(6, 16):
            record_test_run(
                task_id=task.id, run_number=i, passed=(i % 2 == 0)
            )

        result = detect_flaky_test(task_id=task.id)

        # Should only look at last 10 (runs 6-15)
        assert result["total_runs"] == 10
