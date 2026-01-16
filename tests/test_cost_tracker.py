"""Tests for CostTracker."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from bob.database.manager import DatabaseManager
from bob.models.base import AgentType, Project, Session, SessionStatus
from bob.observability.cost_tracker import (
    CostTracker,
    TokenUsage,
    CostBreakdown,
    PRICING,
)


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
        id="proj-1",
        name="Test Project",
        description="Test",
        workspace_dir="/tmp/test",
        spec_source="file://spec.yaml",
    )
    db.create_project(project)
    return project


class TestTokenUsage:
    """Test TokenUsage dataclass."""

    def test_total_tokens(self):
        """Test total_tokens property."""
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=2000,
            cache_write_tokens=100,
        )
        assert usage.total_tokens == 3600


class TestCostBreakdown:
    """Test CostBreakdown dataclass."""

    def test_total_cost(self):
        """Test total_cost property."""
        breakdown = CostBreakdown(
            input_cost=0.003,
            output_cost=0.0075,
            cache_read_cost=0.0006,
            cache_write_cost=0.000375,
        )
        assert breakdown.total_cost == pytest.approx(0.011475)


class TestPricingData:
    """Test that pricing data is correct."""

    def test_pricing_has_all_models(self):
        """Test that pricing includes all models."""
        expected_models = [
            "claude-sonnet-4",
            "claude-sonnet-3-5",
            "claude-opus-3",
            "claude-haiku-3-5",
            "claude-haiku-3",
        ]
        for model in expected_models:
            assert model in PRICING, f"Missing pricing for {model}"

    def test_pricing_has_all_fields(self):
        """Test that each model has all required pricing fields."""
        required_fields = ["input", "output", "cache_read", "cache_write"]
        for model, prices in PRICING.items():
            for field in required_fields:
                assert field in prices, f"Missing {field} for {model}"

    def test_cache_discount(self):
        """Test that cache reads are cheaper than regular inputs."""
        for model, prices in PRICING.items():
            assert prices["cache_read"] < prices["input"], \
                f"{model}: cache_read should be cheaper than input"
            # Cache read should be ~90% cheaper (10% of input cost)
            expected_cache = prices["input"] * 0.1
            assert abs(prices["cache_read"] - expected_cache) < 0.01, \
                f"{model}: cache_read should be ~90% cheaper"


class TestModelNameNormalization:
    """Test model name normalization."""

    def test_normalize_sonnet_4(self, tracker):
        """Test normalizing Sonnet 4 variants."""
        test_cases = [
            "claude-sonnet-4",
            "claude-sonnet-4-5-20250929",
            "anthropic.claude-sonnet-4",
        ]
        for model in test_cases:
            normalized = tracker._normalize_model_name(model)
            assert normalized == "claude-sonnet-4"

    def test_normalize_sonnet_35(self, tracker):
        """Test normalizing Sonnet 3.5 variants."""
        test_cases = [
            "claude-sonnet-3-5",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20240620",
        ]
        for model in test_cases:
            normalized = tracker._normalize_model_name(model)
            assert normalized == "claude-sonnet-3-5"

    def test_normalize_opus(self, tracker):
        """Test normalizing Opus variants."""
        test_cases = [
            "claude-opus-3",
            "claude-3-opus-20240229",
        ]
        for model in test_cases:
            normalized = tracker._normalize_model_name(model)
            assert normalized == "claude-opus-3"

    def test_normalize_haiku(self, tracker):
        """Test normalizing Haiku variants."""
        test_cases = [
            ("claude-haiku-3-5", "claude-haiku-3-5"),
            ("claude-3-5-haiku-20241022", "claude-haiku-3-5"),
            ("claude-haiku-3", "claude-haiku-3"),
            ("claude-3-haiku-20240307", "claude-haiku-3"),
        ]
        for model, expected in test_cases:
            normalized = tracker._normalize_model_name(model)
            assert normalized == expected


class TestCostCalculation:
    """Test cost calculation."""

    def test_calculate_sonnet_cost(self, tracker):
        """Test calculating cost for Sonnet."""
        usage = TokenUsage(
            input_tokens=1_000_000,  # 1M tokens
            output_tokens=500_000,   # 500k tokens
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

        cost = tracker.calculate_cost("claude-sonnet-4", usage)

        # Input: 1M * $3.00 = $3.00
        # Output: 0.5M * $15.00 = $7.50
        assert cost.input_cost == pytest.approx(3.00)
        assert cost.output_cost == pytest.approx(7.50)
        assert cost.cache_read_cost == 0.0
        assert cost.cache_write_cost == 0.0
        assert cost.total_cost == pytest.approx(10.50)

    def test_calculate_with_cache(self, tracker):
        """Test calculating cost with cache tokens."""
        usage = TokenUsage(
            input_tokens=100_000,
            output_tokens=50_000,
            cache_read_tokens=900_000,   # 900k from cache
            cache_write_tokens=100_000,  # 100k cache write
        )

        cost = tracker.calculate_cost("claude-sonnet-4", usage)

        # Input: 0.1M * $3.00 = $0.30
        # Output: 0.05M * $15.00 = $0.75
        # Cache read: 0.9M * $0.30 = $0.27 (90% discount)
        # Cache write: 0.1M * $3.75 = $0.375 (25% surcharge)
        assert cost.input_cost == pytest.approx(0.30)
        assert cost.output_cost == pytest.approx(0.75)
        assert cost.cache_read_cost == pytest.approx(0.27)
        assert cost.cache_write_cost == pytest.approx(0.375)
        assert cost.total_cost == pytest.approx(1.695)

    def test_calculate_opus_cost(self, tracker):
        """Test that Opus is more expensive than Sonnet."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)

        sonnet_cost = tracker.calculate_cost("claude-sonnet-4", usage)
        opus_cost = tracker.calculate_cost("claude-opus-3", usage)

        assert opus_cost.total_cost > sonnet_cost.total_cost

    def test_calculate_haiku_cost(self, tracker):
        """Test that Haiku is cheaper than Sonnet."""
        usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)

        sonnet_cost = tracker.calculate_cost("claude-sonnet-4", usage)
        haiku_cost = tracker.calculate_cost("claude-haiku-3-5", usage)

        assert haiku_cost.total_cost < sonnet_cost.total_cost

    def test_calculate_unknown_model(self, tracker):
        """Test that unknown models raise ValueError."""
        usage = TokenUsage(input_tokens=1000, output_tokens=500)

        with pytest.raises(ValueError, match="Unknown model"):
            tracker.calculate_cost("claude-unknown-model", usage)


