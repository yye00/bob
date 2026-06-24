"""Tests for F088: End-to-end test - Detect regression and trigger rollback.

End-to-end integration test that exercises the full regression detection
and rollback workflow:

Step 1: Complete feature A with passing tests
Step 2: Implement feature B that breaks A's tests
Step 3: Verify regression detected (regression_events record created)
Step 4: Trigger rollback of feature B
Step 5: Verify feature A's tests pass again
Step 6: Verify rollback_events record created
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.db import (
    connect,
    create_evidence,
    create_feature,
    create_project,
    create_task,
    detect_regression,
    get_feature,
    get_regression_event,
    get_rollback_event,
    init_database,
    list_regression_events,
    list_rollback_events,
    query_evidence,
    rollback_feature,
    update_feature,
)
from bob.models import RegressionEvent, RollbackEvent
from bob.orchestrator.claude_executor import ExecutionResult, SpawnResult
from bob.orchestrator.run_loop import (
    LoopTermination,
    OrchestrationLoop,
    handle_execution_result,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database with schema initialized."""
    db_path = tmp_path / "bob.db"
    init_database(db_path=db_path)
    with patch("bob.db.get_database_path", return_value=db_path):
        yield db_path


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory for the project."""
    ws = tmp_path / "regression-rollback-test"
    ws.mkdir()
    return ws


@pytest.fixture
def project(tmp_db):
    """Create a test project."""
    return create_project(
        name="Regression Rollback E2E",
        workspace_path="/tmp/regression-rollback-e2e",
    )


@pytest.fixture
def feature_a(project):
    """Create feature A with 'completed' status and passing tests."""
    return create_feature(
        project_id=project.id,
        name="Feature A - Stable Base",
        description="A completed, stable feature whose tests all pass",
        acceptance_criteria=json.dumps(["All unit tests pass", "Integration test passes"]),
        status="completed",
        priority=10,
        risk_category="low",
    )


@pytest.fixture
def feature_b(project):
    """Create feature B that will cause regression."""
    return create_feature(
        project_id=project.id,
        name="Feature B - Causes Regression",
        description="A feature that breaks Feature A's tests",
        acceptance_criteria=json.dumps(["Feature B implemented"]),
        status="executing",
        priority=20,
        risk_category="medium",
    )


@pytest.fixture
def task_a_validation(project, feature_a):
    """Create a validation task for feature A."""
    return create_task(
        project_id=project.id,
        feature_id=feature_a.id,
        type="validation",
        title="Run Feature A Tests",
        status="completed",
    )


@pytest.fixture
def task_b_impl(project, feature_b):
    """Create an implementation task for feature B."""
    return create_task(
        project_id=project.id,
        feature_id=feature_b.id,
        type="implementation",
        title="Implement Feature B",
        status="completed",
    )


@pytest.fixture
def evidence_a(project, feature_a):
    """Create evidence that feature A's tests were passing."""
    return create_evidence(
        project_id=project.id,
        feature_id=feature_a.id,
        type="test_output",
        content=json.dumps({
            "tests_passed": 5,
            "tests_failed": 0,
            "test_names": ["test_a_unit_1", "test_a_unit_2", "test_a_unit_3",
                           "test_a_integration_1", "test_a_integration_2"],
        }),
    )


@pytest.fixture
def evidence_b(project, feature_b):
    """Create evidence artifacts for feature B."""
    return create_evidence(
        project_id=project.id,
        feature_id=feature_b.id,
        type="test_output",
        content=json.dumps({
            "tests_passed": 3,
            "tests_failed": 2,
            "test_names": ["test_b_1", "test_b_2", "test_b_3"],
        }),
    )


# ============================================================
# Step 1: Complete feature A with passing tests
# ============================================================


