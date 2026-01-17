"""Cost tracking accuracy tests (F059).

This module provides comprehensive tests to verify that cost calculations
are accurate across all scenarios including:
- Known token usage
- Cache read discounts
- Different model pricing
- Cost aggregation by model, agent, and day
- Budget limit enforcement
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from bob.database.manager import DatabaseManager
from bob.models.base import (
    AgentType,
    Project,
    Session,
    SessionStatus,
    Task,
    TaskStatus,
)
from bob.observability.cost_tracker import CostTracker, TokenUsage, PRICING
from bob.orchestrator.engine import Orchestrator, OrchestratorConfig


@pytest.fixture
def db(tmp_path: Path):
    """Create a test database."""
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path)


@pytest.fixture
def tracker(db):
    """Create a CostTracker instance."""
    return CostTracker(db)


@pytest.fixture
def sample_project(db):
    """Create a sample project."""
    project = Project(
        id="proj-test-cost",
        name="Cost Test Project",
        description="Testing cost accuracy",
        workspace_dir="/tmp/cost-test",
        spec_source="file://spec.yaml",
    )
    db.create_project(project)
    return project


@pytest.fixture
def sample_task(db, sample_project):
    """Create a sample task."""
    task = Task(
        id="task-test-cost",
        project_id=sample_project.id,
        spec_id="F001",
        title="Test Task",
        description="Test task for cost tracking",
        status=TaskStatus.PENDING,
        depends_on=[],
    )
    db.create_task(task)
    return task


class TestKnownTokenUsage:
    """Test that known token usage produces expected costs."""

    def test_exact_cost_calculation_sonnet(self, tracker):
        """Verify exact cost calculation for Sonnet with known tokens."""
        # Known usage: 1000 input, 500 output
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

        cost = tracker.calculate_cost("claude-sonnet-4", usage)

        # Sonnet pricing: $3/MTok input, $15/MTok output
        # Input: 1000 * ($3/1M) = $0.003
        # Output: 500 * ($15/1M) = $0.0075
        # Total: $0.0105
        assert cost.input_cost == pytest.approx(0.003)
        assert cost.output_cost == pytest.approx(0.0075)
        assert cost.total_cost == pytest.approx(0.0105)

    def test_exact_cost_calculation_with_cache(self, tracker):
        """Verify exact cost with cache tokens."""
        # Known usage with cache
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=5000,  # 5k from cache
            cache_write_tokens=200,  # 200 cache write
        )

        cost = tracker.calculate_cost("claude-sonnet-4", usage)

        # Sonnet pricing:
        # Input: 1000 * ($3/1M) = $0.003
        # Output: 500 * ($15/1M) = $0.0075
        # Cache read: 5000 * ($0.30/1M) = $0.0015  # 90% discount
        # Cache write: 200 * ($3.75/1M) = $0.00075  # 25% surcharge
        # Total: $0.01275
        assert cost.input_cost == pytest.approx(0.003)
        assert cost.output_cost == pytest.approx(0.0075)
        assert cost.cache_read_cost == pytest.approx(0.0015)
        assert cost.cache_write_cost == pytest.approx(0.00075)
        assert cost.total_cost == pytest.approx(0.01275)


class TestCacheReadDiscount:
    """Test that cache reads have 90% discount."""

    def test_cache_read_significant_discount(self, tracker):
        """Verify cache reads are significantly cheaper than regular input."""
        for model in PRICING.keys():
            prices = PRICING[model]
            # Cache read should be at least 80% cheaper than input
            # (typically 90% but some models may vary slightly)
            discount = 1 - (prices["cache_read"] / prices["input"])
            assert discount >= 0.80, \
                f"{model}: cache_read discount too small ({discount*100:.1f}%)"
            # Cache read should always be cheaper than input
            assert prices["cache_read"] < prices["input"], \
                f"{model}: cache_read should be cheaper than input"

    def test_cache_read_vs_input_cost(self, tracker):
        """Verify actual cost savings from cache."""
        # Same tokens, with and without cache
        usage_no_cache = TokenUsage(input_tokens=10000, output_tokens=0)
        usage_with_cache = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=10000
        )

        cost_no_cache = tracker.calculate_cost("claude-sonnet-4", usage_no_cache)
        cost_with_cache = tracker.calculate_cost("claude-sonnet-4", usage_with_cache)

        # Cache should cost 10% of regular input for Sonnet (90% discount)
        assert cost_with_cache.total_cost == pytest.approx(
            cost_no_cache.total_cost * 0.1
        )

        # Verify significant savings
        assert cost_with_cache.total_cost < cost_no_cache.total_cost


class TestDifferentModelPricing:
    """Test that different models have correct pricing."""

    def test_all_models_have_pricing(self, tracker):
        """Verify all supported models have pricing data."""
        expected_models = [
            "claude-sonnet-4",
            "claude-sonnet-3-5",
            "claude-opus-3",
            "claude-haiku-3-5",
            "claude-haiku-3",
        ]
        for model in expected_models:
            assert model in PRICING, f"Missing pricing for {model}"

    def test_model_price_relationships(self, tracker):
        """Verify price relationships between models."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)

        sonnet_cost = tracker.calculate_cost("claude-sonnet-4", usage)
        opus_cost = tracker.calculate_cost("claude-opus-3", usage)
        haiku_cost = tracker.calculate_cost("claude-haiku-3-5", usage)

        # Opus should be most expensive
        assert opus_cost.total_cost > sonnet_cost.total_cost
        # Haiku should be cheapest
        assert haiku_cost.total_cost < sonnet_cost.total_cost
        assert haiku_cost.total_cost < opus_cost.total_cost

    def test_sonnet_4_vs_sonnet_3_5(self, tracker):
        """Verify Sonnet 4 and 3.5 pricing."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)

        sonnet_4_cost = tracker.calculate_cost("claude-sonnet-4", usage)
        sonnet_3_5_cost = tracker.calculate_cost("claude-sonnet-3-5", usage)

        # Both should have valid costs
        assert sonnet_4_cost.total_cost > 0
        assert sonnet_3_5_cost.total_cost > 0


class TestCostAggregation:
    """Test cost aggregation by model, agent, and day."""

    def test_aggregation_by_model(self, db, tracker, sample_project, sample_task):
        """Verify costs are correctly aggregated by model."""
        # Create sessions with different models
        sessions_data = [
            ("sess-1", "claude-sonnet-4", 1000, 500),
            ("sess-2", "claude-sonnet-4", 2000, 1000),
            ("sess-3", "claude-haiku-3-5", 1000, 500),
        ]

        for sess_id, model, input_tok, output_tok in sessions_data:
            session = Session(
                id=sess_id,
                project_id=sample_project.id,
                task_id=sample_task.id,
                agent_type=AgentType.CODING,
                model=model,
                status=SessionStatus.COMPLETED,
                input_tokens=input_tok,
                output_tokens=output_tok,
            )
            db.create_session(session)

        # Get project costs
        project_costs = tracker.get_project_costs(sample_project.id)

        # Verify aggregation by model
        assert "claude-sonnet-4" in project_costs.by_model
        assert "claude-haiku-3-5" in project_costs.by_model

        # Sonnet sessions should have combined cost
        sonnet_cost = project_costs.by_model["claude-sonnet-4"]
        haiku_cost = project_costs.by_model["claude-haiku-3-5"]

        # Sonnet had 2 sessions, haiku had 1
        assert sonnet_cost > haiku_cost

    def test_aggregation_by_agent(self, db, tracker, sample_project, sample_task):
        """Verify costs are correctly aggregated by agent type."""
        # Create sessions with different agent types
        sessions_data = [
            ("sess-1", AgentType.CODING, 1000, 500),
            ("sess-2", AgentType.CODING, 2000, 1000),
            ("sess-3", AgentType.RESEARCH, 1000, 500),
        ]

        for sess_id, agent_type, input_tok, output_tok in sessions_data:
            session = Session(
                id=sess_id,
                project_id=sample_project.id,
                task_id=sample_task.id,
                agent_type=agent_type,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                input_tokens=input_tok,
                output_tokens=output_tok,
            )
            db.create_session(session)

        # Get project costs
        project_costs = tracker.get_project_costs(sample_project.id)

        # Verify aggregation by agent
        assert "coding" in project_costs.by_agent
        assert "research" in project_costs.by_agent

        # Coding had 2 sessions, research had 1
        coding_cost = project_costs.by_agent["coding"]
        research_cost = project_costs.by_agent["research"]

        assert coding_cost > research_cost

    def test_aggregation_by_day(self, db, tracker, sample_project, sample_task):
        """Verify costs are correctly aggregated by day."""
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        # Create sessions on different days
        session1 = Session(
            id="sess-today",
            project_id=sample_project.id,
            task_id=sample_task.id,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            status=SessionStatus.COMPLETED,
            input_tokens=1000,
            output_tokens=500,
            started_at=now,
        )
        db.create_session(session1)

        session2 = Session(
            id="sess-yesterday",
            project_id=sample_project.id,
            task_id=sample_task.id,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            status=SessionStatus.COMPLETED,
            input_tokens=1000,
            output_tokens=500,
            started_at=yesterday,
        )
        db.create_session(session2)

        # Get project costs
        project_costs = tracker.get_project_costs(sample_project.id)

        # Verify we have costs for both days
        assert len(project_costs.by_day) == 2

        today_key = now.strftime("%Y-%m-%d")
        yesterday_key = yesterday.strftime("%Y-%m-%d")

        assert today_key in project_costs.by_day
        assert yesterday_key in project_costs.by_day

        # Both days should have equal costs (same usage)
        assert project_costs.by_day[today_key] == pytest.approx(
            project_costs.by_day[yesterday_key]
        )


class TestBudgetLimitEnforcement:
    """Test that budget limits are enforced correctly.

    Note: Full budget limit enforcement is tested in test_orchestrator.py.
    These tests verify the cost tracking calculations that underpin limit enforcement.
    """

    def test_high_cost_session_exceeds_low_limit(self, db, tracker, sample_project, sample_task):
        """Verify that high-cost sessions can exceed budget limits."""
        # Create an expensive session
        session = Session(
            id="sess-expensive",
            project_id=sample_project.id,
            task_id=sample_task.id,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            status=SessionStatus.COMPLETED,
            input_tokens=10_000_000,  # 10M tokens
            output_tokens=5_000_000,  # 5M tokens
        )
        db.create_session(session)

        # Calculate costs
        project_costs = tracker.get_project_costs(sample_project.id)

        # This session should cost significantly more than a low limit (e.g., $0.01)
        # Sonnet: 10M input * $3/MTok + 5M output * $15/MTok = $30 + $75 = $105
        low_limit = 0.01
        assert project_costs.total_cost > low_limit, \
            f"Session cost ${project_costs.total_cost:.2f} should exceed ${low_limit}"

    def test_cheap_session_under_high_limit(self, db, tracker, sample_project, sample_task):
        """Verify that cheap sessions stay under generous limits."""
        # Create a cheap session
        session = Session(
            id="sess-cheap",
            project_id=sample_project.id,
            task_id=sample_task.id,
            agent_type=AgentType.CODING,
            model="claude-haiku-3-5",  # Cheaper model
            status=SessionStatus.COMPLETED,
            input_tokens=1000,
            output_tokens=500,
        )
        db.create_session(session)

        # Calculate costs
        project_costs = tracker.get_project_costs(sample_project.id)
        session_cost = tracker.get_session_cost(session.id)

        # This session should cost less than a high limit (e.g., $100)
        high_limit = 100.0
        assert project_costs.total_cost < high_limit, \
            f"Project cost ${project_costs.total_cost:.2f} should be under ${high_limit}"
        assert session_cost.cost.total_cost < high_limit, \
            f"Session cost ${session_cost.cost.total_cost:.2f} should be under ${high_limit}"

    def test_cost_accumulation_for_limit_checking(self, db, tracker, sample_project, sample_task):
        """Verify that costs accumulate correctly for limit checking."""
        # Create multiple sessions
        sessions = []
        for i in range(3):
            session = Session(
                id=f"sess-{i}",
                project_id=sample_project.id,
                task_id=sample_task.id,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                input_tokens=100_000,  # 100k tokens each
                output_tokens=50_000,  # 50k tokens each
            )
            db.create_session(session)
            sessions.append(session)

        # Calculate total project costs
        project_costs = tracker.get_project_costs(sample_project.id)

        # Each session: 0.1M * $3 + 0.05M * $15 = $0.30 + $0.75 = $1.05
        # Total: 3 * $1.05 = $3.15
        expected_total = 3.15
        assert project_costs.total_cost == pytest.approx(expected_total, rel=0.01), \
            f"Total cost ${project_costs.total_cost:.2f} should be ~${expected_total}"

        # Verify a limit of $2.00 would be exceeded
        limit_2_dollars = 2.00
        assert project_costs.total_cost > limit_2_dollars, \
            f"Accumulated cost should exceed ${limit_2_dollars} limit"

        # Verify a limit of $10.00 would not be exceeded
        limit_10_dollars = 10.00
        assert project_costs.total_cost < limit_10_dollars, \
            f"Accumulated cost should be under ${limit_10_dollars} limit"
