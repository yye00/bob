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
    """Model tier for escalation system."""
    TIER1 = "tier1"  # Sonnet (default)
    TIER2 = "tier2"  # Opus (escalated)


class FailureType(str, Enum):
    """Type of failure detected by failure_classifier."""
    KNOWLEDGE_GAP = "knowledge_gap"
    COMPLEXITY = "complexity"
    AMBIGUITY = "ambiguity"
    ENVIRONMENT = "environment"
    DEPENDENCY = "dependency"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class EscalationAction(str, Enum):
    """Action to take on escalation."""
    RETRY_SAME_MODEL = "retry_same_model"
    ESCALATE_TO_OPUS = "escalate_to_opus"
    REQUEST_RESEARCH = "request_research"
    DECOMPOSE_TASK = "decompose_task"
    REQUEST_USER_INPUT = "request_user_input"
    SKIP_TASK = "skip_task"


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
    tokens: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    cost: float = 0.0


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
