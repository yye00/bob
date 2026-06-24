"""Tests for bob3.db.create_agent_run — explicit db_path threading.

Verifies that create_agent_run correctly writes to the project's database
when db_path is supplied explicitly, and that the BOB3_DATABASE_PATH env
var is honoured when it is set.

Root-cause context: without an explicit db_path, create_agent_run resolved
the database from cwd or BOB3_DATABASE_PATH, which could differ from the
project's own DB, causing FK failures that silently zeroed synthesis.
"""
import os
import pathlib
import sqlite3
import uuid

import pytest

from bob3 import db


@pytest.fixture()
def project_with_db(tmp_path):
    """Return (project, db_path) in a fresh, isolated database."""
    db_path = tmp_path / "bob3.db"
    db.init_database(db_path=db_path)
    project = db.create_project(
        name="Test Project",
        workspace_path=str(tmp_path),
        db_path=db_path,
    )
    return project, db_path


def test_create_agent_run_returns_subagentrun(project_with_db):
    """create_agent_run returns a SubAgentRun with the expected fields."""
    project, db_path = project_with_db

    run = db.create_agent_run(
        project_id=project.id,
        purpose="test_purpose",
        db_path=db_path,
    )

    assert run.id is not None
    assert run.project_id == project.id
    assert run.purpose == "test_purpose"
    assert run.status == "running"


def test_create_agent_run_persisted_in_db(project_with_db):
    """Row actually lands in the correct database file."""
    project, db_path = project_with_db

    run = db.create_agent_run(
        project_id=project.id,
        purpose="persistence_check",
        db_path=db_path,
    )

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    row = conn.execute(
        "SELECT id, project_id, purpose FROM sub_agent_runs WHERE id = ?",
        (run.id,),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == run.id
    assert row[1] == project.id
    assert row[2] == "persistence_check"


def test_create_agent_run_explicit_run_id(project_with_db):
    """Supplying a run_id uses that exact value."""
    project, db_path = project_with_db
    custom_id = str(uuid.uuid4())

    run = db.create_agent_run(
        project_id=project.id,
        purpose="custom_id_test",
        run_id=custom_id,
        db_path=db_path,
    )

    assert run.id == custom_id


def test_create_agent_run_optional_fields(project_with_db):
    """Optional fields are stored and returned correctly."""
    project, db_path = project_with_db

    # Create a parent run first so the parent_run_id FK is valid
    parent_run = db.create_agent_run(
        project_id=project.id,
        purpose="parent_run",
        db_path=db_path,
    )

    run = db.create_agent_run(
        project_id=project.id,
        purpose="optional_fields",
        parent_run_id=parent_run.id,
        target_type="feature",
        target_id="feat-123",
        prompt_summary="summary text",
        status="running",
        db_path=db_path,
    )

    assert run.parent_run_id == parent_run.id
    assert run.target_type == "feature"
    assert run.target_id == "feat-123"
    assert run.prompt_summary == "summary text"


def test_create_agent_run_wrong_db_raises_fk_error(tmp_path):
    """Writing to a DB that doesn't contain the project row raises an integrity error."""
    # DB-A has the project; DB-B does not
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    db.init_database(db_path=db_a)
    db.init_database(db_path=db_b)

    project = db.create_project(
        name="Project A",
        workspace_path=str(tmp_path),
        db_path=db_a,
    )

    with pytest.raises(Exception) as exc_info:
        db.create_agent_run(
            project_id=project.id,
            purpose="wrong_db",
            db_path=db_b,  # wrong — project lives in db_a
        )

    exc_str = str(exc_info.value).lower()
    assert any(kw in exc_str for kw in ("foreign key", "integrity", "constraint")), (
        f"Expected FK/integrity error, got: {exc_info.value}"
    )


def test_create_agent_run_env_var_db_path_honoured(project_with_db, monkeypatch):
    """When BOB3_DATABASE_PATH is set to the project DB, create_agent_run succeeds."""
    project, db_path = project_with_db
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

    # Pass db_path explicitly (recommended path) — must succeed
    run = db.create_agent_run(
        project_id=project.id,
        purpose="env_var_test",
        db_path=db_path,
    )

    assert run.project_id == project.id


def test_create_agent_run_logs_resolved_path(project_with_db, caplog):
    """Debug log includes the resolved database path for observability."""
    import logging
    project, db_path = project_with_db

    with caplog.at_level(logging.DEBUG, logger="bob3.db"):
        db.create_agent_run(
            project_id=project.id,
            purpose="log_path_test",
            db_path=db_path,
        )

    log_text = caplog.text
    assert str(db_path) in log_text, (
        f"Expected db path {db_path} in debug log, got: {log_text}"
    )


def test_create_agent_run_importable_from_bob3_db():
    """bob3.db.create_agent_run is importable via the canonical entry point."""
    from bob3.db import create_agent_run as fn
    assert callable(fn)


def test_create_agent_run_importable_from_orchestrator():
    """bob3.orchestrator re-exports create_agent_run (integration AC)."""
    from bob3.orchestrator import create_agent_run as fn
    assert callable(fn)
