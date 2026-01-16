"""Tests for research agent module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from bob.models.base import Task, TaskStatus, ModelTier, FailureType
from bob.orchestrator.research_agent import (
    ResearchResult,
    ExperimentResult,
    ResearchContext,
    ResearchTracker,
    PERPLEXITY_TOOLS,
    get_perplexity_mcp_config,
    generate_research_prompt,
    generate_research_queries_from_error,
    parse_research_response,
    create_research_session_prompt,
)


class TestResearchResult:
    """Test ResearchResult dataclass."""

    def test_research_result_creation(self):
        """Test creating a research result."""
        result = ResearchResult(
            query="How to use pytest fixtures",
            findings="Use @pytest.fixture decorator",
            sources=["https://docs.pytest.org"],
            suggestions=["Use conftest.py for shared fixtures"],
            code_examples=["@pytest.fixture\ndef my_fixture():\n    return 42"],
        )
        assert result.query == "How to use pytest fixtures"
        assert result.findings == "Use @pytest.fixture decorator"
        assert result.success is True
        assert result.error is None

    def test_research_result_to_dict(self):
        """Test converting research result to dict."""
        result = ResearchResult(
            query="Test query",
            findings="Test findings",
        )
        data = result.to_dict()
        assert data["query"] == "Test query"
        assert data["findings"] == "Test findings"
        assert data["success"] is True
        assert "timestamp" in data


class TestExperimentResult:
    """Test ExperimentResult dataclass."""

    def test_experiment_result_creation(self):
        """Test creating an experiment result."""
        result = ExperimentResult(
            command="pytest tests/",
            output="5 passed",
            success=True,
        )
        assert result.command == "pytest tests/"
        assert result.output == "5 passed"
        assert result.success is True
        assert result.rollback_needed is False

    def test_experiment_result_to_dict(self):
        """Test converting experiment result to dict."""
        result = ExperimentResult(
            command="test command",
            output="test output",
            success=True,
            rollback_needed=True,
            rollback_command="undo command",
        )
        data = result.to_dict()
        assert data["command"] == "test command"
        assert data["output"] == "test output"
        assert data["success"] is True
        assert data["rollback_needed"] is True
        assert data["rollback_command"] == "undo command"


class TestResearchContext:
    """Test ResearchContext class."""

    def test_init(self):
        """Test initializing research context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ResearchContext(Path(tmpdir), "task-123")
            assert context.task_id == "task-123"
            assert context.research_history == []
            assert context.experiment_history == []

    def test_add_research(self):
        """Test adding research result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ResearchContext(Path(tmpdir), "task-123")
            result = ResearchResult(query="test", findings="test findings")
            context.add_research(result)

            assert len(context.research_history) == 1
            assert context.research_history[0].query == "test"

            # Verify persistence
            context2 = ResearchContext(Path(tmpdir), "task-123")
            assert len(context2.research_history) == 1
            assert context2.research_history[0].query == "test"

    def test_add_experiment(self):
        """Test adding experiment result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ResearchContext(Path(tmpdir), "task-123")
            result = ExperimentResult(
                command="test cmd",
                output="test output",
                success=True,
            )
            context.add_experiment(result)

            assert len(context.experiment_history) == 1
            assert context.experiment_history[0].command == "test cmd"

            # Verify persistence
            context2 = ResearchContext(Path(tmpdir), "task-123")
            assert len(context2.experiment_history) == 1

    def test_get_research_summary_empty(self):
        """Test getting summary with no research."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ResearchContext(Path(tmpdir), "task-123")
            summary = context.get_research_summary()
            assert "No research has been conducted yet" in summary

    def test_get_research_summary_with_data(self):
        """Test getting summary with research data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            context = ResearchContext(Path(tmpdir), "task-123")
            context.add_research(
                ResearchResult(
                    query="How to test?",
                    findings="Use pytest framework",
                    sources=["https://pytest.org"],
                    suggestions=["Write unit tests", "Use fixtures"],
                )
            )

            summary = context.get_research_summary()
            assert "Research Summary for Task task-123" in summary
            assert "How to test?" in summary
            assert "Use pytest framework" in summary


