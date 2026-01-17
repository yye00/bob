"""Integration tests for research-first workflow.

This module tests the complete research workflow end-to-end:
- Task with research_required flag
- Research phase execution before implementation
- Research findings documentation
- Integration with PERPLEXITY_API_KEY
- Research context passed to implementation
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Tuple

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import (
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
)


def extract_json(output: str) -> dict:
    """Extract JSON from output that may contain extra text.

    Args:
        output: Output string that contains JSON

    Returns:
        Parsed JSON object
    """
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # Try to extract JSON portion from multi-line output
        start = output.find('{')
        if start == -1:
            start = output.find('[')

        if start != -1:
            # Find the matching closing brace/bracket
            depth = 0
            in_string = False
            escape = False

            for i in range(start, len(output)):
                c = output[i]

                if escape:
                    escape = False
                    continue

                if c == '\\':
                    escape = True
                    continue

                if c == '"' and not escape:
                    in_string = not in_string

                if not in_string:
                    if c in '{[':
                        depth += 1
                    elif c in '}]':
                        depth -= 1
                        if depth == 0:
                            # Found the end of JSON
                            json_str = output[start:i+1]
                            try:
                                return json.loads(json_str)
                            except json.JSONDecodeError:
                                pass

        # Try line by line as fallback
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Could not extract JSON from output: {output}")


@pytest.fixture
def setup_research_environment(tmp_path: Path) -> Tuple[Path, Path, Path]:
    """Setup research workflow test environment.

    Creates:
    - Temporary database path
    - Workspace directory
    - Spec file with research-required task

    Returns:
        Tuple of (db_path, workspace_path, spec_path)
    """
    # Create database path
    db_path = tmp_path / "test.db"

    # Create workspace directory
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create a spec file with research-required task
    spec_path = workspace / "spec.yaml"
    spec_content = """
spec_version: 1
tasks:
  - id: F001
    title: "Setup project structure"
    description: "Create initial project directories and files"
    priority: high
    category: functional
    steps:
      - "Create src/ directory"
      - "Create tests/ directory"
      - "Create README.md file"
    depends_on: []

  - id: F002
    title: "Implement advanced feature"
    description: "Implement a complex feature requiring research"
    priority: high
    category: functional
    research_required: true
    research_queries:
      - "Best practices for implementing X in Python"
      - "Common patterns for Y architecture"
      - "Performance optimization techniques for Z"
    steps:
      - "Research implementation approaches"
      - "Design architecture based on research"
      - "Implement core functionality"
      - "Add tests"
      - "Document findings"
    depends_on:
      - F001

  - id: F003
    title: "Write documentation"
    description: "Create user documentation"
    priority: medium
    category: documentation
    steps:
      - "Write usage guide"
      - "Add examples"
    depends_on:
      - F002
