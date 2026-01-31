"""Tests for research controller module."""

import os
import tempfile
from pathlib import Path

import pytest

from bob.database.manager import DatabaseManager
from bob.models.base import Task, TaskStatus, ProjectStatus, Project
from bob.orchestrator.research_controller import ResearchController


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(str(db_path))

        # Create a test project
        project = Project(
            id="proj-test-1",
            name="test-project",
            description="Test project",
            workspace_dir=tmpdir,
            spec_source="file://test.yaml",
        )
        project_id = db.create_project(project)

        yield db, project_id, tmpdir


@pytest.fixture
def sample_task(temp_db):
    """Create a sample task for testing."""
    db, project_id, tmpdir = temp_db

    task = Task(
        id="task-test-1",
        project_id=project_id,
        spec_id="F001",
        title="Test Task",
        description="A test task",
        steps=["Step 1", "Step 2"],
        research_required=True,
        research_queries=["How to implement feature X?", "Best practices for Y"],
    )
    task_id = db.create_task(task)

    task = db.get_task(task_id)
    return db, task, tmpdir


class TestResearchControllerInit:
    """Test ResearchController initialization."""

    def test_init_with_perplexity(self, temp_db):
        """Test initializing with Perplexity available."""
        db, project_id, tmpdir = temp_db

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=True,
        )

        assert controller.db_manager == db
        assert controller.workspace_dir == Path(tmpdir)
        assert controller.research_tracker is not None

    def test_init_without_perplexity(self, temp_db):
        """Test initializing without Perplexity."""
        db, project_id, tmpdir = temp_db

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=False,
        )

        assert controller.perplexity_available is False

    def test_init_checks_api_key(self, temp_db, monkeypatch):
        """Test that init checks for PERPLEXITY_API_KEY."""
        db, project_id, tmpdir = temp_db

        # Remove API key
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=True,
        )

        # Should set perplexity_available to False if no API key
        assert controller.perplexity_available is False


