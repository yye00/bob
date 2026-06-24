"""Tests for F090: End-to-end test - Flaky test detection and handling.

End-to-end integration test that exercises the full flaky test detection
workflow:

Step 1: Create test that passes/fails alternately
Step 2: Run test 10 times
Step 3: Verify is_flaky flag is set
Step 4: Verify flaky_pass_rate calculated (~0.5)
Step 5: Verify flaky test appears in flaky_tests_pending view
"""

import json

import pytest

from bob.db import (
    connect,
    create_feature,
    create_project,
    create_task,
    detect_flaky_test,
    get_task,
    init_database,
    record_test_run,
    update_task,
)
from bob.models import FlakyTestRun


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Create a temporary database and initialize schema."""
    db_path = tmp_path / "bob.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    init_database()
    return db_path


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    return create_project(
        name="Flaky Test E2E",
        workspace_path="/tmp/flaky-test-e2e",
    )


@pytest.fixture
def feature(project):
    """Create a test feature."""
    return create_feature(
        project_id=project.id,
        name="Feature with Flaky Test",
        description="Feature used to test flaky test detection",
        acceptance_criteria=json.dumps(["Test passes reliably"]),
        status="executing",
    )


@pytest.fixture
def validation_task(project, feature):
    """Create a validation task that will become flaky."""
    return create_task(
        project_id=project.id,
        feature_id=feature.id,
        type="validation",
        title="test_widget_renders_correctly",
        status="pending",
    )


# ============================================================
# Step 1: Create test that passes/fails alternately
# ============================================================


class TestStep1AlternatingPassFail:
    """Step 1: Create test that passes/fails alternately."""

    def test_record_alternating_results(self, validation_task):
        """Record 10 runs with alternating pass/fail pattern."""
        runs = []
        for i in range(1, 11):
            passed = (i % 2 == 1)  # Odd runs pass, even runs fail
            run = record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=passed,
                output=f"Run {i}: {'PASS' if passed else 'FAIL'}",
                duration_ms=100 + i * 10,
            )
            runs.append(run)

        assert len(runs) == 10
        # Verify alternating pattern: P, F, P, F, P, F, P, F, P, F
        for i, run in enumerate(runs):
            expected_passed = ((i + 1) % 2 == 1)
            assert run.passed is expected_passed, (
                f"Run {i + 1} expected passed={expected_passed}, got {run.passed}"
            )

    def test_each_run_recorded_as_flaky_test_run(self, validation_task):
        """Each recorded run should be a FlakyTestRun instance."""
        for i in range(1, 11):
            run = record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )
            assert isinstance(run, FlakyTestRun)
            assert run.task_id == validation_task.id
            assert run.run_number == i

    def test_runs_stored_in_database(self, validation_task):
        """All 10 runs should be stored in the flaky_test_runs table."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM flaky_test_runs WHERE task_id = ?",
                (validation_task.id,),
            )
            count = cursor.fetchone()[0]

        assert count == 10


# ============================================================
# Step 2: Run test 10 times
# ============================================================


class TestStep2RunTest10Times:
    """Step 2: Run test 10 times and verify all runs recorded."""

    def test_10_runs_recorded(self, validation_task):
        """Exactly 10 runs should be recorded."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        result = detect_flaky_test(task_id=validation_task.id)
        assert result is not None
        assert result["total_runs"] == 10

    def test_5_passes_and_5_failures(self, validation_task):
        """Should have exactly 5 passes and 5 failures."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passes, "
                "SUM(CASE WHEN NOT passed THEN 1 ELSE 0 END) as failures "
                "FROM flaky_test_runs WHERE task_id = ?",
                (validation_task.id,),
            )
            row = cursor.fetchone()

        assert row[0] == 5  # passes
        assert row[1] == 5  # failures


# ============================================================
# Step 3: Verify is_flaky flag is set
# ============================================================


class TestStep3VerifyFlakyFlag:
    """Step 3: Verify is_flaky flag is set after detection."""

    def test_detect_sets_flaky_flag(self, validation_task):
        """detect_flaky_test() should set is_flaky=True for alternating results."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        result = detect_flaky_test(task_id=validation_task.id)
        assert result["is_flaky"] is True

    def test_task_is_flaky_in_database(self, validation_task):
        """Task.is_flaky should be True after detection."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        detect_flaky_test(task_id=validation_task.id)

        task = get_task(validation_task.id)
        assert task.is_flaky is True

    def test_initially_not_flaky(self, validation_task):
        """Task should start as not flaky."""
        task = get_task(validation_task.id)
        assert task.is_flaky is False