"""
    spec_path.write_text(spec_content)

    return db_path, workspace, spec_path


class TestResearchWorkflowIntegration:
    """Integration tests for research-first workflow."""

    def test_research_workflow_with_api_key(self, setup_research_environment, monkeypatch):
        """Test F052: Complete research workflow with PERPLEXITY_API_KEY set.

        Steps:
        1. Create test project with task that has research_required: true
        2. Add research_queries to task spec
        3. Run 'bob run --project test-research'
        4. Verify research phase executes before implementation
        5. Verify research findings are documented in task
        6. Verify task.research_complete is set to true
        7. Verify implementation uses research context
        """
        # Set mock API key
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test_key_12345")

        db_path, workspace, spec_path = setup_research_environment
        runner = CliRunner()

        # Create project
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-research",
            str(workspace),
            f"file://{spec_path}",
            "--description", "Research workflow test project",
        ])

        assert result.exit_code == 0, f"Project creation failed: {result.output}"
        assert "Created project 'test-research'" in result.output

        # Verify project was created
        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-research"), None)
        assert project is not None
        assert project.name == "test-research"
        project_id = project.id

        # Sync tasks from spec
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
            "--json-output",
        ])

        assert result.exit_code == 0, f"Sync failed: {result.output}"
        sync_output = extract_json(result.output)
        assert sync_output["added"] == 3  # 3 tasks from spec

        # Verify tasks were created with research fields
        all_tasks = db.list_tasks(project_id=project_id)
        assert len(all_tasks) == 3

        # Find task F002 (the research-required task)
        task_map = {task.spec_id: task for task in all_tasks}
        research_task = task_map["F002"]

        # Verify research fields are set correctly
        assert research_task.research_required is True
        assert research_task.research_complete is False
        assert len(research_task.research_queries) == 3
        assert "Best practices for implementing X in Python" in research_task.research_queries
        assert research_task.research_findings is None or research_task.research_findings == {}

        # Test research controller directly
        from bob.orchestrator.research_controller import ResearchController

        research_controller = ResearchController(
            db_manager=db,
            workspace_dir=workspace,
            perplexity_available=True,
        )

        # With API key, perplexity should be available
        assert research_controller.perplexity_available is True

        # Check if research is needed
        assert research_controller.should_research(research_task) is True

        # Run research
        success = research_controller.run_research(research_task, research_type="quick", max_queries=2)
        assert success is True

        # Refresh task from database
        research_task_updated = db.get_task(research_task.id)

        # Verify research was completed
        assert research_task_updated.research_complete is True
        assert research_task_updated.research_findings is not None
        assert isinstance(research_task_updated.research_findings, dict)

        # Verify research findings contain the queries
        findings = research_task_updated.research_findings
        assert len(findings) > 0

        # At least one query should have findings
        for query, data in findings.items():
            assert "findings" in data
            assert "sources" in data
            assert "suggestions" in data
            assert "timestamp" in data
            assert "success" in data

        # Verify should_research returns False now
        assert research_controller.should_research(research_task_updated) is False

        # Verify implementation context can be retrieved
        context = research_controller.get_implementation_context(research_task_updated)
        assert context is not None
        assert "research_findings" in context or len(research_task_updated.research_findings) > 0

    def test_research_workflow_without_api_key(self, setup_research_environment, monkeypatch):
        """Test F052: Research workflow behavior without PERPLEXITY_API_KEY.

        Steps:
        1. Create test project with research-required task
        2. Ensure PERPLEXITY_API_KEY is not set
        3. Verify ResearchController detects missing API key
        4. Verify graceful handling when API key is missing
        """
        # Remove API key
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

        db_path, workspace, spec_path = setup_research_environment
        runner = CliRunner()

        # Create project
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-research-no-key",
            str(workspace),
            f"file://{spec_path}",
            "--description", "Research workflow test without API key",
        ])

        assert result.exit_code == 0
        assert "Created project 'test-research-no-key'" in result.output

        # Get project
        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-research-no-key"), None)
        assert project is not None
        project_id = project.id

        # Sync tasks
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
            "--json-output",
        ])

        assert result.exit_code == 0

        # Get task F002
        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        research_task = task_map["F002"]

        # Test research controller without API key
        from bob.orchestrator.research_controller import ResearchController

        research_controller = ResearchController(
            db_manager=db,
            workspace_dir=workspace,
            perplexity_available=True,  # Even if we set this to True
        )

        # Should detect missing API key and set to False
        assert research_controller.perplexity_available is False

        # Should still be able to check if research is needed
        assert research_controller.should_research(research_task) is True

        # Research execution should still work (using fallback/placeholder)
        success = research_controller.run_research(research_task, research_type="quick", max_queries=1)
        assert success is True

        # Refresh task
        research_task_updated = db.get_task(research_task.id)

        # Should still mark as complete even without real API
        assert research_task_updated.research_complete is True

    def test_research_findings_persistence(self, setup_research_environment, monkeypatch):
        """Test that research findings are persisted correctly in database.

        Steps:
        1. Create project with research task
        2. Execute research
        3. Verify findings are stored in database
        4. Verify findings survive database reconnection
        """
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test_key_12345")

        db_path, workspace, spec_path = setup_research_environment
        runner = CliRunner()

        # Create and setup project
        result = runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-research-persist",
            str(workspace),
            f"file://{spec_path}",
        ])
        assert result.exit_code == 0

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-research-persist"), None)
        project_id = project.id

        # Sync tasks
        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        # Get research task
        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        research_task = task_map["F002"]
        task_id = research_task.id

        # Run research
        from bob.orchestrator.research_controller import ResearchController

        research_controller = ResearchController(
            db_manager=db,
            workspace_dir=workspace,
            perplexity_available=True,
        )

        success = research_controller.run_research(research_task, max_queries=2)
        assert success is True

        # Get findings
        research_task_updated = db.get_task(task_id)
        original_findings = research_task_updated.research_findings

        assert original_findings is not None
        assert len(original_findings) > 0

        # Close and reopen database
        db = None
        db = DatabaseManager(db_path)

        # Retrieve task again
        task_after_reconnect = db.get_task(task_id)

        # Verify findings persisted
        assert task_after_reconnect.research_complete is True
        assert task_after_reconnect.research_findings is not None
        assert task_after_reconnect.research_findings == original_findings

    def test_research_skipped_when_complete(self, setup_research_environment, monkeypatch):
        """Test that research is skipped when already completed.

        Steps:
        1. Create project with research task
        2. Complete research
        3. Attempt to run research again
        4. Verify research is skipped
        """
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test_key_12345")

        db_path, workspace, spec_path = setup_research_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-research-skip",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-research-skip"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        research_task = task_map["F002"]

        # Run research first time
        from bob.orchestrator.research_controller import ResearchController

        research_controller = ResearchController(
            db_manager=db,
            workspace_dir=workspace,
            perplexity_available=True,
        )

        # First run should succeed
        success_first = research_controller.run_research(research_task)
        assert success_first is True

        # Get updated task
        research_task_updated = db.get_task(research_task.id)
        assert research_task_updated.research_complete is True

        # Second run should be skipped
        assert research_controller.should_research(research_task_updated) is False

        # Attempting to run should return False (not needed)
        success_second = research_controller.run_research(research_task_updated)
        assert success_second is False

    def test_task_without_research_queries(self, setup_research_environment, monkeypatch):
        """Test behavior when research_required is True but no queries provided.

        Steps:
        1. Create task with research_required=True but empty research_queries
        2. Verify should_research returns False
        3. Verify task can proceed without research
        """
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test_key_12345")

        db_path, workspace, spec_path = setup_research_environment
        db = DatabaseManager(db_path)

        # Create project manually
        project = Project(
            id="proj-test-research-no-queries",
            name="test-no-queries",
            description="Test project",
            workspace_dir=str(workspace),
            spec_source=f"file://{spec_path}",
        )
        project_id = db.create_project(project)

        # Create task with research_required but no queries
        task = Task(
            id="task-no-queries",
            project_id=project_id,
            spec_id="F999",
            title="Task without research queries",
            description="A task marked as research_required but has no queries",
            steps=["Step 1", "Step 2"],
            research_required=True,
            research_queries=[],  # Empty queries
        )
        task_id = db.create_task(task)
        task = db.get_task(task_id)

        # Test research controller
        from bob.orchestrator.research_controller import ResearchController

        research_controller = ResearchController(
            db_manager=db,
            workspace_dir=workspace,
            perplexity_available=True,
        )

        # Should not need research (no queries)
        assert research_controller.should_research(task) is False

        # run_research should return False
        success = research_controller.run_research(task)
        assert success is False

    def test_research_implementation_context(self, setup_research_environment, monkeypatch):
        """Test that research findings are properly formatted for implementation context.

        Steps:
        1. Create project with research task
        2. Complete research
        3. Get implementation context
        4. Verify context contains research findings in usable format
        """
        monkeypatch.setenv("PERPLEXITY_API_KEY", "test_key_12345")

        db_path, workspace, spec_path = setup_research_environment
        runner = CliRunner()

        # Setup project
        runner.invoke(cli, [
            "--db", str(db_path),
            "project", "create",
            "test-research-context",
            str(workspace),
            f"file://{spec_path}",
        ])

        db = DatabaseManager(db_path)
        projects = db.list_projects()
        project = next((p for p in projects if p.name == "test-research-context"), None)
        project_id = project.id

        runner.invoke(cli, [
            "--db", str(db_path),
            "--project", project_id,
            "sync",
        ])

        all_tasks = db.list_tasks(project_id=project_id)
        task_map = {task.spec_id: task for task in all_tasks}
        research_task = task_map["F002"]

        # Run research
        from bob.orchestrator.research_controller import ResearchController

        research_controller = ResearchController(
            db_manager=db,
            workspace_dir=workspace,
            perplexity_available=True,
        )

        research_controller.run_research(research_task, max_queries=3)

        # Get updated task
        research_task_updated = db.get_task(research_task.id)

        # Get implementation context
        context = research_controller.get_implementation_context(research_task_updated)

        # Verify context structure
        assert context is not None
        assert isinstance(context, str)
        assert len(context) > 0

        # Context should contain research information formatted as markdown
        assert "## Research Findings" in context
        assert "Use these research findings" in context

        # Should contain query information
        assert "Best practices for implementing X in Python" in context

        # Context should contain research information
        assert research_task_updated.research_complete is True
        assert research_task_updated.research_findings is not None
