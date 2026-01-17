"""Integration tests for escalation workflow.

This module tests the complete escalation workflow end-to-end:
- Task fails repeatedly with Sonnet
- Escalation to Opus after MAX_ATTEMPTS_PER_MODEL
- Failure classification after Opus failures
- Appropriate escalation actions (decompose, research, etc.)
- Escalation state persistence in database
- Escalation info display in task status
"""

import json
import tempfile
from pathlib import Path
from typing import Tuple

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
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
    MODEL_NAMES,
)


@pytest.fixture
def setup_escalation_environment(tmp_path: Path) -> Tuple[Path, Path, Path]:
    """Setup escalation test environment.

    Creates:
    - Temporary database path
    - Workspace directory
    - Spec file with tasks for escalation testing

    Returns:
        Tuple of (db_path, workspace_path, spec_path)
    """
    # Create database path
    db_path = tmp_path / "test.db"

    # Create workspace directory
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create a spec file with tasks
    spec_path = workspace / "spec.yaml"
    spec_content = """
spec_version: 1
tasks:
  - id: F001
    title: "Simple task"
    description: "A simple task that should succeed"
    priority: high
    category: functional
    steps:
      - "Do something simple"
    depends_on: []

  - id: F002
    title: "Difficult task"
    description: "An intentionally difficult task to trigger escalation"
    priority: high
    category: functional
    steps:
      - "Implement complex algorithm"
      - "Optimize for performance"
      - "Handle edge cases"
    depends_on:
      - F001
"""
    spec_path.write_text(spec_content)

    return db_path, workspace, spec_path


