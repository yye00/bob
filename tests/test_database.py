"""Tests for database schema and migrations."""

import sqlite3
import tempfile
from pathlib import Path
from bob.database import migrate, verify_schema, get_schema_version, CURRENT_SCHEMA_VERSION


class TestDatabaseSchema:
    """Test database schema creation and structure."""

    def test_schema_creation(self):
        """Test that schema creates all required tables."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")

            # Apply schema
            migrate(conn)

            # Verify all tables exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

            assert "projects" in tables
            assert "tasks" in tables
            assert "sessions" in tables
            assert "events" in tables
            assert "research_sessions" in tables
            assert "schema_version" in tables

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_projects_table_structure(self):
        """Test projects table has correct columns."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            cursor = conn.execute("PRAGMA table_info(projects)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            assert "id" in columns
            assert "name" in columns
            assert "description" in columns
            assert "workspace_dir" in columns
            assert "spec_source" in columns
            assert "config" in columns
            assert "created_at" in columns
            assert "status" in columns

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_tasks_table_structure(self):
        """Test tasks table has correct columns."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            assert "id" in columns
            assert "project_id" in columns
            assert "spec_id" in columns
            assert "title" in columns
            assert "description" in columns
            assert "acceptance_criteria" in columns
            assert "steps" in columns
            assert "depends_on" in columns
            assert "priority" in columns
            assert "category" in columns
            assert "labels" in columns
            assert "status" in columns
            assert "assigned_agent" in columns
            assert "current_model" in columns
            assert "attempts" in columns
            assert "escalation_tier" in columns
            assert "failure_type" in columns
            assert "research_required" in columns
            assert "research_complete" in columns
            assert "research_queries" in columns
            assert "research_findings" in columns
            assert "created_at" in columns
            assert "updated_at" in columns

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_sessions_table_structure(self):
        """Test sessions table has correct columns."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            cursor = conn.execute("PRAGMA table_info(sessions)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            assert "id" in columns
            assert "project_id" in columns
            assert "task_id" in columns
            assert "agent_type" in columns
            assert "model" in columns
            assert "started_at" in columns
            assert "ended_at" in columns
            assert "status" in columns
            assert "turns" in columns
            assert "tokens_input" in columns
            assert "tokens_output" in columns
            assert "cost" in columns

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_indexes_exist(self):
        """Test that all required indexes exist."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
            )
            indexes = [row[0] for row in cursor.fetchall()]

            # Check for key indexes
            assert "idx_tasks_project" in indexes
            assert "idx_tasks_status" in indexes
            assert "idx_sessions_project" in indexes
            assert "idx_events_project" in indexes

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_foreign_key_constraints(self):
        """Test that foreign key constraints work correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            # Insert a project
            conn.execute(
                """
                INSERT INTO projects (id, name, description, workspace_dir, spec_source)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("proj-1", "Test", "Test project", "/tmp/test", "file://spec.yaml"),
            )

            # Insert a task referencing the project
            conn.execute(
                """
                INSERT INTO tasks (id, project_id, spec_id, title, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("task-1", "proj-1", "F001", "Test task", "A test task"),
            )
            conn.commit()

            # Try to insert a task with invalid project_id (should fail)
            try:
                conn.execute(
                    """
                    INSERT INTO tasks (id, project_id, spec_id, title, description)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("task-2", "invalid-proj", "F002", "Bad task", "Should fail"),
                )
                conn.commit()
                assert False, "Foreign key constraint should have failed"
            except sqlite3.IntegrityError:
                # Expected behavior
                conn.rollback()

            # Verify the valid task was inserted
            cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE id = ?", ("task-1",))
            count = cursor.fetchone()[0]
            assert count == 1

            conn.close()
        finally:
            Path(db_path).unlink()


class TestMigrations:
    """Test database migration system."""

    def test_schema_version_tracking(self):
        """Test that schema version is tracked correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")

            # Initial version should be 0
            assert get_schema_version(conn) == 0

            # Apply migration
            migrate(conn)

            # Version should now be current
            assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_verify_schema_valid(self):
        """Test schema verification on valid database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            # Verify schema is valid
            assert verify_schema(conn) is True

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_verify_schema_missing_table(self):
        """Test schema verification fails when table is missing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)

            # Create incomplete schema (missing most tables)
            conn.execute("CREATE TABLE schema_version (version INTEGER)")
            conn.commit()

            # Verify should fail
            assert verify_schema(conn) is False

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_idempotent_migration(self):
        """Test that running migration multiple times is safe."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")

            # Run migration twice
            migrate(conn)
            version1 = get_schema_version(conn)

            migrate(conn)
            version2 = get_schema_version(conn)

            # Version should be the same
            assert version1 == version2
            assert verify_schema(conn) is True

            conn.close()
        finally:
            Path(db_path).unlink()


class TestDataInsertion:
    """Test inserting data into the schema."""

    def test_insert_project(self):
        """Test inserting a project."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            conn.execute(
                """
                INSERT INTO projects (id, name, description, workspace_dir, spec_source)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("proj-1", "My Project", "Description", "/workspace", "file://spec.yaml"),
            )
            conn.commit()

            cursor = conn.execute("SELECT * FROM projects WHERE id = ?", ("proj-1",))
            row = cursor.fetchone()
            assert row is not None
            assert row[1] == "My Project"

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_insert_task(self):
        """Test inserting a task."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            # Insert project first
            conn.execute(
                """
                INSERT INTO projects (id, name, description, workspace_dir, spec_source)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("proj-1", "Test", "Test", "/tmp", "file://spec.yaml"),
            )

            # Insert task
            conn.execute(
                """
                INSERT INTO tasks (id, project_id, spec_id, title, description, priority)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("task-1", "proj-1", "F001", "Test Task", "Description", "high"),
            )
            conn.commit()

            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", ("task-1",))
            row = cursor.fetchone()
            assert row is not None
            assert row[3] == "Test Task"
            assert row[8] == "high"

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_insert_session(self):
        """Test inserting a session."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            # Insert project first
            conn.execute(
                """
                INSERT INTO projects (id, name, description, workspace_dir, spec_source)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("proj-1", "Test", "Test", "/tmp", "file://spec.yaml"),
            )

            # Insert session
            conn.execute(
                """
                INSERT INTO sessions (id, project_id, agent_type, model)
                VALUES (?, ?, ?, ?)
                """,
                ("session-1", "proj-1", "coding", "claude-sonnet-4-5-20250929"),
            )
            conn.commit()

            cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", ("session-1",))
            row = cursor.fetchone()
            assert row is not None
            assert row[3] == "coding"

            conn.close()
        finally:
            Path(db_path).unlink()

    def test_cascade_delete(self):
        """Test that cascade delete works for foreign keys."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn)

            # Insert project and task
            conn.execute(
                """
                INSERT INTO projects (id, name, description, workspace_dir, spec_source)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("proj-1", "Test", "Test", "/tmp", "file://spec.yaml"),
            )
            conn.execute(
                """
                INSERT INTO tasks (id, project_id, spec_id, title, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("task-1", "proj-1", "F001", "Task", "Description"),
            )
            conn.commit()

            # Delete project
            conn.execute("DELETE FROM projects WHERE id = ?", ("proj-1",))
            conn.commit()

            # Task should also be deleted
            cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE id = ?", ("task-1",))
            count = cursor.fetchone()[0]
            assert count == 0

            conn.close()
        finally:
            Path(db_path).unlink()