class TestResearchTracker:
    """Test ResearchTracker class."""

    def test_init(self):
        """Test initializing research tracker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ResearchTracker(Path(tmpdir))
            assert tracker.queries_tried == {}

    def test_record_query(self):
        """Test recording a query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ResearchTracker(Path(tmpdir))
            tracker.record_query("task-123", "How to use pytest?")

            assert "task-123" in tracker.queries_tried
            assert "How to use pytest?" in tracker.queries_tried["task-123"]

            # Verify persistence
            tracker2 = ResearchTracker(Path(tmpdir))
            assert "task-123" in tracker2.queries_tried

    def test_was_query_tried(self):
        """Test checking if query was tried."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ResearchTracker(Path(tmpdir))
            tracker.record_query("task-123", "How to use pytest?")

            assert tracker.was_query_tried("task-123", "How to use pytest?")
            assert tracker.was_query_tried("task-123", "how to use pytest?")  # Case insensitive
            assert not tracker.was_query_tried("task-123", "Different query")

    def test_get_untried_queries(self):
        """Test filtering to untried queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ResearchTracker(Path(tmpdir))
            tracker.record_query("task-123", "Query 1")
            tracker.record_query("task-123", "Query 2")

            queries = ["Query 1", "Query 2", "Query 3", "Query 4"]
            untried = tracker.get_untried_queries("task-123", queries)

            assert len(untried) == 2
            assert "Query 3" in untried
            assert "Query 4" in untried

    def test_reset_task(self):
        """Test resetting research history for a task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ResearchTracker(Path(tmpdir))
            tracker.record_query("task-123", "Query 1")
            tracker.record_query("task-123", "Query 2")

            tracker.reset_task("task-123")

            assert "task-123" not in tracker.queries_tried


class TestPerplexityTools:
    """Test Perplexity MCP integration."""

    def test_perplexity_tools_list(self):
        """Test PERPLEXITY_TOOLS constant."""
        assert isinstance(PERPLEXITY_TOOLS, list)
        assert len(PERPLEXITY_TOOLS) == 4
        assert "mcp__perplexity__perplexity_ask" in PERPLEXITY_TOOLS
        assert "mcp__perplexity__perplexity_search" in PERPLEXITY_TOOLS
        assert "mcp__perplexity__perplexity_research" in PERPLEXITY_TOOLS
        assert "mcp__perplexity__perplexity_reason" in PERPLEXITY_TOOLS

    def test_get_perplexity_mcp_config(self):
        """Test getting Perplexity MCP config."""
        config = get_perplexity_mcp_config()
        assert "perplexity" in config
        assert config["perplexity"]["command"] == "npx"
        assert "-y" in config["perplexity"]["args"]
        assert "@perplexity-ai/mcp-server" in config["perplexity"]["args"]


class TestGenerateResearchPrompt:
    """Test research prompt generation."""

    @pytest.fixture
    def sample_task(self):
        """Create a sample task."""
        return Task(
            id="task-123",
            project_id="proj-1",
            spec_id="F001",
            title="Implement authentication",
            description="Add user authentication to the application",
            steps=["Create user model", "Add login endpoint", "Add JWT support"],
            status=TaskStatus.PENDING,
        )

    def test_quick_research_prompt(self, sample_task):
        """Test generating quick research prompt."""
        queries = ["How to implement JWT?", "Best Python auth libraries"]
        error_context = "ImportError: No module named 'jwt'"

        prompt = generate_research_prompt(
            sample_task, queries, error_context, research_type="quick"
        )

        assert "Quick Investigation" in prompt
        assert sample_task.spec_id in prompt
        assert sample_task.title in prompt
        assert "How to implement JWT?" in prompt
        assert "Best Python auth libraries" in prompt
        assert "ImportError" in prompt
        assert "perplexity_search" in prompt

    def test_deep_research_prompt(self, sample_task):
        """Test generating deep research prompt."""
        queries = ["JWT best practices", "Authentication patterns"]
        error_context = "Multiple authentication failures"

        prompt = generate_research_prompt(
            sample_task, queries, error_context, research_type="deep"
        )

        assert "Deep Investigation" in prompt
        assert sample_task.spec_id in prompt
        assert sample_task.title in prompt
        assert "Create user model" in prompt  # From steps
        assert "perplexity_research" in prompt

    def test_experimental_research_prompt(self, sample_task):
        """Test generating experimental research prompt."""
        queries = ["Test JWT generation"]
        error_context = "Token validation failing"

        prompt = generate_research_prompt(
            sample_task, queries, error_context, research_type="experimental"
        )

        assert "Experimental Investigation" in prompt
        assert sample_task.spec_id in prompt
        assert "experiments subdirectory" in prompt
        assert "rollback" in prompt


class TestGenerateResearchQueries:
    """Test automatic query generation from errors."""

    def test_generate_from_import_error(self):
        """Test generating queries from ImportError."""
        error = "ImportError: No module named 'jwt'"
        queries = generate_research_queries_from_error(error)

        assert len(queries) > 0
        assert any("ImportError" in q for q in queries)
        assert any("jwt" in q for q in queries)

    def test_generate_from_attribute_error(self):
        """Test generating queries from AttributeError."""
        error = "AttributeError: 'NoneType' object has no attribute 'encode'"
        queries = generate_research_queries_from_error(error)

        assert len(queries) > 0
        assert any("AttributeError" in q for q in queries)
        assert any("encode" in q for q in queries)

    def test_generate_from_function_error(self):
        """Test generating queries from function signature error."""
        error = "TypeError: encode() takes 1 positional argument but 2 were given"
        queries = generate_research_queries_from_error(error)

        assert len(queries) > 0
        assert any("TypeError" in q for q in queries)
        assert any("encode" in q for q in queries)

    def test_generate_with_context(self):
        """Test generating queries with context."""
        error = "ImportError: No module named 'jwt'"
        queries = generate_research_queries_from_error(error, context="Django")

        assert all("Django" in q for q in queries)

    def test_generate_from_generic_error(self):
        """Test generating queries from unrecognized error."""
        error = "Some strange error occurred"
        queries = generate_research_queries_from_error(error)

        assert len(queries) > 0
        assert any("error" in q.lower() for q in queries)

    def test_limit_to_three_queries(self):
        """Test that at most 3 queries are generated."""
        error = "Complex error with multiple issues"
        queries = generate_research_queries_from_error(error)

        assert len(queries) <= 3


class TestParseResearchResponse:
    """Test parsing research responses."""

    def test_parse_with_sources(self):
        """Test parsing response with URLs."""
        response = """
        Here's what I found:
        Check out https://docs.pytest.org for documentation.
        Also see https://github.com/pytest-dev/pytest
        """
        result = parse_research_response(response)

        assert len(result.sources) == 2
        assert "https://docs.pytest.org" in result.sources
        assert "https://github.com/pytest-dev/pytest" in result.sources

    def test_parse_with_code_blocks(self):
        """Test parsing response with code blocks."""
        response = """
        Here's an example:
        ```python
        def test_example():
            assert True
        ```

        And another:
        ```python
        @pytest.fixture
        def my_fixture():
            return 42
        ```
        """
        result = parse_research_response(response)

        assert len(result.code_examples) == 2
        assert "def test_example" in result.code_examples[0]
        assert "@pytest.fixture" in result.code_examples[1]

    def test_parse_with_suggestions(self):
        """Test parsing response with bullet points."""
        response = """Recommendations:
- Use pytest fixtures for setup
- Write descriptive test names
* Keep tests isolated
"""
        result = parse_research_response(response)

        assert len(result.suggestions) >= 2
        assert any("pytest fixtures" in s for s in result.suggestions)
        assert any("test names" in s for s in result.suggestions)

    def test_parse_truncates_long_response(self):
        """Test that long responses are truncated."""
        response = "a" * 5000
        result = parse_research_response(response)

        assert len(result.findings) == 2000


class TestCreateResearchSessionPrompt:
    """Test comprehensive research session prompt generation."""

    @pytest.fixture
    def sample_task(self):
        """Create a sample task."""
        return Task(
            id="task-123",
            project_id="proj-1",
            spec_id="F001",
            title="Implement authentication",
            description="Add user authentication",
            status=TaskStatus.FAILED,
        )

    @pytest.fixture
    def classification_result(self):
        """Create a sample classification result."""
        return {
            "failure_type": "missing_info",
            "reason": "Missing JWT library documentation",
            "confidence": 0.85,
            "research_queries": [
                "How to use PyJWT library?",
                "JWT token generation best practices",
            ],
        }

    def test_create_prompt_without_previous_research(
        self, sample_task, classification_result
    ):
        """Test creating prompt without previous research."""
        prompt = create_research_session_prompt(sample_task, classification_result)

        assert "Research Session for Task F001" in prompt
        assert "Implement authentication" in prompt
        assert "missing_info" in prompt
        assert "Missing JWT library documentation" in prompt
        assert "0.85" in prompt or "85%" in prompt
        assert "How to use PyJWT library?" in prompt
        assert "perplexity_ask" in prompt
        assert "perplexity_search" in prompt
        assert "perplexity_research" in prompt

    def test_create_prompt_with_previous_research(
        self, sample_task, classification_result
    ):
        """Test creating prompt with previous research."""
        previous_research = "Previously found: JWT requires secret key"

        prompt = create_research_session_prompt(
            sample_task, classification_result, previous_research
        )

        assert "Previous Research" in prompt
        assert "Previously found: JWT requires secret key" in prompt
        assert "don't repeat queries already tried" in prompt


class TestIntegration:
    """Integration tests for research agent workflow."""

    def test_full_research_workflow(self):
        """Test complete research workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create task
            task = Task(
                id="task-123",
                project_id="proj-1",
                spec_id="F001",
                title="Implement feature",
                description="Test task",
                status=TaskStatus.FAILED,
                research_required=True,
                research_queries=["How to implement?", "Best practices?"],
            )

            # Initialize research context and tracker
            context = ResearchContext(workspace, task.id)
            tracker = ResearchTracker(workspace)

            # Generate queries from error
            error = "ImportError: No module named 'test_module'"
            queries = generate_research_queries_from_error(error)
            assert len(queries) > 0

            # Filter untried queries
            untried = tracker.get_untried_queries(task.id, queries)
            assert len(untried) == len(queries)

            # Record a query as tried
            tracker.record_query(task.id, queries[0])

            # Add research result
            result = ResearchResult(
                query=queries[0],
                findings="Found solution in documentation",
                sources=["https://docs.example.com"],
            )
            context.add_research(result)

            # Verify research was saved
            assert len(context.research_history) == 1

            # Get summary
            summary = context.get_research_summary()
            assert "task-123" in summary
            assert "Found solution" in summary

            # Verify query tracking
            untried2 = tracker.get_untried_queries(task.id, queries)
            assert len(untried2) == len(queries) - 1