class TestTrackSession:
    """Test session tracking."""

    
    def test_track_session(self, tracker, sample_project):
        """Test tracking a session."""
        # Create a session
        session = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
        )
        tracker.db.create_session(session)

        # Track usage
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            cache_read_tokens=2000,
            cache_write_tokens=100,
        )

        tracker.track_session("sess-1", "claude-sonnet-4", usage)

        # Verify session was updated
        updated = tracker.db.get_session("sess-1")
        assert updated.input_tokens == 1000
        assert updated.output_tokens == 500
        assert updated.cache_read_tokens == 2000
        assert updated.cache_write_tokens == 100
        assert updated.cost > 0.0


class TestGetSessionCost:
    """Test getting session cost details."""

    
    def test_get_session_cost(self, tracker, sample_project):
        """Test getting cost for a session."""
        # Create session with token usage
        session = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            input_tokens=1000,
            output_tokens=500,
        )
        tracker.db.create_session(session)

        # Get cost
        session_cost = tracker.get_session_cost("sess-1")

        assert session_cost is not None
        assert session_cost.session_id == "sess-1"
        assert session_cost.project_id == "proj-1"
        assert session_cost.model == "claude-sonnet-4"
        assert session_cost.tokens.input_tokens == 1000
        assert session_cost.tokens.output_tokens == 500
        assert session_cost.cost.total_cost > 0.0

    
    def test_get_session_cost_not_found(self, tracker):
        """Test getting cost for non-existent session."""
        session_cost = tracker.get_session_cost("nonexistent")
        assert session_cost is None


