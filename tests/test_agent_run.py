"""Tests for bob.agent_run.create_agent_run.

Verifies that the facade in bob.agent_run correctly delegates to bob.db and
that db_path is threaded through so rows land in the correct database.
"""
import pathlib
import sqlite3
import uuid

import pytest

from bob import db
from bob.agent_run import create_agent_run


@pytest.fixture()
def project_with_db(tmp_path):
    """Return (project, db_path) in a fresh, isolated database."""
    db_path = tmp_path / "bob.db"
    db.init_database(db_path=db_path)
    project = db.create_project(
        name="Test Project",
        workspace_path=str(tmp_path),
        db_path=db_path,
    )
    return project, db_path


def test_create_agent_run_returns_subagentrun(project_with_db):
    project, db_path = project_with_db

    run = create_agent_run(
        project_id=project.id,
        purpose="test_purpose",
        db_path=db_path,
    )

    assert run.id is not None
    assert run.project_id == project.id
    assert run.purpose == "test_purpose"
    assert run.status == "running"


def test_create_agent_run_persisted_in_correct_db(project_with_db):
    project, db_path = project_with_db

    run = create_agent_run(
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


def test_create_agent_run_accepts_db_path_parameter(project_with_db):
    """Explicit db_path parameter is accepted and honoured."""
    project, db_path = project_with_db

    run = create_agent_run(
        project_id=project.id,
        purpose="db_path_param_test",
        db_path=db_path,
    )

    assert run.project_id == project.id


def test_create_agent_run_wrong_db_raises(tmp_path):
    """Writing to a DB that doesn't hold the project raises an integrity error."""
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
        create_agent_run(
            project_id=project.id,
            purpose="wrong_db",
            db_path=db_b,
        )

    exc_str = str(exc_info.value).lower()
    assert any(kw in exc_str for kw in ("foreign key", "integrity", "constraint"))


def test_create_agent_run_explicit_run_id(project_with_db):
    project, db_path = project_with_db
    custom_id = str(uuid.uuid4())

    run = create_agent_run(
        project_id=project.id,
        purpose="custom_id",
        run_id=custom_id,
        db_path=db_path,
    )

    assert run.id == custom_id


def test_create_agent_run_importable():
    from bob.agent_run import create_agent_run as fn
    assert callable(fn)
