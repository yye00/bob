"""Core data models for BOB framework.

This module defines the data structures used throughout BOB for managing
projects, tasks, sessions, and agent configurations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# Enumerations

class ProjectStatus(str, Enum):
    """Status of a project."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    """Status of a task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESEARCH_NEEDED = "research_needed"
    RESEARCH_COMPLETE = "research_complete"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEPRECATED = "deprecated"


class SessionStatus(str, Enum):
    """Status of an agent session."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class AgentType(str, Enum):
    """Type of agent."""
    INITIALIZER = "initializer"
    CODING = "coding"
    FEATURE_SYNC = "feature_sync"
    RESEARCH = "research"
    DIAGNOSIS = "diagnosis"
    ESCALATION = "escalation"


class ModelTier(str, Enum):
    """Model tier for escalation system.

    Matches the autonomous-coding escalation system:
    - TIER1/SONNET: Default model for initial attempts
    - TIER2/OPUS: Escalated model after repeated failures

    The enum values are "tier1" and "tier2" for database compatibility,
    while the actual model names are stored in current_model field.
    """
    TIER1 = "tier1"  # Sonnet - claude-sonnet-4-5-20250929
    TIER2 = "tier2"  # Opus - claude-opus-4-5-20251101

    # Aliases for semantic clarity
    SONNET = "tier1"
    OPUS = "tier2"


class FailureType(str, Enum):
    """Type of failure detected by diagnosis.

    Matches the autonomous-coding escalation system failure classification.
    Each failure type triggers a different recovery action.
    """
    UNKNOWN = "unknown"
    TOO_BIG = "too_big"  # Feature is too complex, needs decomposition
    MISSING_INFO = "missing_info"  # Missing information, needs research
    WRONG_INFRA = "wrong_infra"  # Missing packages/tools, needs user
    BAD_ASSUMPTIONS = "bad_assumptions"  # Wrong approach, needs restructure
    NEEDS_RESEARCH = "needs_research"  # Specific research needed
    DEPS_NOT_MET = "deps_not_met"  # Dependencies not satisfied yet

    # Legacy aliases for backward compatibility
    KNOWLEDGE_GAP = "missing_info"
    COMPLEXITY = "too_big"
    AMBIGUITY = "bad_assumptions"
    ENVIRONMENT = "wrong_infra"
    DEPENDENCY = "deps_not_met"
    TIMEOUT = "unknown"


class EscalationAction(str, Enum):
    """Action to take based on escalation state.

    Matches the autonomous-coding escalation system actions.
    """
    CONTINUE = "continue"  # Keep trying with current model
    ESCALATE_MODEL = "escalate_model"  # Switch to better model
    DIAGNOSE = "diagnose"  # Run root cause analysis
    DECOMPOSE = "decompose"  # Break feature into sub-features
    RESEARCH = "research"  # Research mode (web search, experimentation)
    REQUEST_USER = "request_user"  # Stop and ask user for help
    RESTRUCTURE = "restructure"  # Research and restructure feature
    SKIP = "skip"  # Skip feature (deps not met)

    # Legacy aliases for backward compatibility
    RETRY_SAME_MODEL = "continue"
    ESCALATE_TO_OPUS = "escalate_model"
    REQUEST_RESEARCH = "research"
    DECOMPOSE_TASK = "decompose"
    REQUEST_USER_INPUT = "request_user"
    SKIP_TASK = "skip"


# Data Models

@dataclass
class Project:
    """Represents a project managed by BOB.

    A project is the top-level container for tasks, sessions, and configuration.
    """
    id: str
    name: str
    description: str
    workspace_dir: str
    spec_source: str  # e.g., "file://spec.yaml", "github://org/repo/issues"
    config: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    status: ProjectStatus = ProjectStatus.ACTIVE
    last_sync_hash: Optional[str] = None  # Hash of spec source at last sync
    last_sync_at: Optional[datetime] = None  # Timestamp of last sync


@dataclass
class Task:
    """Represents a task extracted from a project specification.

    Tasks are the fundamental unit of work in BOB. They map to features
    in the spec and track progress, dependencies, and escalation state.
    """
    id: str
    project_id: str
    spec_id: str  # ID from the spec (e.g., "F001", issue number, etc.)
    title: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    priority: str = "medium"  # critical, high, medium, low
    category: str = "functional"
    labels: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[AgentType] = None
    current_model: str = "claude-sonnet-4-5-20250929"
    attempts: int = 0
    escalation_tier: ModelTier = ModelTier.TIER1
    failure_type: Optional[FailureType] = None
    research_required: bool = False
    research_complete: bool = False
    research_queries: list[str] = field(default_factory=list)
    research_findings: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """Represents a single agent execution session.

    A session tracks one invocation of an agent (e.g., coding, research)
    including duration, resource usage, and outcomes.
    """
    id: str
    project_id: str
    task_id: Optional[str]  # None for project-level sessions (e.g., feature sync)
    agent_type: AgentType
    model: str
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    status: SessionStatus = SessionStatus.RUNNING
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float = 0.0

    # Legacy property for backward compatibility
    @property
    def tokens(self) -> dict[str, int]:
        """Get tokens as a dict for backward compatibility."""
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "cache_read": self.cache_read_tokens,
            "cache_write": self.cache_write_tokens,
        }

    # Convenience property
    @property
    def current_model(self) -> str:
        """Alias for model field."""
        return self.model


@dataclass
class AgentConfig:
    """Configuration for an agent type.

    Defines how a specific agent type should be configured, including
    which model to use, what tools are available, and behavior settings.
    """
    agent_type: AgentType
    model: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    max_turns: int = 100
    temperature: float = 1.0