class TestGetProjectCosts:
    """Test getting project cost summary."""

    
    def test_get_project_costs_empty(self, tracker, sample_project):
        """Test getting costs for project with no sessions."""
        summary = tracker.get_project_costs("proj-1")

        assert summary.project_id == "proj-1"
        assert summary.project_name == "Test Project"
        assert summary.total_cost == 0.0
        assert summary.total_tokens == 0
        assert summary.session_count == 0
        assert summary.by_model == {}
        assert summary.by_agent == {}
        assert summary.by_day == {}

    
    def test_get_project_costs_with_sessions(self, tracker, sample_project):
        """Test getting costs for project with sessions."""
        now = datetime.now()

        # Create sessions
        session1 = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            started_at=now,
            input_tokens=1_000_000,
            output_tokens=500_000,
        )
        session2 = Session(
            id="sess-2",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.RESEARCH,
            model="claude-haiku-3-5",
            started_at=now,
            input_tokens=500_000,
            output_tokens=250_000,
        )
        tracker.db.create_session(session1)
        tracker.db.create_session(session2)

        # Get costs
        summary = tracker.get_project_costs("proj-1")

        assert summary.project_id == "proj-1"
        assert summary.total_cost > 0.0
        assert summary.total_tokens == 2_250_000
        assert summary.session_count == 2
        assert "claude-sonnet-4" in summary.by_model
        assert "claude-haiku-3-5" in summary.by_model
        assert "coding" in summary.by_agent
        assert "research" in summary.by_agent
        assert len(summary.by_day) == 1  # All sessions same day

    
    def test_get_project_costs_date_filter(self, tracker, sample_project):
        """Test filtering costs by date."""
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        # Create sessions on different days
        session1 = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            started_at=yesterday,
            input_tokens=1_000_000,
            output_tokens=500_000,
        )
        session2 = Session(
            id="sess-2",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            started_at=now,
            input_tokens=500_000,
            output_tokens=250_000,
        )
        tracker.db.create_session(session1)
        tracker.db.create_session(session2)

        # Get costs for today only
        summary = tracker.get_project_costs(
            "proj-1",
            start_date=now.replace(hour=0, minute=0, second=0, microsecond=0),
            end_date=now.replace(hour=23, minute=59, second=59, microsecond=999999),
        )

        assert summary.session_count == 1
        assert summary.total_tokens == 750_000

    
    def test_get_project_costs_not_found(self, tracker):
        """Test getting costs for non-existent project."""
        with pytest.raises(ValueError, match="Project not found"):
            tracker.get_project_costs("nonexistent")


class TestGetTotalCosts:
    """Test getting costs for all projects."""

    
    def test_get_total_costs_multiple_projects(self, tracker, db):
        """Test getting costs for multiple projects."""
        # Create projects
        project1 = Project(
            id="proj-1",
            name="Project 1",
            description="Test",
            workspace_dir="/tmp/test1",
            spec_source="file://spec1.yaml",
        )
        project2 = Project(
            id="proj-2",
            name="Project 2",
            description="Test",
            workspace_dir="/tmp/test2",
            spec_source="file://spec2.yaml",
        )
        db.create_project(project1)
        db.create_project(project2)

        # Create sessions
        session1 = Session(
            id="sess-1",
            project_id="proj-1",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-sonnet-4",
            input_tokens=1_000_000,
            output_tokens=500_000,
        )
        session2 = Session(
            id="sess-2",
            project_id="proj-2",
            task_id=None,
            agent_type=AgentType.CODING,
            model="claude-haiku-3-5",
            input_tokens=500_000,
            output_tokens=250_000,
        )
        db.create_session(session1)
        db.create_session(session2)

        # Get total costs
        summaries = tracker.get_total_costs()

        assert len(summaries) == 2
        assert "proj-1" in summaries
        assert "proj-2" in summaries
        assert summaries["proj-1"].session_count == 1
        assert summaries["proj-2"].session_count == 1

    
    def test_get_total_costs_empty(self, tracker):
        """Test getting costs when no projects exist."""
        summaries = tracker.get_total_costs()
        assert summaries == {}
