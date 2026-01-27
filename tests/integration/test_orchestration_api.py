"""Integration tests for orchestration with real Claude API."""
import os
import pytest
import asyncio
from pathlib import Path
from bob.orchestrator.engine import Orchestrator, OrchestratorConfig
from bob.database.manager import DatabaseManager
from bob.models.base import Task, TaskStatus


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="No ANTHROPIC_API_KEY")
class TestClaudeOrchestration:
    """Test orchestration engine with real Claude API calls."""

    @pytest.mark.asyncio
    async def test_simple_task_execution(self, tmp_path):
        """Test that Claude can execute a simple file creation task."""
        # Setup
        db = DatabaseManager(tmp_path / "test.db")
        project_id = db.create_project("test_project", str(tmp_path))

        # Create orchestration engine
        config = OrchestratorConfig(non_interactive=True)
        orchestrator = Orchestrator(db, project_id, tmp_path, config)

        # Create a task
        task = Task(
            id="test-task-1",
            spec_id="task-1",
            project_id=project_id,
            description="Create a file called 'hello.txt' with the content 'Hello, World!'",
            status=TaskStatus.PENDING,
        )
        db.create_task(task)

        # Define a simple prompt
        prompt = """
        Create a file called 'hello.txt' with the content 'Hello, World!'.
        """

        # Execute task
        status, error = await orchestrator.execute_task(task, prompt)

        # Verify task succeeded
        assert status == TaskStatus.COMPLETED, f"Task should succeed, got {status}: {error}"

        # Verify file was created
        hello_file = tmp_path / "hello.txt"
        assert hello_file.exists(), "File should be created"
        content = hello_file.read_text().strip()
        assert "Hello, World!" in content, f"File content should contain greeting, got: {content}"

    @pytest.mark.asyncio
    async def test_task_with_requirements(self, tmp_path):
        """Test task execution with specific requirements."""
        # Setup
        db = DatabaseManager(tmp_path / "test.db")
        project_id = db.create_project("test_project", str(tmp_path))
        config = OrchestratorConfig(non_interactive=True)
        orchestrator = Orchestrator(db, project_id, tmp_path, config)

        # Create a task
        task = Task(
            id="test-task-2",
            spec_id="task-2",
            project_id=project_id,
            description="Create a Python calculator with add function",
            status=TaskStatus.PENDING,
        )
        db.create_task(task)

        # Task with requirements
        prompt = """
        Create a Python script called 'calculator.py' that has an 'add' function
        which takes two numbers and returns their sum.
        """

        # Execute
        status, error = await orchestrator.execute_task(task, prompt)

        # Verify task succeeded
        assert status == TaskStatus.COMPLETED, f"Task should succeed, got {status}: {error}"

        # Verify file exists
        calc_file = tmp_path / "calculator.py"
        assert calc_file.exists(), "Python file should be created"

        # Check that the file has an add function
        content = calc_file.read_text()
        assert "def add" in content, "Should have add function"
        assert "return" in content, "Function should return value"

    @pytest.mark.asyncio
    async def test_multi_step_task(self, tmp_path):
        """Test that Claude can handle multi-step tasks."""
        # Setup
        db = DatabaseManager(tmp_path / "test.db")
        project_id = db.create_project("test_project", str(tmp_path))
        config = OrchestratorConfig(non_interactive=True)
        orchestrator = Orchestrator(db, project_id, tmp_path, config)

        # Create a task
        task = Task(
            id="test-task-3",
            spec_id="task-3",
            project_id=project_id,
            description="Create data directory structure",
            status=TaskStatus.PENDING,
        )
        db.create_task(task)

        # Multi-step task
        prompt = """
        1. Create a directory called 'data'
        2. Create a file 'data/config.json' with JSON content: {"version": "1.0"}
        3. Create a file 'data/README.md' with the text: "Data directory for project"
        """

        # Execute
        status, error = await orchestrator.execute_task(task, prompt)

        # Verify task succeeded
        assert status == TaskStatus.COMPLETED, f"Task should succeed, got {status}: {error}"

        # Verify all steps
        data_dir = tmp_path / "data"
        assert data_dir.exists() and data_dir.is_dir(), "Directory should exist"

        config_file = data_dir / "config.json"
        assert config_file.exists(), "Config file should exist"
        assert "version" in config_file.read_text(), "Config should have version"

        readme_file = data_dir / "README.md"
        assert readme_file.exists(), "README should exist"
        assert "Data directory" in readme_file.read_text(), "README should have description"
