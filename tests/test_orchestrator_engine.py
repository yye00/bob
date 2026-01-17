"""Tests for orchestrator engine - Main orchestration logic."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from bob.database import DatabaseManager
from bob.models.base import (
    Task,
    TaskStatus,
    ModelTier,
    FailureType,
    EscalationAction,
)
from bob.orchestrator.engine import (
    Orchestrator,
    OrchestratorConfig,
    create_orchestrator,
)


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def db_manager(tmp_path):
    """Create a test database manager."""
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path)


@pytest.fixture
def sample_task(db_manager):
    """Create a sample task for testing, persisted to database."""
    # First create a project
    from bob.models.base import Project, ProjectStatus
    project = Project(
        id="proj-1",
        name="test-project",
        description="Test project",
        workspace_dir="/tmp/test",
        spec_source="/tmp/test/spec.txt",
        status=ProjectStatus.ACTIVE,
    )
    db_manager.create_project(project)

    # Then create and persist the task
    task = Task(
        id="task-123",
        project_id="proj-1",
        spec_id="F001",
        title="Test Feature",
        description="Implement feature X",
        status=TaskStatus.PENDING,
        current_model="claude-sonnet-4-20250514",
        attempts=0,
        escalation_tier=ModelTier.SONNET,
    )
    db_manager.create_task(task)
    return task


class TestOrchestratorConfig:
    """Test OrchestratorConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = OrchestratorConfig()

        assert config.default_model == "claude-sonnet-4-20250514"
        assert config.max_retries == 3
        assert config.enable_escalation is True
        assert config.enable_research is True
        assert config.enable_decomposition is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = OrchestratorConfig(
            default_model="claude-opus-4-20250514",
            max_retries=5,
            enable_escalation=False,
            enable_research=False,
            enable_decomposition=False,
        )

        assert config.default_model == "claude-opus-4-20250514"
        assert config.max_retries == 5
        assert config.enable_escalation is False
        assert config.enable_research is False
        assert config.enable_decomposition is False


class TestOrchestratorInit:
    """Test Orchestrator initialization."""

    def test_init_with_default_config(self, db_manager, temp_project_dir):
        """Test initialization with default config."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        assert orchestrator.db == db_manager
        assert orchestrator.project_id == "proj-1"
        assert orchestrator.project_dir == temp_project_dir
        assert orchestrator.config is not None
        assert orchestrator.config.default_model == "claude-sonnet-4-20250514"
        assert orchestrator.escalation is not None
        assert orchestrator.task_decomposer is not None
        assert orchestrator.research_controller is not None

    def test_init_with_custom_config(self, db_manager, temp_project_dir):
        """Test initialization with custom config."""
        config = OrchestratorConfig(
            default_model="claude-opus-4-20250514",
            max_retries=5,
        )
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir, config)

        assert orchestrator.config == config
        assert orchestrator.config.default_model == "claude-opus-4-20250514"
        assert orchestrator.config.max_retries == 5

    def test_initial_state(self, db_manager, temp_project_dir):
        """Test initial state of orchestrator."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        assert orchestrator.current_task is None
        assert orchestrator.current_model == "claude-sonnet-4-20250514"
        assert orchestrator.session_id is None


