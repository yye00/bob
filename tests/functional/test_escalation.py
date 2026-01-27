"""Functional tests for escalation controller and failure classification."""
import pytest
from pathlib import Path
from bob.database.manager import DatabaseManager
from bob.models.base import (
    Task, TaskStatus, Project, ModelTier, 
    FailureType, EscalationAction
)
from bob.orchestrator.escalation import EscalationController
from bob.orchestrator.failure_classifier import (
    classify_failure, classify_by_patterns, 
    check_repeated_errors, analyze_task_complexity,
    ClassificationResult
)


class TestEscalationControllerFunctional:
    """Test escalation controller with real database operations."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Set up database, project, and escalation controller."""
        db = DatabaseManager(tmp_path / "test.db")
        project = Project(
            id="test-proj-esc",
            name="test-project",
            description="Test project for escalation",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/bob_spec.yaml",
        )
        project_id = db.create_project(project)
        controller = EscalationController(db, project_id)
        return db, project_id, controller

    def test_record_successful_attempt_resets_state(self, setup):
        """Test that successful attempt resets escalation state."""
        db, project_id, controller = setup
        
        # Create task with some attempts
        task = Task(
            id="task-success-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            attempts=2,
        )
        db.create_task(task)
        
        # Record successful attempt
        controller.record_attempt(
            task_id="task-success-001",
            success=True,
        )
        
        # Verify attempts reset
        updated = db.get_task("task-success-001")
        assert updated.attempts == 0

    def test_record_failed_attempt_increments_count(self, setup):
        """Test that failed attempt increments attempts count."""
        db, project_id, controller = setup
        
        task = Task(
            id="task-fail-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            attempts=0,
        )
        db.create_task(task)
        
        # Record failed attempt
        controller.record_attempt(
            task_id="task-fail-001",
            success=False,
            error_msg="Test error",
            deps_met=True,
        )
        
        # Verify attempts incremented
        updated = db.get_task("task-fail-001")
        assert updated.attempts == 1

    def test_escalate_model_changes_tier(self, setup):
        """Test that model escalation changes tier from Sonnet to Opus."""
        db, project_id, controller = setup
        
        task = Task(
            id="task-escalate-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            escalation_tier=ModelTier.SONNET,
        )
        db.create_task(task)
        
        # Escalate model
        new_tier = controller.escalate_model("task-escalate-001")
        
        # Verify tier changed to Opus
        assert new_tier == ModelTier.OPUS
        updated = db.get_task("task-escalate-001")
        assert updated.escalation_tier == ModelTier.OPUS
        assert "opus" in updated.current_model.lower()

    def test_get_next_action_continue_when_under_threshold(self, setup):
        """Test that get_next_action returns CONTINUE when under threshold."""
        db, project_id, controller = setup
        
        task = Task(
            id="task-continue-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            attempts=1,  # Under threshold of 3
            escalation_tier=ModelTier.SONNET,
        )
        db.create_task(task)
        
        action, context = controller.get_next_action("task-continue-001")
        assert action == EscalationAction.CONTINUE

    def test_get_next_action_escalate_at_threshold(self, setup):
        """Test that get_next_action returns ESCALATE_MODEL at threshold."""
        db, project_id, controller = setup
        
        task = Task(
            id="task-threshold-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            attempts=3,  # At threshold
            escalation_tier=ModelTier.SONNET,
        )
        db.create_task(task)
        
        action, context = controller.get_next_action("task-threshold-001")
        assert action == EscalationAction.ESCALATE_MODEL
        assert "opus" in context.get("to_model", "").lower()

    def test_get_next_action_diagnose_after_opus_fails(self, setup):
        """Test that diagnosis is triggered after Opus fails."""
        db, project_id, controller = setup
        
        task = Task(
            id="task-diagnose-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            attempts=3,
            escalation_tier=ModelTier.OPUS,
            research_findings={},  # No diagnosis done yet
        )
        db.create_task(task)
        
        action, context = controller.get_next_action("task-diagnose-001")
        assert action == EscalationAction.DIAGNOSE

    def test_record_diagnosis_stores_failure_type(self, setup):
        """Test that diagnosis result is stored correctly."""
        db, project_id, controller = setup
        
        task = Task(
            id="task-diag-store-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
        )
        db.create_task(task)
        
        # Record diagnosis
        controller.record_diagnosis(
            task_id="task-diag-store-001",
            failure_type=FailureType.TOO_BIG,
            research_queries=["How to decompose complex tasks"],
        )
        
        # Verify diagnosis stored
        updated = db.get_task("task-diag-store-001")
        assert updated.failure_type == FailureType.TOO_BIG
        assert updated.research_findings.get("diagnosis_done") == True

    def test_reset_task_clears_escalation_state(self, setup):
        """Test that reset_task clears all escalation state."""
        db, project_id, controller = setup
        
        task = Task(
            id="task-reset-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            attempts=5,
            escalation_tier=ModelTier.OPUS,
            failure_type=FailureType.TOO_BIG,
            research_findings={
                "diagnosis_done": True,
                "error_history": [{"error": "test"}],
            },
        )
        db.create_task(task)
        
        # Reset task
        controller.reset_task("task-reset-001")
        
        # Verify reset
        updated = db.get_task("task-reset-001")
        assert updated.attempts == 0
        assert updated.escalation_tier == ModelTier.SONNET
        assert updated.failure_type is None


