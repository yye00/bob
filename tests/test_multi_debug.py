"""Tests for multi-debug loop and workspace inventory in engine."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from bob.database import DatabaseManager
from bob.models.base import (
    Task,
    TaskStatus,
    ModelTier,
    ExpectedOutput,
    Project,
    ProjectStatus,
)
from bob.orchestrator.engine import (
    Orchestrator,
    OrchestratorConfig,
)


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with some files."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    # Create some files for workspace inventory
    (project_dir / "main.py").write_text("print('hello')\n" * 10)
    (project_dir / "utils.py").write_text("def helper():\n    pass\n" * 5)
    sub = project_dir / "src"
    sub.mkdir()
    (sub / "core.py").write_text("class Core:\n    pass\n" * 3)
    # Create dirs that should be skipped
    git_dir = project_dir / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main")
    pycache = project_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "main.cpython-312.pyc").write_bytes(b"\x00" * 50)
    return project_dir


@pytest.fixture
def db_manager(tmp_path):
    """Create a test database manager."""
    db_path = tmp_path / "test.db"
    return DatabaseManager(db_path)


@pytest.fixture
def sample_task(db_manager):
    """Create a sample task."""
    project = Project(
        id="proj-1",
        name="test-project",
        description="Test project",
        workspace_dir="/tmp/test",
        spec_source="/tmp/test/spec.txt",
        status=ProjectStatus.ACTIVE,
    )
    db_manager.create_project(project)

    task = Task(
        id="task-123",
        project_id="proj-1",
        spec_id="F001",
        title="Test Feature",
        description="Implement feature X",
        status=TaskStatus.PENDING,
        current_model="claude-sonnet-4-20250514",
        attempts=0,
        escalation_tier=ModelTier.SONNET,
        expected_outputs=[
            ExpectedOutput(path="main.py", min_lines=5),
        ],
    )
    db_manager.create_task(task)
    return task


class TestWorkspaceInventory:
    """Test _get_workspace_inventory method."""

    def test_inventory_lists_files(self, db_manager, temp_project_dir):
        """Test that inventory lists project files with line counts."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        inventory = orchestrator._get_workspace_inventory()

        assert "main.py" in inventory
        assert "utils.py" in inventory
        assert "core.py" in inventory
        assert "lines" in inventory

    def test_inventory_skips_hidden_dirs(self, db_manager, temp_project_dir):
        """Test that .git and __pycache__ are skipped."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        inventory = orchestrator._get_workspace_inventory()

        assert ".git" not in inventory
        assert "__pycache__" not in inventory
        assert "HEAD" not in inventory
        assert ".pyc" not in inventory

    def test_inventory_empty_workspace(self, db_manager, tmp_path):
        """Test inventory on an empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        orchestrator = Orchestrator(db_manager, "proj-1", empty_dir)
        inventory = orchestrator._get_workspace_inventory()
        assert "empty workspace" in inventory


class TestBuildDebugPrompt:
    """Test _build_debug_prompt with new parameters."""

    def test_debug_prompt_includes_attempt_info(self, db_manager, temp_project_dir, sample_task):
        """Test that debug prompt includes attempt number."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        prompt = orchestrator._build_debug_prompt(
            task=sample_task,
            original_prompt="Original task prompt",
            verify_errors="Missing file: output.py",
            debug_attempt=2,
            previous_errors=["Error 1", "Error 2", "Missing file: output.py"],
        )
        assert "Debug attempt 3" in prompt  # 0-indexed + 1
        assert "Previous Debug Attempts" in prompt
        assert "Error 1" in prompt
        assert "DIFFERENT approach" in prompt

    def test_debug_prompt_includes_workspace_inventory(self, db_manager, temp_project_dir, sample_task):
        """Test that debug prompt includes workspace file inventory."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        prompt = orchestrator._build_debug_prompt(
            task=sample_task,
            original_prompt="Original task prompt",
            verify_errors="Something broke",
        )
        assert "Full Workspace File Inventory" in prompt
        assert "main.py" in prompt

    def test_debug_prompt_no_previous_errors(self, db_manager, temp_project_dir, sample_task):
        """Test debug prompt without previous errors."""
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir)
        prompt = orchestrator._build_debug_prompt(
            task=sample_task,
            original_prompt="Original task prompt",
            verify_errors="First error",
            debug_attempt=0,
            previous_errors=None,
        )
        assert "Previous Debug Attempts" not in prompt