class TestShouldResearch:
    """Test should_research method."""

    def test_should_research_true(self, sample_task):
        """Test should_research returns True when research needed."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        assert controller.should_research(task) is True

    def test_should_research_false_already_complete(self, sample_task):
        """Test should_research returns False when already complete."""
        db, task, tmpdir = sample_task

        # Mark research complete
        task.research_complete = True

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        assert controller.should_research(task) is False

    def test_should_research_false_not_required(self, sample_task):
        """Test should_research returns False when not required."""
        db, task, tmpdir = sample_task

        # Mark research not required
        task.research_required = False

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        assert controller.should_research(task) is False

    def test_should_research_false_no_queries(self, sample_task):
        """Test should_research returns False with no queries."""
        db, task, tmpdir = sample_task

        # Clear queries
        task.research_queries = []

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        assert controller.should_research(task) is False


class TestRunResearch:
    """Test run_research method."""

    def test_run_research_success(self, sample_task):
        """Test running research successfully."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=True,
        )

        result = controller.run_research(task)

        assert result is True

        # Verify task updated
        updated_task = db.get_task(task.id)
        assert updated_task.research_complete is True
        assert updated_task.research_findings is not None
        assert len(updated_task.research_findings) > 0

    def test_run_research_false_when_not_needed(self, sample_task):
        """Test run_research returns False when not needed."""
        db, task, tmpdir = sample_task

        # Mark research complete
        task.research_complete = True

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        result = controller.run_research(task)

        assert result is False

    def test_run_research_limits_queries(self, sample_task):
        """Test run_research respects max_queries limit."""
        db, task, tmpdir = sample_task

        # Add many queries
        task.research_queries = [f"Query {i}" for i in range(10)]

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        result = controller.run_research(task, max_queries=2)

        assert result is True

        # Should only research 2 queries
        updated_task = db.get_task(task.id)
        assert len(updated_task.research_findings) == 2

    def test_run_research_skips_tried_queries(self, sample_task):
        """Test run_research skips already-tried queries."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Mark first query as tried
        controller.research_tracker.record_query(task.id, task.research_queries[0])

        result = controller.run_research(task, max_queries=5)

        assert result is True

        # Should skip the first query
        updated_task = db.get_task(task.id)
        assert task.research_queries[0] not in updated_task.research_findings

    def test_run_research_all_queries_tried(self, sample_task):
        """Test run_research when all queries already tried."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Mark all queries as tried
        for query in task.research_queries:
            controller.research_tracker.record_query(task.id, query)

        result = controller.run_research(task)

        assert result is True

        # Should mark complete
        updated_task = db.get_task(task.id)
        assert updated_task.research_complete is True

    def test_run_research_without_perplexity(self, sample_task):
        """Test run_research without Perplexity available."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=False,
        )

        result = controller.run_research(task)

        assert result is True

        # Should still create findings (with error message)
        updated_task = db.get_task(task.id)
        assert updated_task.research_complete is True
        assert updated_task.research_findings is not None


class TestGetImplementationContext:
    """Test get_implementation_context method."""

    def test_get_context_with_research(self, sample_task):
        """Test getting context with research findings."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Run research first
        controller.run_research(task)

        # Get context
        updated_task = db.get_task(task.id)
        context = controller.get_implementation_context(updated_task)

        assert "Research Findings" in context
        assert len(context) > 0

    def test_get_context_without_research(self, sample_task):
        """Test getting context without research."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Don't run research
        context = controller.get_implementation_context(task)

        assert context == ""

    def test_get_context_includes_sources(self, sample_task):
        """Test context includes sources."""
        db, task, tmpdir = sample_task

        # Manually set findings with sources
        task.research_complete = True
        task.research_findings = {
            "Test query": {
                "findings": "Test findings",
                "sources": ["https://example.com"],
                "suggestions": ["Do this"],
                "code_examples": ["code here"],
                "success": True,
            }
        }

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        context = controller.get_implementation_context(task)

        assert "Test query" in context
        assert "Test findings" in context
        assert "https://example.com" in context
        assert "Do this" in context


class TestResetResearch:
    """Test reset_research method."""

    def test_reset_research(self, sample_task):
        """Test resetting research state."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Run research first
        controller.run_research(task)

        # Verify research was done
        updated_task = db.get_task(task.id)
        assert updated_task.research_complete is True

        # Reset
        controller.reset_research(updated_task)

        # Verify reset
        reset_task = db.get_task(task.id)
        assert reset_task.research_complete is False
        assert reset_task.research_findings == {}


class TestGetResearchSummary:
    """Test get_research_summary method."""

    def test_get_summary_with_research(self, sample_task):
        """Test getting summary with research."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Run research
        controller.run_research(task)

        # Get summary
        summary = controller.get_research_summary(task)

        assert "Research Summary" in summary

    def test_get_summary_without_research(self, sample_task):
        """Test getting summary without research."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Don't run research
        summary = controller.get_research_summary(task)

        assert "No research has been conducted yet" in summary


class TestHasPerplexityAvailable:
    """Test has_perplexity_available method."""

    def test_has_perplexity_with_key(self, temp_db, monkeypatch):
        """Test with API key present."""
        db, project_id, tmpdir = temp_db

        # Set API key
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=True,
        )

        assert controller.has_perplexity_available() is True

    def test_has_perplexity_without_key(self, temp_db, monkeypatch):
        """Test without API key."""
        db, project_id, tmpdir = temp_db

        # Remove API key
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=True,
        )

        assert controller.has_perplexity_available() is False

    def test_has_perplexity_disabled(self, temp_db, monkeypatch):
        """Test when Perplexity is disabled."""
        db, project_id, tmpdir = temp_db

        # Set API key but disable Perplexity
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
            perplexity_available=False,
        )

        assert controller.has_perplexity_available() is False


