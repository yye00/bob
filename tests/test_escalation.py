"""Tests for EscalationController.

Tests the model escalation and failure handling system adapted from
autonomous-coding/escalation.py.
"""

import pytest
from datetime import datetime

from bob.database.manager import DatabaseManager
from bob.models.base import (
    EscalationAction,
    FailureType,
    ModelTier,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
)
from bob.orchestrator.escalation import (
    EscalationController,
    MAX_ATTEMPTS_PER_MODEL,
    MAX_DIAGNOSIS_ATTEMPTS,
    MODEL_NAMES,
)


# Model name constants for assertions
SONNET_MODEL = MODEL_NAMES[ModelTier.SONNET]
OPUS_MODEL = MODEL_NAMES[ModelTier.OPUS]


@pytest.fixture
def db_manager(tmp_path):
    """Create a temporary database manager for testing."""
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path)


@pytest.fixture
def project(db_manager):
    """Create a test project."""
    proj = Project(
        id="proj-test",
        name="test-project",
        description="Test project for escalation",
        workspace_dir="/tmp/test",
        spec_source="file://test.yaml",
    )
    project_id = db_manager.create_project(proj)
    return db_manager.get_project(project_id)


@pytest.fixture
def task(db_manager, project):
    """Create a test task."""
    task_obj = Task(
        id="task-test",
        project_id=project.id,
        spec_id="F001",
        title="Test task",
        description="Test task for escalation",
        priority="high",
    )
    task_id = db_manager.create_task(task_obj)
    return db_manager.get_task(task_id)


@pytest.fixture
def controller(db_manager, project):
    """Create an escalation controller."""
    return EscalationController(db_manager, project.id)


def create_test_task(db_manager, project_id, spec_id, title, description="Test task"):
    """Helper function to create a test task."""
    import uuid
    task_obj = Task(
        id=f"task-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        spec_id=spec_id,
        title=title,
        description=description,
    )
    return db_manager.create_task(task_obj)


class TestEscalationControllerInit:
    """Test EscalationController initialization."""

    def test_init_with_db_manager(self, db_manager, project):
        """Test controller initializes with database manager."""
        controller = EscalationController(db_manager, project.id)
        assert controller.db == db_manager
        assert controller.project_id == project.id

    def test_init_with_invalid_project(self, db_manager):
        """Test controller with non-existent project."""
        # Should not fail at initialization - only when using methods
        controller = EscalationController(db_manager, "invalid-project")
        assert controller.project_id == "invalid-project"


class TestRecordAttempt:
    """Test recording task attempts."""

    def test_record_success(self, controller, task):
        """Test recording a successful attempt resets state."""
        # Set up initial failure state
        controller.db.update_task(
            task.id,
            attempts=2,
            failure_type=FailureType.UNKNOWN,
        )

        # Record success
        controller.record_attempt(task.id, success=True)

        # Verify state reset
        updated_task = controller.db.get_task(task.id)
        assert updated_task.attempts == 0
        assert updated_task.failure_type is None
        assert updated_task.research_findings.get("error_history", []) == []

    def test_record_failure_increments_attempts(self, controller, task):
        """Test recording a failure increments attempts."""
        controller.record_attempt(
            task.id,
            success=False,
            error_msg="Test error",
            deps_met=True,
        )

        updated_task = controller.db.get_task(task.id)
        assert updated_task.attempts == 1

        error_history = updated_task.research_findings.get("error_history", [])
        assert len(error_history) == 1
        assert error_history[0]["error_msg"] == "Test error"

    def test_record_failure_with_deps_not_met(self, controller, task):
        """Test failure with unmet deps doesn't increment attempts."""
        controller.record_attempt(
            task.id,
            success=False,
            error_msg="Deps not met",
            deps_met=False,
        )

        updated_task = controller.db.get_task(task.id)
        # Attempts shouldn't increment
        assert updated_task.attempts == 0
        # But failure type should be set
        assert updated_task.failure_type == FailureType.DEPS_NOT_MET

    def test_record_multiple_failures(self, controller, task):
        """Test recording multiple failures builds error history."""
        for i in range(3):
            controller.record_attempt(
                task.id,
                success=False,
                error_msg=f"Error {i}",
                error_type="test_error",
                deps_met=True,
            )

        updated_task = controller.db.get_task(task.id)
        assert updated_task.attempts == 3

        error_history = updated_task.research_findings.get("error_history", [])
        assert len(error_history) == 3
        assert error_history[0]["error_msg"] == "Error 0"
        assert error_history[2]["error_msg"] == "Error 2"

    def test_record_attempt_with_invalid_task(self, controller):
        """Test recording attempt for non-existent task raises error."""
        with pytest.raises(ValueError, match="Task .* not found"):
            controller.record_attempt("invalid-task-id", success=True)