# ============================================================
# Step 4: Verify flaky_pass_rate calculated (~0.5)
# ============================================================


class TestStep4VerifyFlakyPassRate:
    """Step 4: Verify flaky_pass_rate calculated (~0.5)."""

    def test_pass_rate_is_0_5(self, validation_task):
        """Pass rate should be approximately 0.5 for alternating results."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        result = detect_flaky_test(task_id=validation_task.id)
        assert result["pass_rate"] == pytest.approx(0.5, abs=0.01)

    def test_pass_rate_persisted_on_task(self, validation_task):
        """flaky_pass_rate should be stored on the task record."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        detect_flaky_test(task_id=validation_task.id)

        task = get_task(validation_task.id)
        assert task.flaky_pass_rate == pytest.approx(0.5, abs=0.01)

    def test_pass_rate_within_flaky_range(self, validation_task):
        """Pass rate of 0.5 falls within the flaky range (0.2-0.8)."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        result = detect_flaky_test(task_id=validation_task.id)
        assert 0.2 <= result["pass_rate"] <= 0.8


# ============================================================
# Step 5: Verify flaky test appears in flaky_tests_pending view
# ============================================================


class TestStep5FlakyTestsPendingView:
    """Step 5: Verify flaky test appears in flaky_tests_pending view."""

    def test_flaky_task_in_view(self, validation_task):
        """Flaky task should appear in the flaky_tests_pending view."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        detect_flaky_test(task_id=validation_task.id)

        with connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM flaky_tests_pending WHERE id = ?",
                (validation_task.id,),
            )
            row = cursor.fetchone()

        assert row is not None, "Flaky task not found in flaky_tests_pending view"

    def test_view_shows_correct_pass_count(self, validation_task):
        """View should show correct pass_count (5 out of 10)."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        detect_flaky_test(task_id=validation_task.id)

        with connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            cursor = conn.execute(
                "SELECT pass_count, total_runs FROM flaky_tests_pending WHERE id = ?",
                (validation_task.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row["pass_count"] == 5
        assert row["total_runs"] == 10

    def test_view_shows_feature_name(self, validation_task, feature):
        """View should include the feature name."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        detect_flaky_test(task_id=validation_task.id)

        with connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            cursor = conn.execute(
                "SELECT feature_name FROM flaky_tests_pending WHERE id = ?",
                (validation_task.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row["feature_name"] == "Feature with Flaky Test"

    def test_completed_task_not_in_view(self, validation_task):
        """A completed flaky task should NOT appear in flaky_tests_pending."""
        for i in range(1, 11):
            record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        detect_flaky_test(task_id=validation_task.id)

        # Mark task as completed
        update_task(validation_task.id, status="completed")

        with connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM flaky_tests_pending WHERE id = ?",
                (validation_task.id,),
            )
            row = cursor.fetchone()

        assert row is None, "Completed flaky task should not appear in flaky_tests_pending"

    def test_non_flaky_task_not_in_view(self, project, feature):
        """A non-flaky task should NOT appear in flaky_tests_pending."""
        stable_task = create_task(
            project_id=project.id,
            feature_id=feature.id,
            type="validation",
            title="test_stable_function",
            status="pending",
        )

        # All passes = not flaky
        for i in range(1, 11):
            record_test_run(
                task_id=stable_task.id,
                run_number=i,
                passed=True,
            )

        detect_flaky_test(task_id=stable_task.id)

        with connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM flaky_tests_pending WHERE id = ?",
                (stable_task.id,),
            )
            row = cursor.fetchone()

        assert row is None, "Non-flaky task should not appear in flaky_tests_pending"


# ============================================================
# Full E2E integration: All 5 steps in one test
# ============================================================


