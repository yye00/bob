"""Tests for create_agent_run DB path resolution (feature a27bd334).

Verifies that:
- create_agent_run accepts an explicit db_path and writes to that file
- export_database_path sets BOB3_DATABASE_PATH to an absolute path
- Sub-agents that inherit BOB3_DATABASE_PATH use the same DB as the project
- A 0-byte stale db in cwd does not shadow the real project DB when db_path
  is passed explicitly
"""

import os
import pathlib
import sqlite3
import tempfile
import uuid

import pytest


def _make_db(path: pathlib.Path) -> None:
    """Create a minimal bob3 schema in a fresh SQLite file at path."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            spec_path TEXT,
            workspace_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planning',
            total_cost_usd REAL NOT NULL DEFAULT 0.0,
            max_cost_usd REAL,
            spec_hash TEXT,
            spec_last_modified TEXT,
            environment_fingerprint TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sub_agent_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id),
            parent_run_id TEXT,
            purpose TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            prompt_summary TEXT,
            mcp_enabled TEXT,
            created_at TEXT NOT NULL,
            ended_at TEXT,
            exit_code INTEGER,
            cost_usd REAL,
            output_summary TEXT,
            error_summary TEXT,
            tokens_used INTEGER,
            attempts INTEGER DEFAULT 1,
            is_startup_crash_exempt INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()


def _insert_project(db_path: pathlib.Path) -> str:
    """Insert a minimal project row and return its ID."""
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    import datetime
    now = datetime.datetime.now().isoformat()
    conn.execute(
        """INSERT INTO projects
           (id, name, workspace_path, status, total_cost_usd,
            max_cost_usd, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (project_id, "test-project", str(db_path.parent),
         "planning", 0.0, 1000000.0, now, now),
    )
    conn.commit()
    conn.close()
    return project_id


class TestCreateAgentRunDbPath:
    """create_agent_run writes to the db_path supplied, not the cwd one."""

    def test_writes_to_explicit_db_path(self, tmp_path):
        """Passing db_path explicitly routes the INSERT to that file."""
        from bob3.db import create_agent_run, init_database

        db_file = tmp_path / "project.db"
        init_database(db_path=db_file)
        project_id = _insert_project(db_file)

        run = create_agent_run(
            project_id=project_id,
            purpose="test-purpose",
            db_path=db_file,
        )

        # Row must be visible in the correct file
        conn = sqlite3.connect(str(db_file))
        row = conn.execute(
            "SELECT id, project_id FROM sub_agent_runs WHERE id = ?",
            (run.id,),
        ).fetchone()
        conn.close()

        assert row is not None, "Row should exist in the target database"
        assert row[0] == run.id
        assert row[1] == project_id

    def test_explicit_db_path_not_cwd_default(self, tmp_path, monkeypatch):
        """When db_path is given, cwd/bob3.db is NOT touched even if it exists."""
        from bob3.db import create_agent_run, init_database

        # Create a stale 0-byte file that would shadow the real DB
        stale_db = tmp_path / "bob3.db"
        stale_db.write_bytes(b"")

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)

        real_db = tmp_path / "real_project.db"
        init_database(db_path=real_db)
        project_id = _insert_project(real_db)

        run = create_agent_run(
            project_id=project_id,
            purpose="explicit-path-test",
            db_path=real_db,
        )

        # Row must be in real_db
        conn = sqlite3.connect(str(real_db))
        row = conn.execute(
            "SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)
        ).fetchone()
        conn.close()
        assert row is not None, "Row must be in the explicitly supplied DB"

        # Stale db must remain empty (no sub_agent_runs table created there)
        stale_size = stale_db.stat().st_size
        assert stale_size == 0, "Stale cwd/bob3.db must not be written to"

    def test_fk_violation_raises_on_wrong_db(self, tmp_path):
        """Writing a project_id to a DB that does not contain it raises."""
        from bob3.db import create_agent_run, init_database

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"

        init_database(db_path=db_a)
        init_database(db_path=db_b)

        # project lives in db_a only
        project_id = _insert_project(db_a)

        # Writing agent_run to db_b (different DB, FK absent) must raise
        with pytest.raises(Exception):
            create_agent_run(
                project_id=project_id,
                purpose="fk-mismatch-test",
                db_path=db_b,
            )


class TestExportDatabasePath:
    """export_database_path exports an absolute path into BOB3_DATABASE_PATH."""

    def test_returns_absolute_path(self, tmp_path, monkeypatch):
        """Always returns an absolute pathlib.Path."""
        from bob3.orchestrator import export_database_path

        db_file = tmp_path / "project.db"
        db_file.touch()

        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
        result = export_database_path(db_path=db_file)

        assert isinstance(result, pathlib.Path)
        assert result.is_absolute()

    def test_sets_env_var(self, tmp_path, monkeypatch):
        """Sets BOB3_DATABASE_PATH to the resolved absolute path string."""
        from bob3.orchestrator import export_database_path

        db_file = tmp_path / "project.db"
        db_file.touch()

        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
        result = export_database_path(db_path=db_file)

        assert os.environ.get("BOB3_DATABASE_PATH") == str(result)

    def test_honors_existing_env_when_no_arg(self, tmp_path, monkeypatch):
        """When no db_path supplied, resolves from BOB3_DATABASE_PATH env."""
        from bob3.orchestrator import export_database_path

        env_db = tmp_path / "env_db.db"
        env_db.touch()
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db))

        result = export_database_path()

        assert result == env_db.resolve()
        assert os.environ["BOB3_DATABASE_PATH"] == str(result)

    def test_explicit_arg_overrides_env(self, tmp_path, monkeypatch):
        """Explicit db_path argument overrides BOB3_DATABASE_PATH env."""
        from bob3.orchestrator import export_database_path

        env_db = tmp_path / "env_db.db"
        env_db.touch()
        explicit_db = tmp_path / "explicit_db.db"
        explicit_db.touch()

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db))

        result = export_database_path(db_path=explicit_db)

        assert result == explicit_db.resolve()
        assert os.environ["BOB3_DATABASE_PATH"] == str(explicit_db.resolve())

    def test_subagent_inherits_exported_path(self, tmp_path, monkeypatch):
        """After export_database_path, get_database_path returns the same path."""
        from bob3.orchestrator import export_database_path
        from bob3.db import get_database_path

        db_file = tmp_path / "project.db"
        db_file.touch()
        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)

        exported = export_database_path(db_path=db_file)
        # get_database_path should now pick up the exported env var
        resolved = get_database_path()

        assert resolved == exported, (
            "get_database_path must return the same path after export_database_path sets env"
        )