class TestGetNextAction:
    """Test determining next escalation action."""

    def test_get_next_action_continue(self, controller, task):
        """Test continue action when under attempt threshold."""
        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.CONTINUE
        assert context["task_id"] == task.id
        assert context["spec_id"] == task.spec_id

    def test_get_next_action_escalate_model(self, controller, task):
        """Test escalate model action after MAX_ATTEMPTS_PER_MODEL."""
        # Record MAX_ATTEMPTS_PER_MODEL failures
        controller.db.update_task(task.id, attempts=MAX_ATTEMPTS_PER_MODEL)

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.ESCALATE_MODEL
        assert context["from_model"] == SONNET_MODEL
        assert context["to_model"] == OPUS_MODEL
        assert context["attempts"] == MAX_ATTEMPTS_PER_MODEL

    def test_get_next_action_diagnose(self, controller, task):
        """Test diagnose action when Opus fails."""
        # Set task to Opus tier with MAX_ATTEMPTS_PER_MODEL failures
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            current_model=OPUS_MODEL,
            attempts=MAX_ATTEMPTS_PER_MODEL,
        )

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.DIAGNOSE
        assert context["total_attempts"] == MAX_ATTEMPTS_PER_MODEL

    def test_get_next_action_skip_deps_not_met(self, controller, task):
        """Test skip action when dependencies not met."""
        action, context = controller.get_next_action(task.id, deps_met=False)

        assert action == EscalationAction.SKIP
        assert context["reason"] == "dependencies_not_met"

    def test_get_next_action_skip_decomposed(self, controller, task):
        """Test skip action when task already decomposed."""
        # Mark task as decomposed
        research_findings = {
            "decomposed": True,
            "sub_tasks": ["F001-1", "F001-2"],
        }
        controller.db.update_task(task.id, research_findings=research_findings)

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.SKIP
        assert context["reason"] == "decomposed"
        assert context["sub_tasks"] == ["F001-1", "F001-2"]

    def test_get_next_action_with_invalid_task(self, controller):
        """Test get_next_action with non-existent task raises error."""
        with pytest.raises(ValueError, match="Task .* not found"):
            controller.get_next_action("invalid-task-id")


class TestPostDiagnosisActions:
    """Test actions after diagnosis has been performed."""

    def test_action_decompose_for_too_big(self, controller, task):
        """Test DECOMPOSE action for TOO_BIG failure."""
        # Set up diagnosed state
        research_findings = {"diagnosis_done": True}
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            failure_type=FailureType.TOO_BIG,
            research_findings=research_findings,
        )

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.DECOMPOSE
        assert context["reason"] == "Task is too complex for atomic implementation"

    def test_action_research_for_missing_info(self, controller, task):
        """Test RESEARCH action for MISSING_INFO failure."""
        research_findings = {"diagnosis_done": True}
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            failure_type=FailureType.MISSING_INFO,
            research_findings=research_findings,
        )
        controller.db.update_task_spec(
            task.id,
            research_queries=["How to implement X?", "What is Y?"],
        )

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.RESEARCH
        assert context["queries"] == ["How to implement X?", "What is Y?"]
        assert context["reason"] == "Missing information needs to be researched"

    def test_action_request_user_for_wrong_infra(self, controller, task):
        """Test REQUEST_USER action for WRONG_INFRA failure."""
        research_findings = {
            "diagnosis_done": True,
            "error_history": [
                {"error_msg": "Package not found", "timestamp": "2024-01-01T00:00:00"},
                {"error_msg": "Tool missing", "timestamp": "2024-01-01T00:01:00"},
            ],
        }
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            failure_type=FailureType.WRONG_INFRA,
            research_findings=research_findings,
        )

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.REQUEST_USER
        assert context["reason"] == "Missing infrastructure or packages that require user action"
        assert len(context["error_history"]) == 2

    def test_action_restructure_for_bad_assumptions(self, controller, task):
        """Test RESTRUCTURE action for BAD_ASSUMPTIONS failure."""
        research_findings = {"diagnosis_done": True}
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            failure_type=FailureType.BAD_ASSUMPTIONS,
            research_findings=research_findings,
        )

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.RESTRUCTURE
        assert context["reason"] == "Fundamental assumptions are incorrect, need research"

    def test_action_research_for_needs_research(self, controller, task):
        """Test RESEARCH action for NEEDS_RESEARCH failure."""
        research_findings = {"diagnosis_done": True}
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            failure_type=FailureType.NEEDS_RESEARCH,
            research_findings=research_findings,
        )
        controller.db.update_task_spec(
            task.id,
            research_queries=["Research query 1"],
        )

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.RESEARCH
        assert context["reason"] == "Specific research needed to solve the problem"

    def test_action_request_user_for_unknown(self, controller, task):
        """Test REQUEST_USER action for UNKNOWN failure."""
        research_findings = {"diagnosis_done": True}
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            failure_type=FailureType.UNKNOWN,
            research_findings=research_findings,
        )

        action, context = controller.get_next_action(task.id)

        assert action == EscalationAction.REQUEST_USER
        assert context["reason"] == "Unable to determine root cause"