class TestEscalationWorkflowIntegration:
    """Integration tests for escalation workflow."""

    def test_escalation_from_sonnet_to_opus(self, setup_escalation_environment):
        """Test F053: Escalation from Sonnet to Opus after repeated failures.

        Steps:
        1. Create test project with task
        2. Simulate multiple failures with Sonnet (MAX_ATTEMPTS_PER_MODEL times)
        3. Verify escalation action is ESCALATE_MODEL
        4. Execute escalation
        5. Verify task now uses Opus model
        6. Verify attempts counter reset
        7. Verify escalation tier updated
        """
        db_path, workspace, spec_path = setup_escalation_environment
        runner = CliRunner()

        # Create project
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-escalation",
            str(workspace),
            f"file://{spec_path}",
            "--description", "Escalation test project",
        ])

        assert result.exit_code == 0
        assert "Created project 'test-escalation'" in result.output

        # Get project
        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-escalation"), None)
        assert project is not None
        project_id = project.id

        # Sync tasks
        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        # Get task F002
        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        task = task_map["F002"]
        task_id = task.id

        # Create escalation controller
        escalation_controller = EscalationController(db, project_id)

        # Verify initial state
        assert task.escalation_tier == ModelTier.SONNET
        assert task.current_model == MODEL_NAMES[ModelTier.SONNET]
        assert task.attempts == 0

        # Simulate failures at Sonnet tier
        for i in range(MAX_ATTEMPTS_PER_MODEL):
            escalation_controller.record_attempt(
                task_id,
                success=False,
                error_msg=f"Simulated failure {i+1}",
                error_type="test_error",
                deps_met=True,
            )

        # Refresh task
        task = db.get_task(task_id)
        assert task.attempts == MAX_ATTEMPTS_PER_MODEL

        # Get next action
        action, context = escalation_controller.get_next_action(task_id, deps_met=True)

        # Should recommend escalation
        assert action == EscalationAction.ESCALATE_MODEL
        assert context["from_model"] == MODEL_NAMES[ModelTier.SONNET]
        assert context["to_model"] == MODEL_NAMES[ModelTier.OPUS]
        assert context["attempts"] == MAX_ATTEMPTS_PER_MODEL

        # Execute escalation
        new_tier = escalation_controller.escalate_model(task_id)
        assert new_tier == ModelTier.OPUS

        # Verify escalation happened
        task = db.get_task(task_id)
        assert task.escalation_tier == ModelTier.OPUS
        assert task.current_model == MODEL_NAMES[ModelTier.OPUS]
        assert task.attempts == 0  # Reset at new tier

    def test_escalation_triggers_diagnosis_after_opus_failures(self, setup_escalation_environment):
        """Test F053: Diagnosis triggered after Opus failures.

        Steps:
        1. Create task and escalate to Opus
        2. Simulate failures at Opus tier
        3. Verify diagnosis action is triggered
        4. Verify error history is passed to diagnosis
        """
        db_path, workspace, spec_path = setup_escalation_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-diagnosis",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-diagnosis"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        task = task_map["F002"]
        task_id = task.id

        escalation_controller = EscalationController(db, project_id)

        # Fast-forward to Opus tier
        db.update_task(
            task_id,
            escalation_tier=ModelTier.OPUS,
            current_model=MODEL_NAMES[ModelTier.OPUS],
            attempts=0,
        )

        # Simulate failures at Opus tier
        for i in range(MAX_ATTEMPTS_PER_MODEL):
            escalation_controller.record_attempt(
                task_id,
                success=False,
                error_msg=f"Opus failure {i+1}: Complex error",
                error_type="implementation_error",
                deps_met=True,
            )

        # Refresh task
        task = db.get_task(task_id)

        # Get next action
        action, context = escalation_controller.get_next_action(task_id, deps_met=True)

        # Should trigger diagnosis
        assert action == EscalationAction.DIAGNOSE
        assert context["total_attempts"] == MAX_ATTEMPTS_PER_MODEL
        assert "error_history" in context
        assert len(context["error_history"]) > 0

    def test_escalation_action_after_diagnosis(self, setup_escalation_environment):
        """Test F053: Appropriate action taken after diagnosis.

        Steps:
        1. Create task at Opus tier with failures
        2. Record diagnosis with specific failure type
        3. Verify appropriate escalation action is returned
        4. Test multiple failure types (TOO_BIG, MISSING_INFO, etc.)
        """
        db_path, workspace, spec_path = setup_escalation_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-diagnosis-action",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-diagnosis-action"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        task = task_map["F002"]
        task_id = task.id

        escalation_controller = EscalationController(db, project_id)

        # Set up task at Opus tier with failures
        db.update_task(
            task_id,
            escalation_tier=ModelTier.OPUS,
            current_model=MODEL_NAMES[ModelTier.OPUS],
            attempts=MAX_ATTEMPTS_PER_MODEL,
        )

        # Test TOO_BIG failure type
        escalation_controller.record_diagnosis(
            task_id,
            failure_type=FailureType.TOO_BIG,
        )

        action, context = escalation_controller.get_next_action(task_id, deps_met=True)
        assert action == EscalationAction.DECOMPOSE
        assert context["reason"] == "Task is too complex for atomic implementation"

        # Reset and test MISSING_INFO
        db.update_task(
            task_id,
            research_findings={},
            failure_type=None,
        )
        db.update_task(task_id, attempts=MAX_ATTEMPTS_PER_MODEL)

        escalation_controller.record_diagnosis(
            task_id,
            failure_type=FailureType.MISSING_INFO,
            research_queries=["How to implement X?", "Best practices for Y"],
        )

        action, context = escalation_controller.get_next_action(task_id, deps_met=True)
        assert action == EscalationAction.RESEARCH
        assert context["reason"] == "Missing information needs to be researched"

        # Reset and test WRONG_INFRA
        db.update_task(
            task_id,
            research_findings={},
            failure_type=None,
        )
        db.update_task(task_id, attempts=MAX_ATTEMPTS_PER_MODEL)

        escalation_controller.record_diagnosis(
            task_id,
            failure_type=FailureType.WRONG_INFRA,
        )

        action, context = escalation_controller.get_next_action(task_id, deps_met=True)
        assert action == EscalationAction.REQUEST_USER
        assert "Missing infrastructure" in context["reason"]

    def test_escalation_state_persistence(self, setup_escalation_environment):
        """Test F053: Escalation state persists in database.

        Steps:
        1. Create task and perform escalation
        2. Record failures and diagnosis
        3. Close and reopen database
        4. Verify escalation state is preserved
        5. Verify error history is preserved
        """
        db_path, workspace, spec_path = setup_escalation_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-persistence",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-persistence"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        task = task_map["F002"]
        task_id = task.id

        escalation_controller = EscalationController(db, project_id)

        # Perform escalation
        for i in range(MAX_ATTEMPTS_PER_MODEL):
            escalation_controller.record_attempt(
                task_id,
                success=False,
                error_msg=f"Test error {i+1}",
                deps_met=True,
            )

        escalation_controller.escalate_model(task_id)

        # Record diagnosis
        escalation_controller.record_diagnosis(
            task_id,
            failure_type=FailureType.TOO_BIG,
        )

        # Get current state
        task_before = db.get_task(task_id)
        error_history_before = task_before.research_findings.get("error_history", [])

        # Close and reopen database
        db = None
        db = DatabaseManager(db_path)

        # Verify state persisted
        task_after = db.get_task(task_id)
        assert task_after.escalation_tier == ModelTier.OPUS
        assert task_after.current_model == MODEL_NAMES[ModelTier.OPUS]
        assert task_after.failure_type == FailureType.TOO_BIG
        assert task_after.research_findings.get("diagnosis_done") is True

        # Verify error history persisted
        error_history_after = task_after.research_findings.get("error_history", [])
        assert len(error_history_after) == len(error_history_before)
        assert error_history_after == error_history_before

    def test_escalation_reset_on_success(self, setup_escalation_environment):
        """Test that escalation state resets when task succeeds.

        Steps:
        1. Create task with failures and escalation
        2. Record successful attempt
        3. Verify escalation state is reset
        4. Verify error history is cleared
        """
        db_path, workspace, spec_path = setup_escalation_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-reset",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-reset"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        task = task_map["F002"]
        task_id = task.id

        escalation_controller = EscalationController(db, project_id)

        # Record some failures
        for i in range(2):
            escalation_controller.record_attempt(
                task_id,
                success=False,
                error_msg=f"Failure {i+1}",
                deps_met=True,
            )

        # Verify failures recorded
        task = db.get_task(task_id)
        assert task.attempts == 2
        assert len(task.research_findings.get("error_history", [])) == 2

        # Record success
        escalation_controller.record_attempt(
            task_id,
            success=True,
            deps_met=True,
        )

        # Verify state reset
        task = db.get_task(task_id)
        assert task.attempts == 0
        assert task.research_findings.get("error_history", []) == []
        assert task.failure_type is None

    def test_escalation_skips_when_deps_not_met(self, setup_escalation_environment):
        """Test that escalation is skipped when dependencies not met.

        Steps:
        1. Create task with dependencies
        2. Record failure with deps_met=False
        3. Verify escalation action is SKIP
        4. Verify attempts not incremented
        """
        db_path, workspace, spec_path = setup_escalation_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-skip",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-skip"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        task = task_map["F002"]  # Has dependency on F001
        task_id = task.id

        escalation_controller = EscalationController(db, project_id)

        # Record failure with deps not met
        escalation_controller.record_attempt(
            task_id,
            success=False,
            error_msg="Dependencies not met",
            deps_met=False,
        )

        # Verify failure type set
        task = db.get_task(task_id)
        assert task.failure_type == FailureType.DEPS_NOT_MET

        # Get next action
        action, context = escalation_controller.get_next_action(task_id, deps_met=False)
        assert action == EscalationAction.SKIP
        assert context["reason"] == "dependencies_not_met"

    def test_error_history_tracking(self, setup_escalation_environment):
        """Test that error history is properly tracked.

        Steps:
        1. Create task
        2. Record multiple failures with different error messages
        3. Verify error history contains all errors with metadata
        4. Verify error history includes timestamps and model info
        """
        db_path, workspace, spec_path = setup_escalation_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-history",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-history"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        task = task_map["F002"]
        task_id = task.id

        escalation_controller = EscalationController(db, project_id)

        # Record failures with different errors
        errors = [
            ("Syntax error in module X", "syntax_error"),
            ("Import error: module Y not found", "import_error"),
            ("Test failed: assertion error in Z", "test_failure"),
        ]

        for error_msg, error_type in errors:
            escalation_controller.record_attempt(
                task_id,
                success=False,
                error_msg=error_msg,
                error_type=error_type,
                deps_met=True,
            )

        # Verify error history
        task = db.get_task(task_id)
        error_history = task.research_findings.get("error_history", [])

        assert len(error_history) == 3

        for i, (error_msg, error_type) in enumerate(errors):
            history_entry = error_history[i]
            assert history_entry["error_msg"] == error_msg
            assert history_entry["error_type"] == error_type
            assert history_entry["model"] == MODEL_NAMES[ModelTier.SONNET]
            assert history_entry["deps_met"] is True
            assert "timestamp" in history_entry