class TestExecuteResearch:
    """Test execute_research method with Claude SDK."""

    @pytest.mark.asyncio
    async def test_execute_research_basic(self, sample_task):
        """Test basic execute_research functionality."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Mock the SDK execution to avoid actual API calls in tests
        import asyncio
        from unittest.mock import AsyncMock, patch

        mock_result = type('MockResult', (), {
            'success': True,
            'output': '''# Research Results

## Codebase Findings
Found similar patterns in auth.py module.

## Error Analysis  
The main issue is missing JWT validation.

## Implementation Recommendations
1. Use PyJWT library for token validation
2. Add middleware for authentication checks
3. Implement proper error handling

## Key References
- auth.py: line 45 for token validation
- middleware.py: authentication patterns
''',
            'error': None
        })()

        with patch('bob.orchestrator.claude_sdk_executor.execute_task_with_sdk', 
                  new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            
            result = await controller.execute_research(task)

        assert result is True

        # Verify task updated
        updated_task = db.get_task(task.id)
        assert updated_task.research_complete is True
        assert updated_task.research_findings is not None
        assert "research_conducted" in updated_task.research_findings
        assert updated_task.research_findings["research_conducted"] is True

    @pytest.mark.asyncio
    async def test_execute_research_with_error_history(self, sample_task):
        """Test execute_research with error history."""
        db, task, tmpdir = sample_task

        # Add error history to task
        error_history = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "model": "claude-sonnet-4",
                "error_msg": "JWT token validation failed",
                "attempt": 1,
            },
            {
                "timestamp": "2024-01-01T11:00:00", 
                "model": "claude-sonnet-4",
                "error_msg": "Authentication middleware not found",
                "attempt": 2,
            }
        ]
        
        task.research_findings = {"error_history": error_history}
        
        # Import FailureType enum
        from bob.models.base import FailureType
        task.failure_type = FailureType.MISSING_INFO
        
        db.update_task(
            task.id,
            research_findings={"error_history": error_history},
            failure_type=FailureType.MISSING_INFO
        )

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Check that the research prompt includes error history
        prompt = controller._build_research_prompt(task)
        
        assert "Error History" in prompt
        assert "JWT token validation failed" in prompt
        assert "Authentication middleware not found" in prompt
        assert "**Failure Type:** missing_info" in prompt

    @pytest.mark.asyncio
    async def test_execute_research_failure(self, sample_task):
        """Test execute_research handles failures gracefully."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        from unittest.mock import AsyncMock, patch

        # Mock SDK execution to fail
        mock_result = type('MockResult', (), {
            'success': False,
            'output': '',
            'error': 'Connection timeout'
        })()

        with patch('bob.orchestrator.claude_sdk_executor.execute_task_with_sdk',
                  new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            
            result = await controller.execute_research(task)

        assert result is False

        # Verify error recorded
        updated_task = db.get_task(task.id)
        assert updated_task.research_findings is not None
        assert "error" in updated_task.research_findings
        assert updated_task.research_findings["error"] == "Research execution failed"

    @pytest.mark.asyncio
    async def test_execute_research_no_sdk(self, sample_task):
        """Test execute_research falls back when SDK not available."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        from unittest.mock import patch

        # Mock SDK import to fail
        with patch.dict('sys.modules', {'bob.orchestrator.claude_sdk_executor': None}):
            with patch.object(controller, 'run_research', return_value=True) as mock_run:
                result = await controller.execute_research(task)

        assert result is True
        mock_run.assert_called_once_with(task)

    def test_build_research_prompt_comprehensive(self, sample_task):
        """Test research prompt building with all elements."""
        db, task, tmpdir = sample_task
        
        # Set up task with comprehensive data
        task.acceptance_criteria = ["Must authenticate users", "Must handle errors"]
        task.steps = ["Implement JWT", "Add middleware", "Test auth"]
        
        # Import FailureType enum
        from bob.models.base import FailureType
        task.failure_type = FailureType.MISSING_INFO
        task.research_queries = ["How to implement JWT?", "Best auth middleware?"]
        
        error_history = [
            {
                "timestamp": "2024-01-01T10:00:00",
                "model": "claude-sonnet-4",
                "error_msg": "ImportError: No module named 'jwt'",
                "attempt": 1,
            }
        ]
        task.research_findings = {"error_history": error_history}

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        prompt = controller._build_research_prompt(task)

        # Verify all sections are included
        assert "# Research Task" in prompt
        assert "Test Task" in prompt  # Title
        assert "Acceptance Criteria" in prompt
        assert "Must authenticate users" in prompt
        assert "Implementation Steps" in prompt
        assert "Implement JWT" in prompt
        assert "Error History" in prompt
        assert "ImportError: No module named 'jwt'" in prompt
        assert "Failure Classification" in prompt
        assert "missing_info" in prompt
        assert "Specific Research Queries" in prompt
        assert "How to implement JWT?" in prompt
        assert "Research Instructions" in prompt
        assert "Codebase Analysis" in prompt
        assert "Expected Output Format" in prompt

    def test_parse_research_output(self, sample_task):
        """Test parsing of research output from Claude."""
        db, task, tmpdir = sample_task

        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Sample research output from Claude
        output = """# Research Results

## Codebase Findings
Found existing auth patterns in the codebase:
- user.py has basic user model
- auth.py contains placeholder for JWT validation

## Documentation Insights  
JWT library documentation shows best practices:
- Use RS256 algorithm for production
- Set proper expiration times

## Error Analysis
The main error "ImportError: No module named 'jwt'" indicates:
- Missing PyJWT dependency in requirements
- Need to install and configure JWT library

## Implementation Recommendations
1. Add PyJWT to requirements.txt
2. Create JWT validation function in auth.py
3. Add authentication middleware to app.py
4. Implement proper error handling

## Key References
- auth.py: Line 45 (JWT validation placeholder)
- requirements.txt: Add PyJWT dependency
- user.py: User model for JWT payload
"""

        findings = controller._parse_research_output(output, task)

        assert findings["research_conducted"] is True
        assert "codebase_findings" in findings
        assert "user.py has basic user model" in findings["codebase_findings"]
        assert "error_analysis" in findings
        assert "ImportError: No module named 'jwt'" in findings["error_analysis"]
        assert "implementation_recommendations" in findings
        assert "Add PyJWT to requirements.txt" in findings["implementation_recommendations"]
        assert len(findings["suggestions"]) > 0
        assert "Add PyJWT to requirements.txt" in findings["suggestions"]


class TestIntegration:
    """Integration tests for research workflow."""

    def test_full_research_workflow(self, temp_db):
        """Test complete research workflow."""
        db, project_id, tmpdir = temp_db

        # Create task with research required
        task = Task(
            id="task-integration-1",
            project_id=project_id,
            spec_id="F001",
            title="Test Task",
            description="A test task",
            research_required=True,
            research_queries=[
                "How to implement authentication?",
                "Best JWT libraries?",
            ],
        )
        task_id = db.create_task(task)

        task = db.get_task(task_id)

        # Initialize controller
        controller = ResearchController(
            db_manager=db,
            workspace_dir=Path(tmpdir),
        )

        # Check if research needed
        assert controller.should_research(task) is True

        # Run research
        result = controller.run_research(task)
        assert result is True

        # Get updated task
        updated_task = db.get_task(task_id)

        # Verify research complete
        assert updated_task.research_complete is True
        assert len(updated_task.research_findings) > 0

        # Get implementation context
        context = controller.get_implementation_context(updated_task)
        assert len(context) > 0
        assert "Research Findings" in context

        # Check that research is no longer needed
        assert controller.should_research(updated_task) is False

        # Get summary
        summary = controller.get_research_summary(updated_task)
        assert "Research Summary" in summary