class TestEscalateModel:
    """Test model escalation."""

    def test_escalate_from_sonnet_to_opus(self, controller, task):
        """Test escalating from Sonnet to Opus."""
        # Task starts at TIER1/SONNET
        assert task.escalation_tier in (ModelTier.TIER1, ModelTier.SONNET)

        new_tier = controller.escalate_model(task.id)

        assert new_tier == ModelTier.OPUS

        updated_task = controller.db.get_task(task.id)
        assert updated_task.escalation_tier == ModelTier.OPUS
        assert updated_task.current_model == OPUS_MODEL
        assert updated_task.attempts == 0  # Reset attempts at new tier

    def test_escalate_already_at_opus(self, controller, task):
        """Test escalating when already at highest tier."""
        # Set task to Opus
        controller.db.update_task(
            task.id,
            escalation_tier=ModelTier.OPUS,
            current_model=OPUS_MODEL,
        )

        new_tier = controller.escalate_model(task.id)

        # Should stay at Opus
        assert new_tier == ModelTier.OPUS

        updated_task = controller.db.get_task(task.id)
        assert updated_task.escalation_tier == ModelTier.OPUS

    def test_escalate_with_invalid_task(self, controller):
        """Test escalating non-existent task raises error."""
        with pytest.raises(ValueError, match="Task .* not found"):
            controller.escalate_model("invalid-task-id")


class TestRecordDiagnosis:
    """Test recording diagnosis results."""

    def test_record_diagnosis_basic(self, controller, task):
        """Test recording basic diagnosis."""
        controller.record_diagnosis(
            task.id,
            failure_type=FailureType.TOO_BIG,
        )

        updated_task = controller.db.get_task(task.id)
        assert updated_task.failure_type == FailureType.TOO_BIG
        assert updated_task.research_findings["diagnosis_done"] is True

    def test_record_diagnosis_with_research_queries(self, controller, task):
        """Test recording diagnosis with research queries."""
        queries = ["Query 1", "Query 2"]
        controller.record_diagnosis(
            task.id,
            failure_type=FailureType.NEEDS_RESEARCH,
            research_queries=queries,
        )

        updated_task = controller.db.get_task(task.id)
        assert updated_task.failure_type == FailureType.NEEDS_RESEARCH
        assert updated_task.research_queries == queries
        assert updated_task.research_findings["diagnosis_done"] is True

    def test_record_diagnosis_with_invalid_task(self, controller):
        """Test recording diagnosis for non-existent task raises error."""
        with pytest.raises(ValueError, match="Task .* not found"):
            controller.record_diagnosis("invalid-task-id", FailureType.UNKNOWN)