class TestStep1FeatureACompleted:
    """Step 1: Verify feature A exists in a completed state with passing tests."""

    def test_feature_a_is_completed(self, feature_a):
        """Feature A should be in 'completed' status."""
        assert feature_a.status == "completed"

    def test_feature_a_has_validation_task(self, feature_a, task_a_validation):
        """Feature A should have a completed validation task."""
        assert task_a_validation.feature_id == feature_a.id
        assert task_a_validation.type == "validation"
        assert task_a_validation.status == "completed"

    def test_feature_a_has_passing_test_evidence(self, feature_a, evidence_a):
        """Feature A has evidence that all tests passed."""
        content = json.loads(evidence_a.content)
        assert content["tests_failed"] == 0
        assert content["tests_passed"] > 0

    def test_feature_a_retrievable_from_database(self, feature_a):
        """Feature A is persisted in the database and retrievable."""
        retrieved = get_feature(feature_a.id)
        assert retrieved is not None
        assert retrieved.id == feature_a.id
        assert retrieved.status == "completed"
        assert retrieved.name == "Feature A - Stable Base"


# ============================================================
# Step 2: Implement feature B that breaks A's tests
# ============================================================


class TestStep2FeatureBBreaksA:
    """Step 2: Feature B is implemented and breaks A's tests."""

    def test_feature_b_exists_in_executing_state(self, feature_b):
        """Feature B should be in 'executing' status."""
        assert feature_b.status == "executing"

    def test_feature_b_has_implementation_task(self, feature_b, task_b_impl):
        """Feature B should have a completed implementation task."""
        assert task_b_impl.feature_id == feature_b.id
        assert task_b_impl.type == "implementation"
        assert task_b_impl.status == "completed"

    def test_feature_a_tests_fail_after_feature_b(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """Simulates that after feature B, feature A's tests now fail."""
        # Before feature B: all of A's tests pass
        before_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": True,
            "test_a_unit_3": True,
            "test_a_integration_1": True,
            "test_a_integration_2": True,
        }

        # After feature B: some of A's tests fail
        after_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": False,
            "test_a_unit_3": True,
            "test_a_integration_1": False,
            "test_a_integration_2": True,
        }

        # Verify that tests that previously passed now fail
        newly_failing = [
            name for name, passed_before in before_results.items()
            if passed_before and not after_results.get(name, True)
        ]
        assert len(newly_failing) == 2
        assert "test_a_unit_2" in newly_failing
        assert "test_a_integration_1" in newly_failing


# ============================================================
# Step 3: Verify regression detected (regression_events record created)
# ============================================================