class TestFullE2EFlakyTestDetection:
    """Full end-to-end: all 5 acceptance criteria in one comprehensive test."""

    def test_complete_flaky_test_detection_workflow(
        self, tmp_db, project, feature, validation_task
    ):
        """Complete E2E: alternating results -> detect -> flag set -> rate ~0.5 -> in view."""

        # ---- Step 1: Create test that passes/fails alternately ----
        for i in range(1, 11):
            passed = (i % 2 == 1)  # P, F, P, F, P, F, P, F, P, F
            run = record_test_run(
                task_id=validation_task.id,
                run_number=i,
                passed=passed,
                output=f"Run {i}: {'PASS' if passed else 'FAIL'}",
                duration_ms=150,
            )
            assert isinstance(run, FlakyTestRun)
            assert run.passed is passed

        # ---- Step 2: Run test 10 times ----
        with connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM flaky_test_runs WHERE task_id = ?",
                (validation_task.id,),
            )
            total_recorded = cursor.fetchone()[0]
        assert total_recorded == 10

        # ---- Step 3: Verify is_flaky flag is set ----
        result = detect_flaky_test(task_id=validation_task.id)
        assert result is not None
        assert result["is_flaky"] is True

        task_after = get_task(validation_task.id)
        assert task_after.is_flaky is True

        # ---- Step 4: Verify flaky_pass_rate calculated (~0.5) ----
        assert result["pass_rate"] == pytest.approx(0.5, abs=0.01)
        assert result["total_runs"] == 10

        assert task_after.flaky_pass_rate == pytest.approx(0.5, abs=0.01)

        # ---- Step 5: Verify flaky test appears in flaky_tests_pending view ----
        with connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            cursor = conn.execute(
                "SELECT * FROM flaky_tests_pending WHERE id = ?",
                (validation_task.id,),
            )
            view_row = cursor.fetchone()

        assert view_row is not None, (
            "Flaky task not found in flaky_tests_pending view"
        )
        assert view_row["feature_name"] == "Feature with Flaky Test"
        assert view_row["pass_count"] == 5
        assert view_row["total_runs"] == 10
        assert view_row["is_flaky"] == 1

    def test_e2e_multiple_flaky_and_stable_tasks(
        self, tmp_db, project, feature
    ):
        """E2E with multiple tasks: only flaky ones appear in view."""
        # Create a flaky validation task
        flaky_task = create_task(
            project_id=project.id,
            feature_id=feature.id,
            type="validation",
            title="test_flaky_network_call",
            status="pending",
        )

        # Create a stable validation task
        stable_task = create_task(
            project_id=project.id,
            feature_id=feature.id,
            type="validation",
            title="test_pure_math_function",
            status="pending",
        )

        # Flaky task: alternating pass/fail
        for i in range(1, 11):
            record_test_run(
                task_id=flaky_task.id,
                run_number=i,
                passed=(i % 2 == 1),
            )

        # Stable task: all passing
        for i in range(1, 11):
            record_test_run(
                task_id=stable_task.id,
                run_number=i,
                passed=True,
            )

        detect_flaky_test(task_id=flaky_task.id)
        detect_flaky_test(task_id=stable_task.id)

        # Verify only flaky task appears in view
        with connect() as conn:
            cursor = conn.execute("SELECT id FROM flaky_tests_pending")
            rows = cursor.fetchall()

        task_ids_in_view = [row[0] for row in rows]
        assert flaky_task.id in task_ids_in_view
        assert stable_task.id not in task_ids_in_view

    def test_e2e_flaky_test_with_varying_pattern(
        self, tmp_db, project, feature
    ):
        """E2E: a task with 3 passes out of 10 (30% rate) is also flaky."""
        task = create_task(
            project_id=project.id,
            feature_id=feature.id,
            type="validation",
            title="test_intermittent_timeout",
            status="pending",
        )

        # 3 passes, 7 failures (pass rate = 0.3)
        for i in range(1, 11):
            record_test_run(
                task_id=task.id,
                run_number=i,
                passed=(i <= 3),
            )

        result = detect_flaky_test(task_id=task.id)
        assert result["is_flaky"] is True
        assert result["pass_rate"] == pytest.approx(0.3)

        task_after = get_task(task.id)
        assert task_after.is_flaky is True
        assert task_after.flaky_pass_rate == pytest.approx(0.3)

        with connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            cursor = conn.execute(
                "SELECT pass_count, total_runs FROM flaky_tests_pending WHERE id = ?",
                (task.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row["pass_count"] == 3
        assert row["total_runs"] == 10