class TestRecordDecomposition:
    """Test recording task decomposition."""

    def test_record_decomposition(self, controller, task):
        """Test recording task decomposition."""
        sub_tasks = ["F001-1", "F001-2", "F001-3"]
        controller.record_decomposition(task.id, sub_tasks)

        updated_task = controller.db.get_task(task.id)
        assert updated_task.research_findings["decomposed"] is True
        assert updated_task.research_findings["sub_tasks"] == sub_tasks

    def test_record_decomposition_with_invalid_task(self, controller):
        """Test decomposing non-existent task raises error."""
        with pytest.raises(ValueError, match="Task .* not found"):
            controller.record_decomposition("invalid-task-id", ["F001-1"])


class TestResetTask:
    """Test resetting task escalation state."""

    def test_reset_task_clears_state(self, controller, task):
        """Test reset clears all escalation state."""
        # Set up escalation state
        research_findings = {
            "error_history": [{"error": "test"}],
            "diagnosis_done": True,
            "decomposed": True,
            "sub_tasks": ["F001-1"],
        }
        controller.db.update_task(
            task.id,
            attempts=5,
            escalation_tier=ModelTier.OPUS,
            current_model=OPUS_MODEL,
            failure_type=FailureType.TOO_BIG,
            research_findings=research_findings,
        )

        # Reset
        controller.reset_task(task.id)

        # Verify reset
        updated_task = controller.db.get_task(task.id)
        assert updated_task.attempts == 0
        assert updated_task.escalation_tier == ModelTier.SONNET
        assert updated_task.current_model == SONNET_MODEL
        assert updated_task.failure_type is None
        assert "error_history" not in updated_task.research_findings
        assert "diagnosis_done" not in updated_task.research_findings
        assert "decomposed" not in updated_task.research_findings
        assert "sub_tasks" not in updated_task.research_findings

    def test_reset_task_with_invalid_task(self, controller):
        """Test resetting non-existent task raises error."""
        with pytest.raises(ValueError, match="Task .* not found"):
            controller.reset_task("invalid-task-id")


class TestResetAll:
    """Test resetting all tasks in a project."""

    def test_reset_all_clears_all_tasks(self, db_manager, project, controller):
        """Test reset_all clears escalation state for all tasks."""
        # Create multiple tasks with escalation state
        task_ids = []
        for i in range(3):
            task_id = create_test_task(
                db_manager,
                project.id,
                f"F{i:03d}",
                f"Task {i}",
                f"Test task {i}",
            )
            task_ids.append(task_id)

            # Set escalation state
            db_manager.update_task(
                task_id,
                attempts=3,
                escalation_tier=ModelTier.OPUS,
                failure_type=FailureType.TOO_BIG,
            )

        # Reset all
        controller.reset_all()

        # Verify all reset
        for task_id in task_ids:
            task = db_manager.get_task(task_id)
            assert task.attempts == 0
            assert task.escalation_tier == ModelTier.SONNET
            assert task.failure_type is None


class TestGetModelForTask:
    """Test getting current model for a task."""

    def test_get_model_for_task(self, controller, task):
        """Test getting current model."""
        model = controller.get_model_for_task(task.id)
        assert model == SONNET_MODEL

    def test_get_model_for_escalated_task(self, controller, task):
        """Test getting model for escalated task."""
        controller.db.update_task(
            task.id,
            current_model=OPUS_MODEL,
        )

        model = controller.get_model_for_task(task.id)
        assert model == OPUS_MODEL

    def test_get_model_for_invalid_task(self, controller):
        """Test getting model for non-existent task raises error."""
        with pytest.raises(ValueError, match="Task .* not found"):
            controller.get_model_for_task("invalid-task-id")


