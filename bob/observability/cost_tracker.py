"""Cost tracking for BOB framework.

Tracks token usage and calculates costs for different Claude models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from bob.database.manager import DatabaseManager
from bob.models.base import ModelTier


# Pricing as of January 2026 (per 1M tokens)
# Source: https://www.anthropic.com/pricing
PRICING: Dict[str, Dict[str, float]] = {
    # Claude 3.5 Sonnet (newest, most capable)
    "claude-sonnet-4": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,  # 90% discount
        "cache_write": 3.75,  # 25% surcharge
    },
    "claude-sonnet-3-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    # Claude 3 Opus (most capable legacy)
    "claude-opus-3": {
        "input": 15.00,
        "output": 75.00,
        "cache_read": 1.50,
        "cache_write": 18.75,
    },
    # Claude 3.5 Haiku (fastest, cheapest)
    "claude-haiku-3-5": {
        "input": 0.80,
        "output": 4.00,
        "cache_read": 0.08,
        "cache_write": 1.00,
    },
    "claude-haiku-3": {
        "input": 0.25,
        "output": 1.25,
        "cache_read": 0.03,
        "cache_write": 0.30,
    },
}


@dataclass
class TokenUsage:
    """Token usage for a single API call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total number of tokens."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass
class CostBreakdown:
    """Cost breakdown for token usage."""

    input_cost: float
    output_cost: float
    cache_read_cost: float
    cache_write_cost: float

    @property
    def total_cost(self) -> float:
        """Total cost in USD."""
        return (
            self.input_cost + self.output_cost + self.cache_read_cost + self.cache_write_cost
        )


@dataclass
class SessionCost:
    """Cost for a session."""

    session_id: str
    project_id: str
    model: str
    agent_type: str
    start_time: datetime
    tokens: TokenUsage
    cost: CostBreakdown


@dataclass
class ProjectCostSummary:
    """Cost summary for a project."""

    project_id: str
    project_name: str
    total_cost: float
    total_tokens: int
    session_count: int
    by_model: Dict[str, float]
    by_agent: Dict[str, float]
    by_day: Dict[str, float]