class TestFailureClassifierFunctional:
    """Test failure classification with real error patterns."""

    def test_classify_infrastructure_error(self):
        """Test classification of infrastructure errors."""
        errors = ["ModuleNotFoundError: No module named 'flask'"]
        
        result = classify_by_patterns(errors)
        
        assert result is not None
        assert result.failure_type == FailureType.WRONG_INFRA
        assert result.confidence >= 0.8

    def test_classify_complexity_error(self):
        """Test classification of complexity-related errors."""
        errors = ["TimeoutError: Execution timeout exceeded"]
        
        result = classify_by_patterns(errors)
        
        assert result is not None
        assert result.failure_type == FailureType.TOO_BIG

    def test_classify_missing_info_error(self):
        """Test classification of missing information errors."""
        errors = ["AttributeError: 'Response' has no attribute 'json_data'"]
        
        result = classify_by_patterns(errors)
        
        assert result is not None
        assert result.failure_type == FailureType.MISSING_INFO
        assert len(result.research_queries) > 0

    def test_classify_bad_assumptions_error(self):
        """Test classification of bad assumptions errors."""
        errors = ["AssertionError: Expected 5 but got 3"]
        
        result = classify_by_patterns(errors)
        
        assert result is not None
        assert result.failure_type == FailureType.BAD_ASSUMPTIONS

    def test_check_repeated_errors_detects_patterns(self):
        """Test detection of repeated error patterns."""
        error_history = [
            {"error_msg": "ImportError: cannot import name 'foo'"},
            {"error_msg": "ImportError: cannot import name 'foo'"},
            {"error_msg": "ImportError: cannot import name 'foo'"},
        ]
        
        is_repeated, pattern = check_repeated_errors(error_history)
        
        assert is_repeated == True
        assert pattern is not None

    def test_check_repeated_errors_different_errors(self):
        """Test that different errors are not flagged as repeated."""
        error_history = [
            {"error_msg": "Error type A"},
            {"error_msg": "Error type B"},
            {"error_msg": "Error type C"},
        ]
        
        is_repeated, pattern = check_repeated_errors(error_history)
        
        assert is_repeated == False

    def test_analyze_task_complexity_simple_task(self):
        """Test complexity analysis for simple task."""
        task = Task(
            id="simple-task",
            project_id="proj-001",
            spec_id="F001",
            title="Simple Task",
            description="A short description",
            steps=["Step 1", "Step 2"],
            depends_on=[],
        )
        
        result = analyze_task_complexity(task)
        
        assert result["is_complex"] == False
        assert result["should_decompose"] == False
        assert result["complexity_score"] < 4

    def test_analyze_task_complexity_complex_task(self):
        """Test complexity analysis for complex task."""
        task = Task(
            id="complex-task",
            project_id="proj-001",
            spec_id="F002",
            title="Complex Task",
            description="A very long description " * 50,  # Long description
            steps=["Step " + str(i) for i in range(15)],  # Many steps
            depends_on=["F001", "F002", "F003", "F004", "F005", "F006"],  # Many deps
        )
        
        result = analyze_task_complexity(task)
        
        assert result["is_complex"] == True
        assert result["complexity_score"] >= 4

    def test_classify_failure_full_pipeline(self, tmp_path):
        """Test full classification pipeline with real task."""
        db = DatabaseManager(tmp_path / "test.db")
        project = Project(
            id="test-proj-classify",
            name="test-project",
            description="Test project",
            workspace_dir=str(tmp_path),
            spec_source=f"file://{tmp_path}/spec.yaml",
        )
        project_id = db.create_project(project)
        
        task = Task(
            id="task-classify-001",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="Implement a feature",
            steps=["Step 1", "Step 2"],
        )
        db.create_task(task)
        
        # Get task from DB
        task = db.get_task("task-classify-001")
        
        error_history = [
            {"error_msg": "ModuleNotFoundError: No module named 'requests'"},
        ]
        deps_status = {}
        
        result = classify_failure(task, error_history, deps_status)
        
        assert isinstance(result, ClassificationResult)
        assert result.failure_type is not None
        assert result.confidence > 0
        assert result.recommended_action is not None
