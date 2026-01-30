"""Tests for bob.cli.logs module (log viewing commands)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import Project
from bob.observability.logger import EventType, create_logger
from bob.state import StateManager


class TestLogsCommand:
    """Test 'bob logs' command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_logs_with_no_active_project(self, tmp_path: Path) -> None:
        """Test logs command with no active project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(cli, ["--db", str(db_path), "logs"])

            assert result.exit_code == 1
            assert "No active project" in result.output

    def test_logs_with_no_log_directory(self, tmp_path: Path) -> None:
        """Test logs command when log directory doesn't exist."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-1",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            result = self.runner.invoke(cli, ["--db", str(db_path), "logs"])

            assert result.exit_code == 1
            assert "No logs found" in result.output

    def test_logs_display_basic(self, tmp_path: Path) -> None:
        """Test basic log display."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-2",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create some logs
            logger = create_logger("test_logger", project_workspace=workspace)
            logger.set_context(project_id=project.id, session_id="sess-123")
            logger.info("Test message 1", event_type=EventType.SESSION_STARTED)
            logger.info("Test message 2", event_type=EventType.TASK_STARTED)
            logger.info("Test message 3", event_type=EventType.TASK_COMPLETED)

            result = self.runner.invoke(cli, ["--db", str(db_path), "logs"])

            assert result.exit_code == 0
            assert "Test message 1" in result.output
            assert "Test message 2" in result.output
            assert "Test message 3" in result.output

    def test_logs_filter_by_session(self, tmp_path: Path) -> None:
        """Test filtering logs by session ID."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-3",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create logs with different session IDs
            logger = create_logger("test_logger", project_workspace=workspace)
            logger.set_context(project_id=project.id, session_id="sess-123")
            logger.info("Message from session 123")

            logger.set_context(project_id=project.id, session_id="sess-456")
            logger.info("Message from session 456")

            # Filter by session 123
            result = self.runner.invoke(
                cli, ["--db", str(db_path), "logs", "--session", "sess-123"]
            )

            assert result.exit_code == 0
            assert "Message from session 123" in result.output
            assert "Message from session 456" not in result.output

    def test_logs_filter_by_level(self, tmp_path: Path) -> None:
        """Test filtering logs by level."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-4",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create logs with different levels
            logger = create_logger("test_logger", project_workspace=workspace)
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")

            # Filter by ERROR level
            result = self.runner.invoke(
                cli, ["--db", str(db_path), "logs", "--level", "ERROR"]
            )

            assert result.exit_code == 0
            assert "Error message" in result.output
            assert "Info message" not in result.output
            assert "Warning message" not in result.output

    def test_logs_filter_by_event_type(self, tmp_path: Path) -> None:
        """Test filtering logs by event type."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-5",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create logs with different event types
            logger = create_logger("test_logger", project_workspace=workspace)
            logger.info("Session started", event_type=EventType.SESSION_STARTED)
            logger.info("Task started", event_type=EventType.TASK_STARTED)
            logger.info("Task completed", event_type=EventType.TASK_COMPLETED)

            # Filter by task_started event
            result = self.runner.invoke(
                cli, ["--db", str(db_path), "logs", "--event", "task_started"]
            )

            assert result.exit_code == 0
            assert "Task started" in result.output
            assert "Session started" not in result.output
            assert "Task completed" not in result.output

    def test_logs_json_output(self, tmp_path: Path) -> None:
        """Test JSON output format."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-6",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create a log
            logger = create_logger("test_logger", project_workspace=workspace)
            logger.set_context(project_id=project.id, session_id="sess-789")
            logger.info("Test JSON message", event_type=EventType.TASK_STARTED)

            # Get JSON output
            result = self.runner.invoke(cli, ["--db", str(db_path), "logs", "--json"])

            assert result.exit_code == 0

            # Parse the JSON output (skip non-JSON lines like DB migration messages)
            lines = [line for line in result.output.strip().split("\n") if line]
            json_lines = [line for line in lines if line.strip().startswith("{")]
            assert len(json_lines) >= 1

            # Verify it's valid JSON
            log_entry = json.loads(json_lines[0])
            assert log_entry["message"] == "Test JSON message"
            assert log_entry["event_type"] == "task_started"
            assert log_entry["level"] == "INFO"
            assert "timestamp" in log_entry
            assert log_entry["context"]["project_id"] == project.id
            assert log_entry["context"]["session_id"] == "sess-789"

    def test_logs_tail_option(self, tmp_path: Path) -> None:
        """Test --tail option to limit output."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-7",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create 10 logs
            logger = create_logger("test_logger", project_workspace=workspace)
            for i in range(10):
                logger.info(f"Message {i}")

            # Get only last 3
            result = self.runner.invoke(cli, ["--db", str(db_path), "logs", "--tail", "3"])

            assert result.exit_code == 0
            assert "Message 7" in result.output
            assert "Message 8" in result.output
            assert "Message 9" in result.output
            assert "Message 0" not in result.output
            assert "Message 1" not in result.output

    def test_logs_with_exception(self, tmp_path: Path) -> None:
        """Test displaying logs with exception traces."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-8",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create a log with exception
            logger = create_logger("test_logger", project_workspace=workspace)
            try:
                raise ValueError("Test error")
            except ValueError:
                logger.error("Error occurred", exc_info=True)

            result = self.runner.invoke(cli, ["--db", str(db_path), "logs"])

            assert result.exit_code == 0
            assert "Error occurred" in result.output
            assert "ValueError: Test error" in result.output

    def test_logs_multiple_filters(self, tmp_path: Path) -> None:
        """Test combining multiple filters."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-9",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create various logs
            logger = create_logger("test_logger", project_workspace=workspace)
            logger.set_context(project_id=project.id, session_id="sess-abc")
            logger.info("Info task started", event_type=EventType.TASK_STARTED)
            logger.error("Error task started", event_type=EventType.TASK_STARTED)

            logger.set_context(project_id=project.id, session_id="sess-xyz")
            logger.info("Info task completed", event_type=EventType.TASK_COMPLETED)
            logger.error("Error task completed", event_type=EventType.TASK_COMPLETED)

            # Filter by session AND level AND event
            result = self.runner.invoke(
                cli,
                [
                    "--db",
                    str(db_path),
                    "logs",
                    "--session",
                    "sess-abc",
                    "--level",
                    "ERROR",
                    "--event",
                    "task_started",
                ],
            )

            assert result.exit_code == 0
            assert "Error task started" in result.output
            assert "Info task started" not in result.output
            assert "Error task completed" not in result.output
            assert "Info task completed" not in result.output

    def test_logs_empty_result(self, tmp_path: Path) -> None:
        """Test when no logs match the filter."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")
            workspace = tmp_path / "workspace"
            workspace.mkdir()

            # Create project and set as active
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-10",
                name="test-app",
                description="Test project",
                workspace_dir=str(workspace),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # State manager expects parent directory of db file
            state = StateManager(db_path.parent)
            state.set_active_project(project.id)

            # Create logs
            logger = create_logger("test_logger", project_workspace=workspace)
            logger.info("Test message")

            # Filter by non-existent session
            result = self.runner.invoke(
                cli, ["--db", str(db_path), "logs", "--session", "sess-nonexistent"]
            )

            assert result.exit_code == 0
            assert "No matching log entries found" in result.output
