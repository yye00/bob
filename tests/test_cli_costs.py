"""Tests for bob.cli.costs module (cost reporting commands)."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models.base import (
    AgentType,
    Project,
    Session,
    SessionStatus,
)


class TestCostsCommand:
    """Test 'bob costs' command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner(mix_stderr=False)

    def test_costs_with_no_projects(self, tmp_path: Path) -> None:
        """Test costs command with no projects."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(cli, ["--db", str(db_path), "costs"])

            assert result.exit_code == 0
            assert "No cost data available" in result.output

    def test_costs_with_single_project(self, tmp_path: Path) -> None:
        """Test costs command with single project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # Create project
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-1",
                name="test-app",
                description="",
                workspace_dir=str(tmp_path / "workspace"),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # Create a session with token counts that yield $0.15
            # Sonnet: input=$3/1M, output=$15/1M
            # 10K input = $0.03, 8K output = $0.12 => $0.15 total
            session = Session(
                id="sess-test-1",
                project_id=project.id,
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                input_tokens=10000,
                output_tokens=8000,
            )
            db.create_session(session)

            result = self.runner.invoke(cli, ["--db", str(db_path), "costs"])

            assert result.exit_code == 0
            assert "Cost Report: All Projects" in result.output
            assert "test-app" in result.output

    def test_costs_with_project_flag(self, tmp_path: Path) -> None:
        """Test costs command with --project flag."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # Create project
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-2",
                name="test-app",
                description="",
                workspace_dir=str(tmp_path / "workspace"),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # Create a session
            session = Session(
                id="sess-test-2",
                project_id=project.id,
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                input_tokens=10000,
                output_tokens=11334,  # ~$0.20 total
            )
            db.create_session(session)

            result = self.runner.invoke(
                cli, ["--db", str(db_path), "costs", "--project", "test-app"]
            )

            assert result.exit_code == 0
            assert f"Cost Report: test-app ({project.id})" in result.output

    def test_costs_with_nonexistent_project(self, tmp_path: Path) -> None:
        """Test costs command with nonexistent project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            result = self.runner.invoke(
                cli, ["--db", str(db_path), "costs", "--project", "nonexistent"]
            )

            assert result.exit_code == 1
            # Error message goes to stderr with mix_stderr=False
            combined = result.output + (getattr(result, 'stderr', '') or '')
            assert "not found" in combined.lower()

    def test_costs_json_output_single_project(self, tmp_path: Path) -> None:
        """Test costs command JSON output for single project."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # Create project
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-3",
                name="test-app",
                description="",
                workspace_dir=str(tmp_path / "workspace"),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # Create a session
            session = Session(
                id="sess-test-3",
                project_id=project.id,
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                input_tokens=10000,
                output_tokens=16000,  # ~$0.27 total
            )
            db.create_session(session)

            result = self.runner.invoke(
                cli,
                ["--db", str(db_path), "costs", "--project", "test-app", "--json-output"],
            )

            assert result.exit_code == 0

            # Parse JSON output (strip any trailing database messages)
            json_output = result.output.split('\n✓')[0]  # Remove database status messages
            data = json.loads(json_output)
            assert "project" in data
            assert data["project"]["name"] == "test-app"
            assert "costs" in data
            assert "total" in data["costs"]

    def test_costs_breakdown_by_model(self, tmp_path: Path) -> None:
        """Test costs breakdown by model."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # Create project
            db = DatabaseManager(db_path)
            project = Project(
                id="proj-test-4",
                name="test-app",
                description="",
                workspace_dir=str(tmp_path / "workspace"),
                spec_source="file://spec.yaml",
            )
            db.create_project(project)

            # Create sessions with different models
            session1 = Session(
                id="sess-test-4a",
                project_id=project.id,
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                input_tokens=10000,
                output_tokens=10000,
            )
            db.create_session(session1)

            session2 = Session(
                id="sess-test-4b",
                project_id=project.id,
                task_id=None,
                agent_type=AgentType.RESEARCH,
                model="claude-haiku-3-5",
                status=SessionStatus.COMPLETED,
                input_tokens=5000,
                output_tokens=5000,
            )
            db.create_session(session2)

            result = self.runner.invoke(
                cli, ["--db", str(db_path), "costs", "--project", "test-app"]
            )

            assert result.exit_code == 0
            assert "Cost by Model:" in result.output
            assert "claude-sonnet-4" in result.output
            assert "claude-haiku-3-5" in result.output

    def test_costs_with_multiple_projects(self, tmp_path: Path) -> None:
        """Test costs command with multiple projects."""
        with self.runner.isolated_filesystem(temp_dir=tmp_path):
            db_path = Path(".bob-test.db")

            # Create projects
            db = DatabaseManager(db_path)

            # Project 1
            project1 = Project(
                id="proj-test-5a",
                name="project-1",
                description="",
                workspace_dir=str(tmp_path / "workspace1"),
                spec_source="file://spec1.yaml",
            )
            db.create_project(project1)
            session1 = Session(
                id="sess-test-5a",
                project_id=project1.id,
                task_id=None,
                agent_type=AgentType.CODING,
                model="claude-sonnet-4",
                status=SessionStatus.COMPLETED,
                input_tokens=10000,
                output_tokens=30000,  # ~$0.48 total
            )
            db.create_session(session1)

            # Project 2
            project2 = Project(
                id="proj-test-5b",
                name="project-2",
                description="",
                workspace_dir=str(tmp_path / "workspace2"),
                spec_source="file://spec2.yaml",
            )
            db.create_project(project2)
            session2 = Session(
                id="sess-test-5b",
                project_id=project2.id,
                task_id=None,
                agent_type=AgentType.RESEARCH,
                model="claude-haiku-3-5",
                status=SessionStatus.COMPLETED,
                input_tokens=50000,
                output_tokens=50000,  # ~$0.24 total
            )
            db.create_session(session2)

            result = self.runner.invoke(cli, ["--db", str(db_path), "costs"])

            assert result.exit_code == 0
            assert "Cost Report: All Projects" in result.output
            assert "project-1" in result.output
            assert "project-2" in result.output
            assert "Projects: 2" in result.output
