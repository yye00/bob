"""Tests for db_path threading in create_agent_run.

Verifies that create_agent_run writes to the explicitly-supplied database
(the project's own DB) rather than the cwd-resolved or BOB3_DATABASE_PATH-
resolved one. This prevents the FK-mismatch silent failure that caused zero
synthesized acceptance criteria.
"""
from __future__ import annotations

import os
import pathlib
import sqlite3
import tempfile
import uuid

import pytest

from bob3.db import (
    connect,
    create_agent_run,
    create_project,
    get_database_path,
    init_database,
)


def _make_test_db(tmp_path: pathlib.Path, suffix: str = "") -> pathlib.Path:
    """Create an initialised SQLite database in tmp_path."""
    db_path = tmp_path / f"bob3{suffix}.db"
    init_database(db_path=db_path)
    return db_path


def _count_agent_runs(db_path: pathlib.Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM sub_agent_runs").fetchone()[0]
    finally:
        conn.close()


class TestCreateAgentRunDbPathThreading:
    """create_agent_run writes to the supplied db_path, not to cwd/env."""

    def test_writes_to_explicit_db_path(self, tmp_path):
        """create_agent_run inserts into the db_path argument's database."""
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        before = _count_agent_runs(db)
        run = create_agent_run(
            project_id=project.id,
            purpose="test_write",
            db_path=db,
        )
        after = _count_agent_runs(db)
        assert after == before + 1
        assert run.project_id == project.id

    def test_does_not_write_to_cwd_db(self, tmp_path, monkeypatch):
        """When db_path is supplied, the cwd-resolved DB is untouched."""
        project_db = _make_test_db(tmp_path, "-project")
        cwd_db = _make_test_db(tmp_path, "-cwd")
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=project_db
        )
        monkeypatch.chdir(tmp_path)
        # Rename cwd DB so get_database_path() would resolve it if used
        cwd_db.rename(tmp_path / "bob3.db")
        cwd_shadow = tmp_path / "bob3.db"
        before_cwd = _count_agent_runs(cwd_shadow)
        create_agent_run(
            project_id=project.id,
            purpose="test_isolation",
            db_path=project_db,
        )
        after_cwd = _count_agent_runs(cwd_shadow)
        assert after_cwd == before_cwd, (
            "cwd-resolved DB was written when explicit db_path was supplied"
        )

    def test_does_not_write_to_env_db(self, tmp_path, monkeypatch):
        """When db_path is supplied, the BOB3_DATABASE_PATH DB is untouched."""
        project_db = _make_test_db(tmp_path, "-project")
        env_db = _make_test_db(tmp_path, "-env")
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=project_db
        )
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db))
        before_env = _count_agent_runs(env_db)
        create_agent_run(
            project_id=project.id,
            purpose="test_env_isolation",
            db_path=project_db,
        )
        after_env = _count_agent_runs(env_db)
        assert after_env == before_env, (
            "BOB3_DATABASE_PATH DB was written when explicit db_path was supplied"
        )

    def test_fk_constraint_satisfied_when_db_path_matches_project_db(self, tmp_path):
        """FK project_id is satisfied when project and agent_run share the same DB."""
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        # Should not raise FK violation
        run = create_agent_run(
            project_id=project.id,
            purpose="fk_test",
            db_path=db,
        )
        assert run.id is not None

    def test_fk_violation_when_project_id_not_in_db(self, tmp_path):
        """FK violation raised when project_id references a different database."""
        db_a = _make_test_db(tmp_path, "-a")
        db_b = _make_test_db(tmp_path, "-b")
        # Create project only in db_a
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db_a
        )
        # Write to db_b where the project does NOT exist — FK should fail
        with pytest.raises(Exception):
            create_agent_run(
                project_id=project.id,
                purpose="fk_violation_test",
                db_path=db_b,
            )

    def test_run_id_is_unique_per_call(self, tmp_path):
        """Each call generates a distinct run ID."""
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        run1 = create_agent_run(
            project_id=project.id, purpose="r1", db_path=db
        )
        run2 = create_agent_run(
            project_id=project.id, purpose="r2", db_path=db
        )
        assert run1.id != run2.id

    def test_explicit_run_id_is_honored(self, tmp_path):
        """Caller-supplied run_id is preserved in the returned record."""
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        fixed_id = str(uuid.uuid4())
        run = create_agent_run(
            project_id=project.id,
            purpose="id_test",
            run_id=fixed_id,
            db_path=db,
        )
        assert run.id == fixed_id

    def test_purpose_stored_correctly(self, tmp_path):
        """purpose field is persisted and returned in the model."""
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        run = create_agent_run(
            project_id=project.id,
            purpose="synthesize_acs",
            db_path=db,
        )
        assert run.purpose == "synthesize_acs"

    def test_status_defaults_to_running(self, tmp_path):
        """Default status is 'running'."""
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        run = create_agent_run(
            project_id=project.id,
            purpose="status_test",
            db_path=db,
        )
        assert run.status == "running"

    def test_optional_fields_stored(self, tmp_path):
        """Optional target_type/target_id/parent_run_id are persisted."""
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        # Create a real parent run first so the FK reference is valid
        parent_run = create_agent_run(
            project_id=project.id,
            purpose="parent_run",
            db_path=db,
        )
        run = create_agent_run(
            project_id=project.id,
            purpose="optional_fields",
            target_type="feature",
            target_id="abc-123",
            parent_run_id=parent_run.id,
            db_path=db,
        )
        assert run.target_type == "feature"
        assert run.target_id == "abc-123"
        assert run.parent_run_id == parent_run.id


class TestGetDatabasePathResolution:
    """get_database_path() respects BOB3_DATABASE_PATH, falls back to cwd."""

    def test_env_var_takes_precedence(self, tmp_path, monkeypatch):
        """BOB3_DATABASE_PATH overrides cwd-relative default."""
        custom = tmp_path / "custom.db"
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(custom))
        assert get_database_path() == custom

    def test_cwd_fallback(self, tmp_path, monkeypatch):
        """Without env var, resolves to cwd/bob3.db."""
        monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
        monkeypatch.chdir(tmp_path)
        assert get_database_path() == tmp_path / "bob3.db"


class TestDbLogsTelemetry:
    """create_agent_run logs the resolved database path for observability."""

    def test_log_message_contains_db_path(self, tmp_path, caplog):
        """A DEBUG log line records the resolved DB path so mismatches are visible."""
        import logging
        db = _make_test_db(tmp_path)
        project = create_project(
            name="p1", workspace_path=str(tmp_path), db_path=db
        )
        with caplog.at_level(logging.DEBUG, logger="bob3.db"):
            create_agent_run(
                project_id=project.id,
                purpose="telemetry_test",
                db_path=db,
            )
        assert any(str(db) in record.message for record in caplog.records), (
            "Expected resolved DB path to appear in debug logs"
        )