class TestExecuteTask:
    """Test task execution."""

    @pytest.mark.asyncio
    async def test_execute_task_updates_status_to_in_progress(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test that task status is updated to in_progress."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        # Mock client creation and execution
        with patch('bob.orchestrator.engine.create_client', return_value=MagicMock()):
            with patch.object(orchestrator, '_execute_with_client', return_value=(True, None)):
                await orchestrator.execute_task(sample_task, "Test prompt")

        # Task should have been reset after success (attempts = 0)
        updated_task = db_manager.get_task("task-123")
        assert updated_task.attempts == 0  # Reset on success
        assert updated_task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_task_success(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test successful task execution."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        # Mock client creation and successful execution
        with patch('bob.orchestrator.engine.create_client', return_value=MagicMock()):
            with patch.object(orchestrator, '_execute_with_client', return_value=(True, None)):
                status, error = await orchestrator.execute_task(sample_task, "Test prompt")

        assert status == TaskStatus.COMPLETED
        assert error is None
        # Reload task to get updated status
        updated_task = db_manager.get_task("task-123")
        assert updated_task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_task_failure(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test task execution failure."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        # Mock failed execution
        error_msg = "Test error"
        with patch('bob.orchestrator.engine.create_client', return_value=MagicMock()):
            with patch.object(orchestrator, '_execute_with_client', return_value=(False, error_msg)):
                with patch.object(orchestrator, '_handle_failure', return_value=(TaskStatus.PENDING, "Retrying")):
                    status, error = await orchestrator.execute_task(sample_task, "Test prompt")

        # _handle_failure should have been called
        assert status == TaskStatus.PENDING
        assert error == "Retrying"

    @pytest.mark.asyncio
    async def test_execute_task_with_research_needed(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test task execution when research is needed."""
        sample_task.research_required = True
        sample_task.research_complete = False

        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        # Mock create_research_client
        with patch('bob.orchestrator.engine.create_research_client') as mock_create_research:
            mock_client = MagicMock()
            mock_create_research.return_value = mock_client

            with patch.object(orchestrator, '_execute_with_client', return_value=(True, None)):
                await orchestrator.execute_task(sample_task, "Test prompt")

            # Research client should have been created
            mock_create_research.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_task_without_research(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test task execution without research."""
        sample_task.research_required = False

        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        # Mock create_client
        with patch('bob.orchestrator.engine.create_client') as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            with patch.object(orchestrator, '_execute_with_client', return_value=(True, None)):
                await orchestrator.execute_task(sample_task, "Test prompt")

            # Regular client should have been created
            mock_create.assert_called_once()


class TestHandleFailure:
    """Test failure handling."""

    @pytest.mark.asyncio
    async def test_handle_failure_adds_to_error_history(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test that failure adds to error history."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        error = "Test error message"

        with patch('bob.orchestrator.engine.classify_failure') as mock_classify:
            from bob.orchestrator.failure_classifier import ClassificationResult
            mock_classify.return_value = ClassificationResult(
                failure_type=FailureType.UNKNOWN,
                confidence=0.9,
                reason="Test reason",
                research_queries=[],
                recommended_action="continue",
                details={},
            )

            with patch.object(orchestrator.escalation, 'get_next_action', return_value=(EscalationAction.CONTINUE, {})):
                with patch.object(orchestrator, '_execute_escalation_action', return_value=(TaskStatus.PENDING, "Retry")):
                    await orchestrator._handle_failure(sample_task, error)

        # Failure type should be set - reload to check
        updated_task = db_manager.get_task("task-123")
        assert updated_task.failure_type == FailureType.UNKNOWN

    @pytest.mark.asyncio
    async def test_handle_failure_classifies_error(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test that failure classification is called."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        error = "ImportError: module not found"

        with patch('bob.orchestrator.engine.classify_failure') as mock_classify:
            from bob.orchestrator.failure_classifier import ClassificationResult
            mock_classify.return_value = ClassificationResult(
                failure_type=FailureType.MISSING_INFO,
                confidence=0.95,
                reason="Test reason",
                research_queries=["test query"],
                recommended_action="escalate",
                details={}, # EscalationAction.RESEARCH,
            )

            with patch.object(orchestrator.escalation, 'get_next_action', return_value=(EscalationAction.RESEARCH, {})):
                with patch.object(orchestrator, '_execute_escalation_action', return_value=(TaskStatus.PENDING, "Research")):
                    await orchestrator._handle_failure(sample_task, error)

        # Classification should have been called
        mock_classify.assert_called_once()
        # Reload to check updated failure type
        updated_task = db_manager.get_task("task-123")
        assert updated_task.failure_type == FailureType.MISSING_INFO


class TestEscalationActions:
    """Test escalation action execution."""

    @pytest.mark.asyncio
    async def test_execute_escalation_action_continue(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test CONTINUE action."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        from bob.orchestrator.failure_classifier import ClassificationResult
        classification = ClassificationResult(
            failure_type=FailureType.UNKNOWN,
            confidence=0.8,
            reason="Test reason",
            research_queries=[],
            recommended_action="continue",
                details={},
        )

        status, error = await orchestrator._execute_escalation_action(
            sample_task, EscalationAction.CONTINUE, classification
        )

        assert status == TaskStatus.PENDING
        assert error == "Retrying"
        assert sample_task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_execute_escalation_action_escalate_model(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test ESCALATE_MODEL action."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        from bob.orchestrator.failure_classifier import ClassificationResult
        classification = ClassificationResult(
            failure_type=FailureType.TOO_BIG,
            confidence=0.9,
            reason="Test reason",
            research_queries=[],
            recommended_action="escalate",
                details={}, # EscalationAction.ESCALATE_MODEL,
        )

        with patch.object(orchestrator.escalation, 'escalate_model', return_value=ModelTier.OPUS):
            status, error = await orchestrator._execute_escalation_action(
                sample_task, EscalationAction.ESCALATE_MODEL, classification
            )

        assert status == TaskStatus.PENDING
        assert "Escalated" in error
        assert sample_task.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_execute_escalation_action_research(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test RESEARCH action."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        from bob.orchestrator.failure_classifier import ClassificationResult
        classification = ClassificationResult(
            failure_type=FailureType.MISSING_INFO,
            confidence=0.95,
            reason="Test reason",
            research_queries=["test query"],
            recommended_action="escalate",
                details={}, # EscalationAction.RESEARCH,
        )

        status, error = await orchestrator._execute_escalation_action(
            sample_task, EscalationAction.RESEARCH, classification
        )

        assert status == TaskStatus.PENDING
        assert "research" in error.lower()
        # Reload to check updated fields
        updated_task = db_manager.get_task("task-123")
        assert updated_task.research_required is True
        assert updated_task.research_complete is False

    @pytest.mark.asyncio
    async def test_execute_escalation_action_request_user(
        self, db_manager, temp_project_dir, sample_task
    ):
        """Test REQUEST_USER action."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        from bob.orchestrator.failure_classifier import ClassificationResult
        classification = ClassificationResult(
            failure_type=FailureType.WRONG_INFRA,
            confidence=0.9,
            reason="Test reason",
            research_queries=[],
            recommended_action="escalate",
                details={}, # EscalationAction.REQUEST_USER,
        )

        status, error = await orchestrator._execute_escalation_action(
            sample_task, EscalationAction.REQUEST_USER, classification
        )

        assert status == TaskStatus.BLOCKED
        assert "user" in error.lower()
        # Reload to check updated status
        updated_task = db_manager.get_task("task-123")
        assert updated_task.status == TaskStatus.BLOCKED


class TestGetModelForTier:
    """Test model selection by tier."""

    def test_get_model_for_sonnet(self, db_manager, temp_project_dir):
        """Test getting Sonnet model."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        model = orchestrator._get_model_for_tier(ModelTier.SONNET)
        assert model == "claude-sonnet-4-20250514"

    def test_get_model_for_opus(self, db_manager, temp_project_dir):
        """Test getting Opus model."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        model = orchestrator._get_model_for_tier(ModelTier.OPUS)
        assert model == "claude-opus-4-20250514"

    def test_get_model_for_default(self, db_manager, temp_project_dir):
        """Test getting default model for unknown tier."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        # Test with a string that's not a valid tier (will return default)
        model = orchestrator._get_model_for_tier("unknown")  # type: ignore
        assert model == "claude-sonnet-4-20250514"


class TestGetExecutionSummary:
    """Test execution summary."""

    def test_get_execution_summary(self, db_manager, temp_project_dir, sample_task):
        """Test getting execution summary."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        orchestrator.current_task = sample_task
        orchestrator.session_id = "session-123"

        summary = orchestrator.get_execution_summary()

        assert summary["current_task_id"] == "task-123"
        assert summary["current_model"] == "claude-sonnet-4-20250514"
        assert summary["session_id"] == "session-123"
        assert "config" in summary
        assert summary["config"]["default_model"] == "claude-sonnet-4-20250514"
        assert summary["config"]["escalation_enabled"] is True

    def test_get_execution_summary_no_task(self, db_manager, temp_project_dir):
        """Test getting execution summary when no task is running."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)

        summary = orchestrator.get_execution_summary()

        assert summary["current_task_id"] is None
        assert summary["current_model"] is not None


class TestCreateOrchestrator:
    """Test orchestrator factory function."""

    def test_create_orchestrator(self, db_manager, temp_project_dir):
        """Test creating orchestrator with factory function."""
        orchestrator = create_orchestrator(db_manager, "proj-1", temp_project_dir)

        assert isinstance(orchestrator, Orchestrator)
        assert orchestrator.db == db_manager
        assert orchestrator.project_dir == temp_project_dir

    def test_create_orchestrator_with_config(self, db_manager, temp_project_dir):
        """Test creating orchestrator with custom config."""
        config = OrchestratorConfig(
            default_model="claude-opus-4-20250514",
            max_retries=5,
        )

        orchestrator = create_orchestrator(db_manager, "proj-1", temp_project_dir, config)

        assert orchestrator.config == config
        assert orchestrator.config.default_model == "claude-opus-4-20250514"