class TestStep3RegressionDetected:
    """Step 3: Regression is detected and regression_events record created."""

    def test_regression_detected_when_feature_b_breaks_a(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """detect_regression identifies that feature B broke feature A's tests."""
        before_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": True,
            "test_a_unit_3": True,
            "test_a_integration_1": True,
            "test_a_integration_2": True,
        }
        after_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": False,
            "test_a_unit_3": True,
            "test_a_integration_1": False,
            "test_a_integration_2": True,
        }
        test_to_feature_map = {name: feature_a.id for name in before_results}

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        assert result is not None
        assert isinstance(result, RegressionEvent)

    def test_regression_event_has_correct_fields(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """Regression event correctly identifies cause, affected feature, and tests."""
        before_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": True,
            "test_a_integration_1": True,
        }
        after_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": False,
            "test_a_integration_1": False,
        }
        test_to_feature_map = {name: feature_a.id for name in before_results}

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        assert result.causing_feature_id == feature_b.id
        assert result.affected_feature_id == feature_a.id
        assert result.status == "detected"
        assert result.detected_at is not None

        affected_tests = json.loads(result.affected_tests)
        assert sorted(affected_tests) == ["test_a_integration_1", "test_a_unit_2"]

    def test_regression_event_persisted_in_database(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """Regression event is stored in the regression_events table."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT id, project_id, affected_feature_id, causing_feature_id, "
                "status FROM regression_events WHERE id = ?",
                (result.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == result.id
        assert row[1] == project.id
        assert row[2] == feature_a.id
        assert row[3] == feature_b.id
        assert row[4] == "detected"

    def test_feature_a_status_updated_to_regression(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """After regression detection, feature A's status becomes 'regression'."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        updated_a = get_feature(feature_a.id)
        assert updated_a.status == "regression"

    def test_regression_appears_in_active_list(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """Detected regression appears in active regression list."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        active = list_regression_events(project_id=project.id, active_only=True)
        assert any(e.id == result.id for e in active)


# ============================================================
# Step 4: Trigger rollback of feature B
# ============================================================


class TestStep4TriggerRollback:
    """Step 4: Trigger rollback of feature B."""

    def test_rollback_feature_b_after_regression(
        self, project, feature_a, feature_b, task_a_validation, evidence_b
    ):
        """After detecting regression, rolling back feature B creates a rollback event."""
        # Step 3: Detect regression first
        before_results = {"test_a_1": True, "test_a_2": True}
        after_results = {"test_a_1": False, "test_a_2": True}
        test_to_feature_map = {"test_a_1": feature_a.id, "test_a_2": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )
        assert reg_event is not None

        # Step 4: Rollback feature B
        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before_b",
            commit_after="sha_after_b",
            rollback_commit="sha_rollback_b",
            regression_event_id=reg_event.id,
        )

        assert rollback_event is not None
        assert isinstance(rollback_event, RollbackEvent)
        assert rollback_event.feature_id == feature_b.id
        assert rollback_event.trigger == "regression"
        assert rollback_event.regression_event_id == reg_event.id

    def test_feature_b_status_becomes_rolled_back(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """After rollback, feature B's status should be 'rolled_back'."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event.id,
        )

        updated_b = get_feature(feature_b.id)
        assert updated_b.status == "rolled_back"

    def test_regression_event_status_becomes_rolled_back(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """After rollback, the linked regression event status becomes 'rolled_back'."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event.id,
        )

        updated_reg = get_regression_event(reg_event.id)
        assert updated_reg.status == "rolled_back"
        assert updated_reg.resolved_at is not None

    def test_evidence_preserved_during_rollback(
        self, project, feature_a, feature_b, task_a_validation, evidence_b
    ):
        """Evidence artifacts for feature B are preserved during rollback."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event.id,
        )

        preserved = json.loads(rollback_event.artifacts_preserved)
        assert evidence_b.id in preserved


# ============================================================
# Step 5: Verify feature A's tests pass again
# ============================================================


class TestStep5FeatureATestsPassAgain:
    """Step 5: After rolling back B, feature A's tests should pass again."""

    def test_feature_a_can_be_restored_to_completed(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """After rollback, feature A can be restored to 'completed' status.

        In the real workflow, the orchestrator would re-run A's tests and
        confirm they pass. Here we simulate restoring A's status to show
        the rollback resolved the regression.
        """
        # Detect regression
        before_results = {"test_a_1": True, "test_a_2": True}
        after_results = {"test_a_1": False, "test_a_2": True}
        test_to_feature_map = {"test_a_1": feature_a.id, "test_a_2": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        # Verify feature A is in 'regression' state
        feature_a_after_reg = get_feature(feature_a.id)
        assert feature_a_after_reg.status == "regression"

        # Rollback feature B
        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            rollback_commit="sha_rollback",
            regression_event_id=reg_event.id,
        )

        # After rollback, re-run A's tests — they should pass
        # Simulated: no regression found when re-checking
        recheck_result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True, "test_a_2": True},
            after_results={"test_a_1": True, "test_a_2": True},
        )
        assert recheck_result is None  # No regression: tests pass again

        # Restore feature A to completed
        update_feature(feature_a.id, status="completed")
        restored_a = get_feature(feature_a.id)
        assert restored_a.status == "completed"

    def test_no_new_regression_after_rollback(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """After rollback, running detect_regression finds no new failures."""
        # Detect and rollback
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event.id,
        )

        # Post-rollback check: A's tests should pass
        post_rollback_result = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a_1": True},
            after_results={"test_a_1": True},
        )
        assert post_rollback_result is None