class TestMultiDebugLoop:
    """Test the multi-debug loop in execute_task."""

    @pytest.mark.asyncio
    async def test_multi_debug_loops_multiple_times(self, db_manager, temp_project_dir, sample_task):
        """Test that debug loop runs multiple times on repeated failure."""
        config = OrchestratorConfig(max_debug_attempts=3)
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir, config)

        call_count = {"execute": 0, "verify": 0}

        async def mock_execute(client, prompt):
            call_count["execute"] += 1
            return (True, None)

        def mock_verify(task, project_dir):
            call_count["verify"] += 1
            # First verify fails, all debug verifies also fail
            return (False, f"Verification error #{call_count['verify']}")

        with patch.object(orchestrator, '_execute_with_client', side_effect=mock_execute):
            with patch('bob.orchestrator.engine.verify_task_outputs', side_effect=mock_verify):
                with patch.object(orchestrator, '_handle_failure', return_value=(TaskStatus.FAILED, "All debug failed")):
                    status, error = await orchestrator.execute_task(sample_task, "Test prompt")

        # 1 initial execute + 3 debug attempts = 4 execute calls
        assert call_count["execute"] == 4
        # 1 initial verify + 3 debug verifies = 4 verify calls
        assert call_count["verify"] == 4
        assert status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_debug_succeeds_on_second_attempt(self, db_manager, temp_project_dir, sample_task):
        """Test that debug succeeds on the second attempt."""
        config = OrchestratorConfig(max_debug_attempts=3)
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir, config)

        verify_count = {"count": 0}

        async def mock_execute(client, prompt):
            return (True, None)

        def mock_verify(task, project_dir):
            verify_count["count"] += 1
            # Fail on first two verifications (initial + first debug), pass on third (second debug)
            if verify_count["count"] <= 2:
                return (False, f"Error #{verify_count['count']}")
            return (True, "All good!")

        with patch.object(orchestrator, '_execute_with_client', side_effect=mock_execute):
            with patch('bob.orchestrator.engine.verify_task_outputs', side_effect=mock_verify):
                status, error = await orchestrator.execute_task(sample_task, "Test prompt")

        assert status == TaskStatus.COMPLETED
        assert error is None
        assert verify_count["count"] == 3  # initial + debug1 + debug2

    @pytest.mark.asyncio
    async def test_debug_execution_failure(self, db_manager, temp_project_dir, sample_task):
        """Test handling when debug execution itself fails."""
        config = OrchestratorConfig(max_debug_attempts=2)
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir, config)

        exec_count = {"count": 0}

        async def mock_execute(client, prompt):
            exec_count["count"] += 1
            if exec_count["count"] == 1:
                return (True, None)  # Initial execution succeeds
            return (False, "Debug execution crashed")  # Debug attempts fail

        def mock_verify(task, project_dir):
            return (False, "Something wrong")

        with patch.object(orchestrator, '_execute_with_client', side_effect=mock_execute):
            with patch('bob.orchestrator.engine.verify_task_outputs', side_effect=mock_verify):
                with patch.object(orchestrator, '_handle_failure', return_value=(TaskStatus.FAILED, "Gave up")):
                    status, error = await orchestrator.execute_task(sample_task, "Test prompt")

        assert status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_telemetry_records_debug_attempts(self, db_manager, temp_project_dir, sample_task):
        """Test that telemetry records each debug attempt."""
        config = OrchestratorConfig(max_debug_attempts=2)
        orchestrator = Orchestrator(db_manager, "proj-1", temp_project_dir, config)

        verify_count = {"count": 0}

        async def mock_execute(client, prompt):
            return (True, None)

        def mock_verify(task, project_dir):
            verify_count["count"] += 1
            if verify_count["count"] <= 2:
                return (False, f"Error #{verify_count['count']}")
            return (True, "Passed")

        with patch.object(orchestrator, '_execute_with_client', side_effect=mock_execute):
            with patch('bob.orchestrator.engine.verify_task_outputs', side_effect=mock_verify):
                await orchestrator.execute_task(sample_task, "Test prompt")

        # Check telemetry
        task_tel = orchestrator.telemetry.tasks.get(sample_task.id)
        assert task_tel is not None
        assert task_tel.debug_attempts >= 1
        assert len(task_tel.verification_results) >= 2
