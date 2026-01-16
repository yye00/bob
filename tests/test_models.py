"""Tests for core data models."""

from datetime import datetime
from bob.models import (
    Project,
    Task,
    Session,
    AgentConfig,
    ProjectStatus,
    TaskStatus,
    SessionStatus,
    AgentType,
    ModelTier,
    FailureType,
    EscalationAction,
)


class TestEnums:
    """Test all enum types."""

    def test_project_status_values(self):
        """Test ProjectStatus enum has all expected values."""
        assert ProjectStatus.ACTIVE == "active"
        assert ProjectStatus.PAUSED == "paused"
        assert ProjectStatus.COMPLETED == "completed"
        assert ProjectStatus.ARCHIVED == "archived"

    def test_task_status_values(self):
        """Test TaskStatus enum has all expected values."""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.BLOCKED == "blocked"
        assert TaskStatus.RESEARCH_NEEDED == "research_needed"
        assert TaskStatus.RESEARCH_COMPLETE == "research_complete"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.SKIPPED == "skipped"
        assert TaskStatus.DEPRECATED == "deprecated"

    def test_session_status_values(self):
        """Test SessionStatus enum has all expected values."""
        assert SessionStatus.RUNNING == "running"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.FAILED == "failed"
        assert SessionStatus.TIMEOUT == "timeout"
        assert SessionStatus.CANCELLED == "cancelled"

    def test_agent_type_values(self):
        """Test AgentType enum has all expected values."""
        assert AgentType.INITIALIZER == "initializer"
        assert AgentType.CODING == "coding"
        assert AgentType.FEATURE_SYNC == "feature_sync"
        assert AgentType.RESEARCH == "research"
        assert AgentType.DIAGNOSIS == "diagnosis"
        assert AgentType.ESCALATION == "escalation"

    def test_model_tier_values(self):
        """Test ModelTier enum has all expected values."""
        assert ModelTier.TIER1 == "tier1"
        assert ModelTier.TIER2 == "tier2"

    def test_failure_type_values(self):
        """Test FailureType enum has all expected values."""
        assert FailureType.KNOWLEDGE_GAP == "knowledge_gap"
        assert FailureType.COMPLEXITY == "complexity"
        assert FailureType.AMBIGUITY == "ambiguity"
        assert FailureType.ENVIRONMENT == "environment"
        assert FailureType.DEPENDENCY == "dependency"
        assert FailureType.TIMEOUT == "timeout"
        assert FailureType.UNKNOWN == "unknown"

    def test_escalation_action_values(self):
        """Test EscalationAction enum has all expected values."""
        assert EscalationAction.RETRY_SAME_MODEL == "retry_same_model"
        assert EscalationAction.ESCALATE_TO_OPUS == "escalate_to_opus"
        assert EscalationAction.REQUEST_RESEARCH == "request_research"
        assert EscalationAction.DECOMPOSE_TASK == "decompose_task"
        assert EscalationAction.REQUEST_USER_INPUT == "request_user_input"
        assert EscalationAction.SKIP_TASK == "skip_task"


class TestProject:
    """Test Project dataclass."""

    def test_project_creation_minimal(self):
        """Test creating a project with minimal required fields."""
        project = Project(
            id="proj-1",
            name="Test Project",
            description="A test project",
            workspace_dir="/tmp/test",
            spec_source="file://spec.yaml",
        )
        assert project.id == "proj-1"
        assert project.name == "Test Project"
        assert project.description == "A test project"
        assert project.workspace_dir == "/tmp/test"
        assert project.spec_source == "file://spec.yaml"
        assert project.status == ProjectStatus.ACTIVE
        assert project.config == {}
        assert isinstance(project.created_at, datetime)

    def test_project_creation_with_config(self):
        """Test creating a project with custom config."""
        config = {"model": "claude-opus-4-5-20251101", "max_cost": 10.0}
        project = Project(
            id="proj-2",
            name="Configured Project",
            description="A project with config",
            workspace_dir="/tmp/configured",
            spec_source="github://org/repo/issues",
            config=config,
            status=ProjectStatus.PAUSED,
        )
        assert project.config == config
        assert project.status == ProjectStatus.PAUSED


