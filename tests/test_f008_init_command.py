"""Tests for F008: Implement 'bob3 init <project>' command to create new project."""

import pathlib
import sqlite3

import pytest
from click.testing import CliRunner

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent


# ============================================================
# Step 1: Init command accepts project name argument
# ============================================================


class TestInitCommandAcceptsProject:
    """Step 1: Implement init command in cli.py that accepts a project name."""

    def test_init_command_exists(self):
        from bob3.cli import main

        assert "init" in main.commands, "init command must be registered"

    def test_init_with_project_name_does_not_error(self, tmp_path):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["init", str(tmp_path / "test-project")])
        assert result.exit_code == 0, f"init command failed: {result.output}"

    def test_init_without_args_shows_usage_or_error(self):
        from bob3.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["init"])
        # Should either show usage/help or fail with missing argument
        assert result.exit_code != 0 or "usage" in result.output.lower() or "error" in result.output.lower() or "missing" in result.output.lower()


# ============================================================
# Step 2: Create project workspace directory
# ============================================================


class TestProjectWorkspaceCreation:
    """Step 2: Create project workspace directory."""

    def test_workspace_directory_created(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "my-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"
        assert project_path.exists(), "Project workspace directory must be created"
        assert project_path.is_dir(), "Project workspace must be a directory"

    def test_workspace_directory_already_exists(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "existing-project"
        project_path.mkdir()
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        # Should succeed even if directory already exists
        assert result.exit_code == 0, f"init should work with existing dir: {result.output}"


# ============================================================
# Step 3: Initialize SQLite database with schema
# ============================================================


class TestDatabaseInitialization:
    """Step 3: Initialize SQLite database with schema."""

    def test_database_file_created(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "db-test-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        assert db_path.exists(), "bob3.db must be created in project workspace"

    def test_database_has_projects_table(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "schema-test-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        )
        tables = cursor.fetchall()
        conn.close()
        assert len(tables) == 1, "projects table must exist in database"

    def test_database_has_features_table(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "features-table-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='features'"
        )
        tables = cursor.fetchall()
        conn.close()
        assert len(tables) == 1, "features table must exist in database"

    def test_database_has_tasks_table(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "tasks-table-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
        tables = cursor.fetchall()
        conn.close()
        assert len(tables) == 1, "tasks table must exist in database"


# ============================================================
# Step 4: Insert project record into database
# ============================================================


class TestProjectRecordInsertion:
    """Step 4: Insert project record into database."""

    def test_project_record_exists(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "record-test"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM projects")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1, "Exactly one project record must be inserted"

    def test_project_record_has_correct_name(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "named-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM projects")
        name = cursor.fetchone()[0]
        conn.close()
        assert name == "named-project", f"Project name should be 'named-project', got '{name}'"

    def test_project_record_has_workspace_path(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "workspace-test"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT workspace_path FROM projects")
        workspace = cursor.fetchone()[0]
        conn.close()
        assert workspace == str(project_path.resolve()), (
            f"workspace_path should be '{project_path.resolve()}', got '{workspace}'"
        )

    def test_project_record_has_planning_status(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "status-test"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT status FROM projects")
        status = cursor.fetchone()[0]
        conn.close()
        assert status == "planning", f"Project status should be 'planning', got '{status}'"

    def test_project_record_has_id(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "id-test"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT id FROM projects")
        project_id = cursor.fetchone()[0]
        conn.close()
        assert project_id is not None and len(project_id) > 0, "Project must have a non-empty ID"


# ============================================================
# Step 5: Display success message with project path
# ============================================================


class TestSuccessMessage:
    """Step 5: Display success message with project path."""

    def test_success_message_displayed(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "success-msg-test"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"
        output_lower = result.output.lower()
        assert "initialized" in output_lower or "created" in output_lower or "success" in output_lower, (
            f"Success message expected, got: {result.output}"
        )

    def test_output_contains_project_path(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "path-in-output"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"
        assert str(project_path) in result.output or "path-in-output" in result.output, (
            f"Output should contain project path, got: {result.output}"
        )


# ============================================================
# Step 6: Run 'bob3 init test-project' and verify database created
# ============================================================


class TestEndToEndInit:
    """Step 6: Run 'bob3 init test-project' and verify database created."""

    def test_full_init_creates_database(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "test-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        assert db_path.exists(), "Database file must be created"

        # Verify it's a valid SQLite database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "projects" in tables
        assert "features" in tables
        assert "tasks" in tables

    def test_full_init_creates_workspace(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "test-project-ws"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"
        assert project_path.is_dir(), "Workspace directory must exist"


# ============================================================
# Step 7: Verify project record exists in database
# ============================================================


class TestProjectRecordVerification:
    """Step 7: Verify project record exists in database."""

    def test_project_record_complete(self, tmp_path):
        from bob3.cli import main

        project_path = tmp_path / "verify-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init command failed: {result.output}"

        db_path = project_path / "bob3.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM projects")
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "Project record must exist"
        assert row["id"] is not None, "Project must have an ID"
        assert row["name"] == "verify-project", f"Name mismatch: {row['name']}"
        assert row["workspace_path"] == str(project_path.resolve()), (
            f"Workspace path mismatch: {row['workspace_path']}"
        )
        assert row["status"] == "planning", f"Status mismatch: {row['status']}"
        assert row["created_at"] is not None, "created_at must be set"

    def test_multiple_inits_fail_or_coexist(self, tmp_path):
        """Running init twice on the same path should handle gracefully."""
        from bob3.cli import main

        project_path = tmp_path / "double-init"
        runner = CliRunner()
        result1 = runner.invoke(main, ["init", str(project_path)])
        assert result1.exit_code == 0

        result2 = runner.invoke(main, ["init", str(project_path)])
        # Second init may fail or succeed depending on implementation,
        # but should not crash
        assert result2.exit_code == 0 or "already" in result2.output.lower() or "exists" in result2.output.lower()


# ============================================================
# R9-008: bob3 init must honor BOB3_DATABASE_PATH
# ============================================================


class TestInitRespectsBob3DatabasePath:
    """Regression test for R9-008.

    When BOB3_DATABASE_PATH is set (the recommended hardened-deployment
    pattern: DB outside the workspace so sub-agents can't tamper with
    budget data), ``bob3 init <project>`` must create the database at
    that path — NOT at ``<project>/bob3.db``. Otherwise subsequent
    ``bob3 plan`` / ``bob3 run`` / ``bob3 status`` commands (which all
    route through ``get_database_path()`` and DO honor the env var) will
    report "No project found".
    """

    def test_init_uses_env_path_when_set(self, tmp_path, monkeypatch):
        """With BOB3_DATABASE_PATH set, the DB lands at the env path,
        not inside the workspace."""
        from bob3.cli import main

        secure_dir = tmp_path / "secure"
        env_db_path = secure_dir / "bob3.db"
        # Important: do NOT pre-create secure_dir. The init command must
        # create the parent directory itself when the env var points
        # somewhere that doesn't exist yet (operators often set this on
        # first run before any path exists).
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db_path))

        project_path = tmp_path / "test-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path), "--name", "test"])
        assert result.exit_code == 0, f"init failed: {result.output}"

        # The DB landed at the env-var path.
        assert env_db_path.exists(), (
            f"Database must be created at BOB3_DATABASE_PATH={env_db_path}, "
            f"got: {result.output}"
        )

        # The DB did NOT land inside the workspace.
        workspace_db = project_path / "bob3.db"
        assert not workspace_db.exists(), (
            f"Database must NOT be created at workspace path "
            f"{workspace_db} when BOB3_DATABASE_PATH is set"
        )

    def test_init_falls_back_to_workspace_when_env_unset(
        self, tmp_path, monkeypatch
    ):
        """Without BOB3_DATABASE_PATH, init keeps the legacy behavior:
        the DB lives inside the workspace at <project>/bob3.db."""
        from bob3.cli import main

        # Make sure it's NOT set (some test runners may leak env vars)
        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)

        project_path = tmp_path / "legacy-project"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init failed: {result.output}"

        workspace_db = project_path / "bob3.db"
        assert workspace_db.exists(), (
            "Without BOB3_DATABASE_PATH, init must create "
            "<project>/bob3.db (legacy behavior)"
        )

    def test_init_announces_db_path(self, tmp_path, monkeypatch):
        """The init output mentions where the database was created so
        operators can confirm the env-var path was honored."""
        from bob3.cli import main

        secure_dir = tmp_path / "secure"
        env_db_path = secure_dir / "bob3.db"
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db_path))

        project_path = tmp_path / "announce-test"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(project_path)])
        assert result.exit_code == 0, f"init failed: {result.output}"

        # Output should mention the DB path so the operator can verify
        # it landed where they wanted.
        assert str(env_db_path) in result.output, (
            f"init output must announce the database path; got: "
            f"{result.output!r}"
        )

    def test_subsequent_status_finds_project_via_env_path(
        self, tmp_path, monkeypatch
    ):
        """End-to-end sanity: after init with BOB3_DATABASE_PATH set,
        running ``bob3 status`` (which goes through get_database_path
        and respects the env var) finds the project. This is the bug
        R9-008 was fixing — without the fix, status reports
        'No project found.'"""
        from bob3.cli import main

        secure_dir = tmp_path / "secure"
        env_db_path = secure_dir / "bob3.db"
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db_path))

        project_path = tmp_path / "e2e-project"
        runner = CliRunner()
        init_result = runner.invoke(
            main, ["init", str(project_path), "--name", "e2e-project"]
        )
        assert init_result.exit_code == 0, (
            f"init failed: {init_result.output}"
        )

        # Now invoke status from a different cwd (the ``runner.invoke``
        # default doesn't change cwd, but the env var is what matters).
        status_result = runner.invoke(main, ["status"])
        assert status_result.exit_code == 0, (
            f"status failed: {status_result.output}"
        )

        # The project must be found — the legacy bug surfaced as
        # "No project found.". Check both that we DON'T see that and
        # that we DO see the project name.
        assert "no project found" not in status_result.output.lower(), (
            f"status reported 'No project found' — R9-008 regression: "
            f"{status_result.output}"
        )
        assert "e2e-project" in status_result.output, (
            f"status output should mention the project name 'e2e-project'; "
            f"got: {status_result.output}"
        )