class CostTracker:
    """Tracks token usage and costs for Claude API calls."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        """Initialize cost tracker.

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def calculate_cost(
        self, model: str, usage: TokenUsage
    ) -> CostBreakdown:
        """Calculate cost for token usage.

        Args:
            model: Model name (e.g., "claude-sonnet-4")
            usage: Token usage data

        Returns:
            Cost breakdown

        Raises:
            ValueError: If model pricing not found
        """
        # Normalize model name (remove version suffixes, prefixes)
        normalized_model = self._normalize_model_name(model)

        if normalized_model not in PRICING:
            raise ValueError(f"Unknown model: {model} (normalized: {normalized_model})")

        prices = PRICING[normalized_model]

        # Calculate costs (prices are per 1M tokens)
        input_cost = (usage.input_tokens / 1_000_000) * prices["input"]
        output_cost = (usage.output_tokens / 1_000_000) * prices["output"]
        cache_read_cost = (usage.cache_read_tokens / 1_000_000) * prices["cache_read"]
        cache_write_cost = (usage.cache_write_tokens / 1_000_000) * prices["cache_write"]

        return CostBreakdown(
            input_cost=input_cost,
            output_cost=output_cost,
            cache_read_cost=cache_read_cost,
            cache_write_cost=cache_write_cost,
        )

    def _normalize_model_name(self, model: str) -> str:
        """Normalize model name to match pricing keys.

        Args:
            model: Raw model name from API

        Returns:
            Normalized model name
        """
        # Remove common prefixes
        model = model.lower()
        if model.startswith("anthropic."):
            model = model[len("anthropic.") :]

        # Map full model names to pricing keys
        model_mapping = {
            "claude-sonnet-4-5-20250929": "claude-sonnet-4",
            "claude-sonnet-4": "claude-sonnet-4",
            "claude-3-5-sonnet-20241022": "claude-sonnet-3-5",
            "claude-3-5-sonnet-20240620": "claude-sonnet-3-5",
            "claude-sonnet-3-5": "claude-sonnet-3-5",
            "claude-3-opus-20240229": "claude-opus-3",
            "claude-opus-3": "claude-opus-3",
            "claude-3-5-haiku-20241022": "claude-haiku-3-5",
            "claude-haiku-3-5": "claude-haiku-3-5",
            "claude-3-haiku-20240307": "claude-haiku-3",
            "claude-haiku-3": "claude-haiku-3",
        }

        return model_mapping.get(model, model)

    def track_session(
        self,
        session_id: str,
        model: str,
        usage: TokenUsage,
    ) -> None:
        """Track token usage for a session.

        Updates the session record with token counts and cost.

        Args:
            session_id: Session ID
            model: Model name
            usage: Token usage data
        """
        cost = self.calculate_cost(model, usage)

        # Update session with token counts and cost
        self.db.update_session(
            session_id=session_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cost_usd=cost.total_cost,
        )

    def get_session_cost(self, session_id: str, use_stored_cost: bool = False) -> Optional[SessionCost]:
        """Get cost details for a session.

        Args:
            session_id: Session ID
            use_stored_cost: If True, use stored cost instead of recalculating from tokens

        Returns:
            Session cost details, or None if session not found
        """
        session = self.db.get_session(session_id)
        if not session:
            return None

        usage = TokenUsage(
            input_tokens=session.input_tokens or 0,
            output_tokens=session.output_tokens or 0,
            cache_read_tokens=session.cache_read_tokens or 0,
            cache_write_tokens=session.cache_write_tokens or 0,
        )

        # Get cost breakdown
        if use_stored_cost and session.cost > 0:
            # Use stored cost, distributed evenly across token types
            # This is a simplification - we don't know the exact breakdown
            total_cost = session.cost
            cost = CostBreakdown(
                input_cost=total_cost * 0.5,  # Rough approximation
                output_cost=total_cost * 0.5,
                cache_read_cost=0.0,
                cache_write_cost=0.0,
            )
        else:
            # Calculate from tokens
            cost = self.calculate_cost(session.current_model, usage)

        return SessionCost(
            session_id=session.id,
            project_id=session.project_id,
            model=session.current_model,
            agent_type=session.agent_type.value,
            start_time=session.started_at,
            tokens=usage,
            cost=cost,
        )

    def get_project_costs(
        self,
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_stored_cost: bool = False,
    ) -> ProjectCostSummary:
        """Get cost breakdown for a project.

        Args:
            project_id: Project ID
            start_date: Filter sessions after this date (inclusive)
            end_date: Filter sessions before this date (inclusive)
            use_stored_cost: If True, use stored cost instead of recalculating from tokens

        Returns:
            Project cost summary

        Raises:
            ValueError: If project not found
        """
        project = self.db.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        # Get all sessions for project
        sessions = self.db.list_sessions(
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
        )

        total_cost = 0.0
        total_tokens = 0
        by_model: Dict[str, float] = {}
        by_agent: Dict[str, float] = {}
        by_day: Dict[str, float] = {}

        for session in sessions:
            # Get session cost
            if use_stored_cost and session.cost > 0:
                # Use the stored cost value
                session_cost = session.cost
            else:
                # Calculate cost for this session from tokens
                usage = TokenUsage(
                    input_tokens=session.input_tokens or 0,
                    output_tokens=session.output_tokens or 0,
                    cache_read_tokens=session.cache_read_tokens or 0,
                    cache_write_tokens=session.cache_write_tokens or 0,
                )

                cost = self.calculate_cost(session.current_model, usage)
                session_cost = cost.total_cost

            # Count tokens regardless of cost calculation method
            usage = TokenUsage(
                input_tokens=session.input_tokens or 0,
                output_tokens=session.output_tokens or 0,
                cache_read_tokens=session.cache_read_tokens or 0,
                cache_write_tokens=session.cache_write_tokens or 0,
            )
            total_tokens += usage.total_tokens

            # Accumulate totals
            total_cost += session_cost

            # By model
            model = session.current_model
            by_model[model] = by_model.get(model, 0.0) + session_cost

            # By agent type
            agent = session.agent_type.value
            by_agent[agent] = by_agent.get(agent, 0.0) + session_cost

            # By day
            day = session.started_at.strftime("%Y-%m-%d")
            by_day[day] = by_day.get(day, 0.0) + session_cost

        return ProjectCostSummary(
            project_id=project.id,
            project_name=project.name,
            total_cost=total_cost,
            total_tokens=total_tokens,
            session_count=len(sessions),
            by_model=by_model,
            by_agent=by_agent,
            by_day=by_day,
        )

    def get_total_costs(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, ProjectCostSummary]:
        """Get cost breakdown for all projects.

        Args:
            start_date: Filter sessions after this date (inclusive)
            end_date: Filter sessions before this date (inclusive)

        Returns:
            Dictionary mapping project_id to cost summary
        """
        projects = self.db.list_projects()
        result = {}

        for project in projects:
            try:
                summary = self.get_project_costs(
                    project.id,
                    start_date=start_date,
                    end_date=end_date,
                )
                result[project.id] = summary
            except ValueError:
                # Project not found (should not happen, but handle gracefully)
                continue

        return result
