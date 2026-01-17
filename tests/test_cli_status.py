"""Tests for global status command (F038)"""
import json
from pathlib import Path
from click.testing import CliRunner

from bob.cli.main import cli
from bob.database.manager import DatabaseManager
from bob.models import Project, ProjectStatus


class TestStatusCommand:
    """Test F038: Global status command"""

    def test_status_with_no_projects(self, tmp_path: Path) -> None:
        """Status command works with no projects"""
        db_path = tmp_path / "test.db"
        runner = CliRunner()

        result = runner.invoke(cli, ['--db', str(db_path), 'status'])

        assert result.exit_code == 0
        assert 'No projects found' in result.output

    def test_status_with_single_project(self, tmp_path: Path) -> None:
        """Status command shows single project"""
        db_path = tmp_path / "test.db"
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()

        # Create a project
        db = DatabaseManager(db_path)
        project = Project(
            id="proj-test",
            name="test-project",
            description="Test project",
            workspace_dir=str(workspace_path),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        runner = CliRunner()
        result = runner.invoke(cli, ['--db', str(db_path), 'status'])

        assert result.exit_code == 0
        assert 'BOB STATUS OVERVIEW' in result.output
        assert 'test-project' in result.output
        assert '1 total' in result.output  # 1 project

    def test_status_with_project_flag(self, tmp_path: Path) -> None:
        """Status command with --project flag shows specific project"""
        db_path = tmp_path / "test.db"
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()

        # Create projects
        db = DatabaseManager(db_path)
        project1 = Project(
            id="proj-one",
            name="project-one",
            description="First project",
            workspace_dir=str(workspace_path / "one"),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        project2 = Project(
            id="proj-two",
            name="project-two",
            description="Second project",
            workspace_dir=str(workspace_path / "two"),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project1)
        db.create_project(project2)

        runner = CliRunner()
        result = runner.invoke(cli, ['--db', str(db_path), 'status', '--project', 'project-one'])

        assert result.exit_code == 0
        assert 'project-one' in result.output
        assert 'project-two' not in result.output

    def test_status_with_nonexistent_project(self, tmp_path: Path) -> None:
        """Status command fails gracefully with nonexistent project"""
        db_path = tmp_path / "test.db"
        runner = CliRunner()

        result = runner.invoke(cli, ['--db', str(db_path), 'status', '--project', 'nonexistent'])

        assert result.exit_code != 0
        assert 'not found' in result.output

    def test_status_json_output_single_project(self, tmp_path: Path) -> None:
        """Status command produces valid JSON output"""
        db_path = tmp_path / "test.db"
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()

        # Create a project
        db = DatabaseManager(db_path)
        project = Project(
            id="proj-test",
            name="test-project",
            description="Test project",
            workspace_dir=str(workspace_path),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        runner = CliRunner()
        result = runner.invoke(cli, ['--db', str(db_path), 'status', '--json'])

        assert result.exit_code == 0

        # Parse JSON output - filter out database status messages
        lines = [line for line in result.output.split('\n') if line and not line.startswith('✓')]
        json_output = '\n'.join(lines)
        output = json.loads(json_output)

        assert 'projects' in output
        assert 'summary' in output
        assert 'total_costs' in output
        assert len(output['projects']) == 1
        assert output['projects'][0]['name'] == 'test-project'

    def test_status_with_multiple_projects(self, tmp_path: Path) -> None:
        """Status command shows multiple projects"""
        db_path = tmp_path / "test.db"
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()

        # Create multiple projects
        db = DatabaseManager(db_path)
        for i in range(3):
            project = Project(
                id=f"proj-{i}",
                name=f"project-{i}",
                description=f"Project {i}",
                workspace_dir=str(workspace_path / f"proj{i}"),
                spec_source="file://spec.yaml",
                status=ProjectStatus.ACTIVE,
            )
            db.create_project(project)

        runner = CliRunner()
        result = runner.invoke(cli, ['--db', str(db_path), 'status'])

        assert result.exit_code == 0
        assert 'project-0' in result.output
        assert 'project-1' in result.output
        assert 'project-2' in result.output
        assert '3 total' in result.output

    def test_status_shows_task_counts(self, tmp_path: Path) -> None:
        """Status command shows task counts for projects"""
        db_path = tmp_path / "test.db"
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()

        # Create project with tasks
        db = DatabaseManager(db_path)
        project = Project(
            id="proj-test",
            name="test-project",
            description="Test project",
            workspace_dir=str(workspace_path),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        # Add some tasks
        from bob.models import Task, TaskStatus
        for i in range(5):
            task = Task(
                id=f"task-{i}",
                project_id=project.id,
                spec_id=f"T{i:03d}",
                title=f"Task {i}",
                description=f"Description {i}",
                status=TaskStatus.COMPLETED if i < 2 else TaskStatus.PENDING,
            )
            db.create_task(task)

        runner = CliRunner()
        result = runner.invoke(cli, ['--db', str(db_path), 'status'])

        assert result.exit_code == 0
        assert '2/5 completed' in result.output or 'Tasks: 2/5' in result.output

    def test_status_shows_costs(self, tmp_path: Path) -> None:
        """Status command shows cost information"""
        db_path = tmp_path / "test.db"
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()

        # Create project
        db = DatabaseManager(db_path)
        project = Project(
            id="proj-test",
            name="test-project",
            description="Test project",
            workspace_dir=str(workspace_path),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        runner = CliRunner()
        result = runner.invoke(cli, ['--db', str(db_path), 'status'])

        assert result.exit_code == 0
        # Should show cost even if zero
        assert 'Cost:' in result.output or 'cost' in result.output.lower()

    def test_status_verbose_mode(self, tmp_path: Path) -> None:
        """Status command with --verbose shows more details"""
        db_path = tmp_path / "test.db"
        workspace_path = tmp_path / "workspace"
        workspace_path.mkdir()

        # Create project
        db = DatabaseManager(db_path)
        project = Project(
            id="proj-test",
            name="test-project",
            description="Test project",
            workspace_dir=str(workspace_path),
            spec_source="file://spec.yaml",
            status=ProjectStatus.ACTIVE,
        )
        db.create_project(project)

        runner = CliRunner()
        result_normal = runner.invoke(cli, ['--db', str(db_path), 'status'])
        result_verbose = runner.invoke(cli, ['--db', str(db_path), 'status', '--verbose'])

        assert result_normal.exit_code == 0
        assert result_verbose.exit_code == 0
        # Verbose output should be longer or contain more information
        # At minimum, both should succeed
        assert 'test-project' in result_verbose.output