class TestTask:
    """Test Task dataclass."""

    def test_task_creation_minimal(self):
        """Test creating a task with minimal required fields."""
        task = Task(
            id="task-1",
            project_id="proj-1",
            spec_id="F001",
            title="Implement feature",
            description="A feature to implement",
        )
        assert task.id == "task-1"
        assert task.project_id == "proj-1"
        assert task.spec_id == "F001"
        assert task.title == "Implement feature"
        assert task.description == "A feature to implement"
        assert task.status == TaskStatus.PENDING
        assert task.priority == "medium"
        assert task.category == "functional"
        assert task.acceptance_criteria == []
        assert task.steps == []
        assert task.depends_on == []
        assert task.labels == []
        assert task.assigned_agent is None
        assert task.current_model == "claude-sonnet-4-5-20250929"
        assert task.attempts == 0
        assert task.escalation_tier == ModelTier.TIER1
        assert task.failure_type is None
        assert task.research_required is False
        assert task.research_complete is False
        assert task.research_queries == []
        assert task.research_findings == {}

    def test_task_creation_full(self):
        """Test creating a task with all fields populated."""
        task = Task(
            id="task-2",
            project_id="proj-1",
            spec_id="F042",
            title="Complex feature",
            description="A complex feature requiring research",
            acceptance_criteria=["Criterion 1", "Criterion 2"],
            steps=["Step 1", "Step 2", "Step 3"],
            depends_on=["F001", "F010"],
            priority="critical",
            category="functional",
            labels=["backend", "api"],
            status=TaskStatus.RESEARCH_NEEDED,
            assigned_agent=AgentType.RESEARCH,
            current_model="claude-opus-4-5-20251101",
            attempts=2,
            escalation_tier=ModelTier.TIER2,
            failure_type=FailureType.KNOWLEDGE_GAP,
            research_required=True,
            research_complete=False,
            research_queries=["How to implement X?", "Best practices for Y"],
            research_findings={"key": "finding"},
        )
        assert task.priority == "critical"
        assert task.status == TaskStatus.RESEARCH_NEEDED
        assert task.assigned_agent == AgentType.RESEARCH
        assert task.escalation_tier == ModelTier.TIER2
        assert task.failure_type == FailureType.KNOWLEDGE_GAP
        assert task.research_required is True
        assert len(task.research_queries) == 2
        assert task.research_findings == {"key": "finding"}


class TestSession:
    """Test Session dataclass."""

    def test_session_creation_minimal(self):
        """Test creating a session with minimal required fields."""
        session = Session(
            id="session-1",
            project_id="proj-1",
            task_id="task-1",
            agent_type=AgentType.CODING,
            model="claude-sonnet-4-5-20250929",
        )
        assert session.id == "session-1"
        assert session.project_id == "proj-1"
        assert session.task_id == "task-1"
        assert session.agent_type == AgentType.CODING
        assert session.model == "claude-sonnet-4-5-20250929"
        assert session.status == SessionStatus.RUNNING
        assert isinstance(session.started_at, datetime)
        assert session.ended_at is None
        assert session.turns == 0
        assert session.tokens == {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        assert session.cost == 0.0

    def test_session_creation_with_stats(self):
        """Test creating a session with usage statistics."""
        now = datetime.now()
        session = Session(
            id="session-2",
            project_id="proj-1",
            task_id=None,  # Project-level session
            agent_type=AgentType.FEATURE_SYNC,
            model="claude-sonnet-4-5-20250929",
            started_at=now,
            status=SessionStatus.COMPLETED,
            turns=5,
            input_tokens=1000,
            output_tokens=500,
            cost=0.05,
        )
        assert session.task_id is None
        assert session.status == SessionStatus.COMPLETED
        assert session.turns == 5
        assert session.tokens["input"] == 1000
        assert session.tokens["output"] == 500
        assert session.cost == 0.05


class TestAgentConfig:
    """Test AgentConfig dataclass."""

    def test_agent_config_creation_minimal(self):
        """Test creating agent config with minimal fields."""
        config = AgentConfig(
            agent_type=AgentType.CODING,
            model="claude-sonnet-4-5-20250929",
            system_prompt="You are a coding agent.",
        )
        assert config.agent_type == AgentType.CODING
        assert config.model == "claude-sonnet-4-5-20250929"
        assert config.system_prompt == "You are a coding agent."
        assert config.allowed_tools == []
        assert config.mcp_servers == []
        assert config.max_turns == 100
        assert config.temperature == 1.0

    def test_agent_config_creation_full(self):
        """Test creating agent config with all fields."""
        config = AgentConfig(
            agent_type=AgentType.RESEARCH,
            model="claude-opus-4-5-20251101",
            system_prompt="You are a research agent.",
            allowed_tools=["web_search", "perplexity"],
            mcp_servers=["perplexity"],
            max_turns=50,
            temperature=0.7,
        )
        assert config.agent_type == AgentType.RESEARCH
        assert config.allowed_tools == ["web_search", "perplexity"]
        assert config.mcp_servers == ["perplexity"]
        assert config.max_turns == 50
        assert config.temperature == 0.7


class TestModelTypeHints:
    """Test that all models have proper type hints."""

    def test_project_has_type_hints(self):
        """Verify Project has type annotations."""
        annotations = Project.__annotations__
        assert "id" in annotations
        assert "name" in annotations
        assert "description" in annotations
        assert "workspace_dir" in annotations
        assert "spec_source" in annotations
        assert "config" in annotations
        assert "created_at" in annotations
        assert "status" in annotations

    def test_task_has_type_hints(self):
        """Verify Task has type annotations."""
        annotations = Task.__annotations__
        assert "id" in annotations
        assert "project_id" in annotations
        assert "spec_id" in annotations
        assert "title" in annotations
        assert "description" in annotations
        assert "status" in annotations
        assert "research_required" in annotations

    def test_session_has_type_hints(self):
        """Verify Session has type annotations."""
        annotations = Session.__annotations__
        assert "id" in annotations
        assert "project_id" in annotations
        assert "task_id" in annotations
        assert "agent_type" in annotations
        assert "model" in annotations
        assert "status" in annotations

    def test_agent_config_has_type_hints(self):
        """Verify AgentConfig has type annotations."""
        annotations = AgentConfig.__annotations__
        assert "agent_type" in annotations
        assert "model" in annotations
        assert "system_prompt" in annotations
        assert "max_turns" in annotations