class TestGetEscalationSummary:
    """Test getting escalation summary."""

    def test_get_escalation_summary_empty(self, controller):
        """Test summary with no tasks."""
        summary = controller.get_escalation_summary()

        assert summary["tasks_at_sonnet"] == 0
        assert summary["tasks_at_opus"] == 0
        assert summary["tasks_diagnosed"] == 0
        assert summary["tasks_decomposed"] == 0
        assert summary["tasks_stuck"] == 0
        assert summary["total_tracked"] == 0

    def test_get_escalation_summary_with_tasks(self, db_manager, project, controller):
        """Test summary with various task states."""
        # Create tasks in different states
        # Task 1: At Sonnet
        task1_id = create_test_task(
            db_manager,
            project.id,
            "F001",
            "Task 1",
            "At Sonnet",
        )

        # Task 2: At Opus
        task2_id = create_test_task(
            db_manager,
            project.id,
            "F002",
            "Task 2",
            "At Opus",
        )
        db_manager.update_task(
            task2_id,
            escalation_tier=ModelTier.OPUS,
        )

        # Task 3: Diagnosed
        task3_id = create_test_task(
            db_manager,
            project.id,
            "F003",
            "Task 3",
            "Diagnosed",
        )
        db_manager.update_task(
            task3_id,
            research_findings={"diagnosis_done": True},
        )

        # Task 4: Decomposed
        task4_id = create_test_task(
            db_manager,
            project.id,
            "F004",
            "Task 4",
            "Decomposed",
        )
        db_manager.update_task(
            task4_id,
            research_findings={"decomposed": True},
        )

        # Task 5: Stuck (Opus + max attempts + diagnosed)
        task5_id = create_test_task(
            db_manager,
            project.id,
            "F005",
            "Task 5",
            "Stuck",
        )
        db_manager.update_task(
            task5_id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            research_findings={"diagnosis_done": True},
        )

        summary = controller.get_escalation_summary()

        assert summary["tasks_at_sonnet"] == 2  # Task 1 and 3
        assert summary["tasks_at_opus"] == 2  # Task 2 and 5
        assert summary["tasks_diagnosed"] == 2  # Task 3 and 5
        assert summary["tasks_decomposed"] == 1  # Task 4
        assert summary["tasks_stuck"] == 1  # Task 5
        assert summary["total_tracked"] == 5


class TestGetStuckTasks:
    """Test getting list of stuck tasks."""

    def test_get_stuck_tasks_empty(self, controller):
        """Test getting stuck tasks when none exist."""
        stuck = controller.get_stuck_tasks()
        assert len(stuck) == 0

    def test_get_stuck_tasks_with_stuck_task(self, db_manager, project, controller):
        """Test getting stuck tasks."""
        # Create a stuck task
        task_id = create_test_task(
            db_manager,
            project.id,
            "F001",
            "Stuck task",
            "This task is stuck",
        )

        error_history = [
            {"error_msg": "Error 1", "timestamp": "2024-01-01T00:00:00"},
            {"error_msg": "Error 2", "timestamp": "2024-01-01T00:01:00"},
            {"error_msg": "Error 3", "timestamp": "2024-01-01T00:02:00"},
        ]

        db_manager.update_task(
            task_id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            failure_type=FailureType.TOO_BIG,
            research_findings={
                "diagnosis_done": True,
                "error_history": error_history,
            },
        )
        db_manager.update_task_spec(
            task_id,
            research_queries=["How to fix this?"],
        )

        stuck = controller.get_stuck_tasks()

        assert len(stuck) == 1
        assert stuck[0]["task_id"] == task_id
        assert stuck[0]["spec_id"] == "F001"
        assert stuck[0]["failure_type"] == "too_big"
        assert stuck[0]["total_attempts"] == MAX_ATTEMPTS_PER_MODEL
        assert stuck[0]["research_queries"] == ["How to fix this?"]
        assert len(stuck[0]["last_errors"]) == 3

    def test_get_stuck_tasks_ignores_non_stuck(self, db_manager, project, controller):
        """Test that non-stuck tasks are not included."""
        # Create task at Opus but not enough attempts
        task1_id = create_test_task(
            db_manager,
            project.id,
            "F001",
            "Not stuck 1",
            "Not enough attempts",
        )
        db_manager.update_task(
            task1_id,
            escalation_tier=ModelTier.OPUS,
            attempts=1,  # Less than MAX
        )

        # Create task at Opus with enough attempts but not diagnosed
        task2_id = create_test_task(
            db_manager,
            project.id,
            "F002",
            "Not stuck 2",
            "Not diagnosed",
        )
        db_manager.update_task(
            task2_id,
            escalation_tier=ModelTier.OPUS,
            attempts=MAX_ATTEMPTS_PER_MODEL,
            research_findings={"diagnosis_done": False},
        )

        stuck = controller.get_stuck_tasks()
        assert len(stuck) == 0