# ============================================================
# Step 6: Verify rollback_events record created
# ============================================================


class TestStep6RollbackEventsRecordCreated:
    """Step 6: Verify rollback_events record is created and complete."""

    def test_rollback_event_persisted_in_database(
        self, project, feature_a, feature_b, task_a_validation, evidence_b
    ):
        """Rollback event is stored in the rollback_events table."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before_b",
            commit_after="sha_after_b",
            rollback_commit="sha_rollback_b",
            regression_event_id=reg_event.id,
        )

        with connect() as conn:
            cursor = conn.execute(
                "SELECT id, project_id, feature_id, trigger, "
                "commit_before, commit_after, rollback_commit, "
                "regression_event_id FROM rollback_events WHERE id = ?",
                (rollback_event.id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == rollback_event.id
        assert row[1] == project.id
        assert row[2] == feature_b.id
        assert row[3] == "regression"
        assert row[4] == "sha_before_b"
        assert row[5] == "sha_after_b"
        assert row[6] == "sha_rollback_b"
        assert row[7] == reg_event.id

    def test_rollback_event_retrievable_by_id(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """Rollback event is retrievable via get_rollback_event."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event.id,
        )

        fetched = get_rollback_event(rollback_event.id)
        assert fetched is not None
        assert fetched.id == rollback_event.id
        assert fetched.feature_id == feature_b.id
        assert fetched.trigger == "regression"
        assert fetched.regression_event_id == reg_event.id

    def test_rollback_event_in_project_list(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """Rollback event appears in list_rollback_events for the project."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event.id,
        )

        events = list_rollback_events(project_id=project.id)
        assert len(events) == 1
        assert events[0].id == rollback_event.id

    def test_regression_no_longer_active_after_rollback(
        self, project, feature_a, feature_b, task_a_validation
    ):
        """After rollback, the regression event should not appear in active list."""
        before_results = {"test_a_1": True}
        after_results = {"test_a_1": False}
        test_to_feature_map = {"test_a_1": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        # Before rollback: regression is active
        active_before = list_regression_events(project_id=project.id, active_only=True)
        assert any(e.id == reg_event.id for e in active_before)

        rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event.id,
        )

        # After rollback: regression is no longer active
        active_after = list_regression_events(project_id=project.id, active_only=True)
        assert not any(e.id == reg_event.id for e in active_after)


# ============================================================
# Full E2E integration: All 6 steps in one test
# ============================================================


class TestFullE2ERegressionRollback:
    """Full end-to-end: all 6 acceptance criteria in one comprehensive test."""

    def test_complete_regression_detection_and_rollback_workflow(
        self, project, feature_a, feature_b, task_a_validation,
        task_b_impl, evidence_a, evidence_b
    ):
        """Complete E2E: Feature A passes -> Feature B breaks A -> detect -> rollback -> A passes again."""

        # ---- Step 1: Feature A is completed with passing tests ----
        assert feature_a.status == "completed"
        a_evidence = query_evidence(feature_id=feature_a.id)
        assert len(a_evidence) >= 1
        a_content = json.loads(a_evidence[0].content)
        assert a_content["tests_failed"] == 0

        # ---- Step 2: Feature B breaks A's tests ----
        before_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": True,
            "test_a_unit_3": True,
            "test_a_integration_1": True,
            "test_a_integration_2": True,
        }
        after_results = {
            "test_a_unit_1": True,
            "test_a_unit_2": False,  # Broken by B
            "test_a_unit_3": True,
            "test_a_integration_1": False,  # Broken by B
            "test_a_integration_2": True,
        }
        test_to_feature_map = {name: feature_a.id for name in before_results}

        # ---- Step 3: Detect regression ----
        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )

        # Verify regression_events record created
        assert reg_event is not None
        assert isinstance(reg_event, RegressionEvent)
        assert reg_event.causing_feature_id == feature_b.id
        assert reg_event.affected_feature_id == feature_a.id
        assert reg_event.status == "detected"

        affected_tests = json.loads(reg_event.affected_tests)
        assert sorted(affected_tests) == ["test_a_integration_1", "test_a_unit_2"]

        # Verify feature A's status updated to 'regression'
        feature_a_regressed = get_feature(feature_a.id)
        assert feature_a_regressed.status == "regression"

        # Verify regression persisted in database
        fetched_reg = get_regression_event(reg_event.id)
        assert fetched_reg is not None
        assert fetched_reg.id == reg_event.id

        # Verify it's in the active regression list
        active = list_regression_events(project_id=project.id, active_only=True)
        assert any(e.id == reg_event.id for e in active)

        # ---- Step 4: Trigger rollback of feature B ----
        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before_feature_b",
            commit_after="sha_after_feature_b",
            rollback_commit="sha_rollback_feature_b",
            regression_event_id=reg_event.id,
        )

        assert rollback_event is not None
        assert isinstance(rollback_event, RollbackEvent)

        # Feature B is now 'rolled_back'
        feature_b_rolled_back = get_feature(feature_b.id)
        assert feature_b_rolled_back.status == "rolled_back"

        # Regression event status updated to 'rolled_back'
        reg_after_rollback = get_regression_event(reg_event.id)
        assert reg_after_rollback.status == "rolled_back"
        assert reg_after_rollback.resolved_at is not None

        # Evidence from feature B preserved
        preserved = json.loads(rollback_event.artifacts_preserved)
        assert evidence_b.id in preserved

        # ---- Step 5: Feature A's tests pass again ----
        # Simulate re-running tests after rollback — no new regressions
        recheck = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=before_results,  # All pass again (same as before)
        )
        assert recheck is None  # No regression

        # Restore feature A to completed status
        update_feature(feature_a.id, status="completed")
        feature_a_restored = get_feature(feature_a.id)
        assert feature_a_restored.status == "completed"

        # ---- Step 6: Verify rollback_events record created ----
        fetched_rollback = get_rollback_event(rollback_event.id)
        assert fetched_rollback is not None
        assert fetched_rollback.id == rollback_event.id
        assert fetched_rollback.project_id == project.id
        assert fetched_rollback.feature_id == feature_b.id
        assert fetched_rollback.trigger == "regression"
        assert fetched_rollback.commit_before == "sha_before_feature_b"
        assert fetched_rollback.commit_after == "sha_after_feature_b"
        assert fetched_rollback.rollback_commit == "sha_rollback_feature_b"
        assert fetched_rollback.regression_event_id == reg_event.id

        # Rollback appears in project's rollback list
        rollbacks = list_rollback_events(project_id=project.id)
        assert len(rollbacks) == 1
        assert rollbacks[0].id == rollback_event.id

        # Regression no longer active
        active_after = list_regression_events(project_id=project.id, active_only=True)
        assert not any(e.id == reg_event.id for e in active_after)

        # All regression events for this project (including resolved)
        all_regressions = list_regression_events(project_id=project.id, active_only=False)
        assert len(all_regressions) >= 1

        # Database consistency check
        with connect() as conn:
            # Regression event table
            cursor = conn.execute(
                "SELECT status FROM regression_events WHERE id = ?",
                (reg_event.id,),
            )
            assert cursor.fetchone()[0] == "rolled_back"

            # Rollback event table
            cursor = conn.execute(
                "SELECT regression_event_id FROM rollback_events WHERE id = ?",
                (rollback_event.id,),
            )
            assert cursor.fetchone()[0] == reg_event.id

            # Feature statuses
            cursor = conn.execute(
                "SELECT status FROM features WHERE id = ?",
                (feature_a.id,),
            )
            assert cursor.fetchone()[0] == "completed"

            cursor = conn.execute(
                "SELECT status FROM features WHERE id = ?",
                (feature_b.id,),
            )
            assert cursor.fetchone()[0] == "rolled_back"

    def test_e2e_with_orchestration_loop_rollback_method(
        self, tmp_db, workspace, project, feature_a, feature_b,
        task_a_validation, evidence_b
    ):
        """Test the OrchestrationLoop.rollback_feature method in the E2E flow."""
        # Step 3: Detect regression
        before_results = {"test_a_1": True, "test_a_2": True}
        after_results = {"test_a_1": False, "test_a_2": True}
        test_to_feature_map = {"test_a_1": feature_a.id, "test_a_2": feature_a.id}

        reg_event = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results=before_results,
            after_results=after_results,
            test_to_feature_map=test_to_feature_map,
        )
        assert reg_event is not None

        # Step 4: Use the orchestration loop's rollback method
        loop = OrchestrationLoop(
            project_id=project.id,
            workspace=str(workspace),
        )

        with patch(
            "bob.orchestrator.run_loop.git_revert_feature",
            return_value="sha_reverted",
        ):
            loop.rollback_feature(
                feature_id=feature_b.id,
                trigger="regression",
                commit_sha="sha_after_b",
                commit_before="sha_before_b",
                regression_event_id=reg_event.id,
            )

        # Verify feature B is rolled back
        updated_b = get_feature(feature_b.id)
        assert updated_b.status == "rolled_back"

        # Verify rollback event created
        rollbacks = list_rollback_events(project_id=project.id)
        assert len(rollbacks) == 1
        assert rollbacks[0].feature_id == feature_b.id
        assert rollbacks[0].trigger == "regression"
        assert rollbacks[0].regression_event_id == reg_event.id

        # Verify regression event updated
        updated_reg = get_regression_event(reg_event.id)
        assert updated_reg.status == "rolled_back"

    def test_e2e_multiple_affected_features(self, project, task_a_validation):
        """Regression affecting multiple features from multiple test sets."""
        feature_a1 = create_feature(
            project_id=project.id,
            name="Feature A1 - Stable",
            status="completed",
        )
        feature_a2 = create_feature(
            project_id=project.id,
            name="Feature A2 - Also Stable",
            status="completed",
        )
        feature_b = create_feature(
            project_id=project.id,
            name="Feature B - Breaks Both",
            status="executing",
        )

        # Feature B breaks tests from A1
        reg_event_1 = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a1_1": True, "test_a1_2": True},
            after_results={"test_a1_1": False, "test_a1_2": True},
            test_to_feature_map={"test_a1_1": feature_a1.id, "test_a1_2": feature_a1.id},
        )
        assert reg_event_1 is not None
        assert reg_event_1.affected_feature_id == feature_a1.id

        # Feature B also breaks tests from A2
        reg_event_2 = detect_regression(
            project_id=project.id,
            causing_feature_id=feature_b.id,
            before_results={"test_a2_1": True},
            after_results={"test_a2_1": False},
            test_to_feature_map={"test_a2_1": feature_a2.id},
        )
        assert reg_event_2 is not None
        assert reg_event_2.affected_feature_id == feature_a2.id

        # Two active regressions
        active = list_regression_events(project_id=project.id, active_only=True)
        active_ids = {e.id for e in active}
        assert reg_event_1.id in active_ids
        assert reg_event_2.id in active_ids

        # Rollback feature B (link to first regression)
        evidence_b = create_evidence(
            project_id=project.id,
            feature_id=feature_b.id,
            type="test_output",
            content=json.dumps({"output": "partial"}),
        )

        rollback_event = rollback_feature(
            project_id=project.id,
            feature_id=feature_b.id,
            trigger="regression",
            commit_before="sha_before",
            commit_after="sha_after",
            regression_event_id=reg_event_1.id,
        )

        # First regression is rolled back, second is still detected
        updated_1 = get_regression_event(reg_event_1.id)
        assert updated_1.status == "rolled_back"

        updated_2 = get_regression_event(reg_event_2.id)
        assert updated_2.status == "detected"

        # Only one active regression remains
        active_after = list_regression_events(project_id=project.id, active_only=True)
        assert len(active_after) == 1
        assert active_after[0].id == reg_event_2.id
