"""Tests that create_agent_run writes to the project's database, not a cwd-resolved one.

Root cause: db.create_agent_run called connect() without db_path, so when the
orchestrator's cwd differed from the project's database location, the INSERT hit
a different SQLite file, failing the FK constraint (project_id REFERENCES projects(id))
and silently returning None → zero synthesized ACs for entire generations.

Fix: create_agent_run accepts an explicit db_path that is threaded from callers that
already know the project's database path, ensuring the INSERT targets the same DB as
the project row.
"""
from __future__ import annotations

import pathlib
import sqlite3
import uuid

import pytest

import bob3.db as db
from bob3.db import (
    create_agent_run,
    create_project,
    get_connection,
    init_database,
)


@pytest.fixture()
def isolated_db(tmp_path):
    """Create an isolated, fully-initialized database in a temp directory."""
    db_path = tmp_path / "project.db"
    init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project_in_isolated_db(isolated_db):
    """Create a project row in the isolated database, return (project, db_path)."""
    project = create_project(
        name="Test Project",
        workspace_path=str(isolated_db.parent),
        db_path=isolated_db,
    )
    return project, isolated_db


def test_create_agent_run_accepts_db_path_parameter():
    """create_agent_run must accept a db_path keyword argument."""
    import inspect
    sig = inspect.signature(create_agent_run)
    assert "db_path" in sig.parameters, (
        "create_agent_run must accept a db_path parameter to allow callers to "
        "specify exactly which database the row is written to"
    )


def test_create_agent_run_writes_to_explicit_db_path(project_in_isolated_db):
    """When db_path is supplied, the row must land in that database."""
    project, db_path = project_in_isolated_db
    run = create_agent_run(
        project_id=project.id,
        purpose="test_isolation",
        db_path=db_path,
    )
    assert run is not None
    assert run.id is not None
    assert run.project_id == project.id

    # Confirm the row is physically in the correct database file
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT id, project_id FROM sub_agent_runs WHERE id = ?", (run.id,)
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    assert row is not None, "Row must be present in the explicit db_path database"
    assert row[0] == run.id
    assert row[1] == project.id


def test_create_agent_run_does_not_leak_to_other_db(tmp_path, project_in_isolated_db):
    """Row must NOT appear in a second, separate database file."""
    project, db_path = project_in_isolated_db

    # Create a completely separate database (simulates the cwd-resolved DB)
    other_db_path = tmp_path / "other.db"
    init_database(db_path=other_db_path)

    run = create_agent_run(
        project_id=project.id,
        purpose="test_no_leak",
        db_path=db_path,
    )

    # The row must NOT appear in the unrelated database
    conn = sqlite3.connect(str(other_db_path))
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM sub_agent_runs WHERE id = ?", (run.id,)
        )
        count = cursor.fetchone()[0]
    finally:
        conn.close()
    assert count == 0, "Row must not appear in a database other than the explicit db_path"


def test_create_agent_run_fk_enforced_when_project_absent(tmp_path):
    """create_agent_run with a project_id not in the db must raise (FK enforcement)."""
    db_path = tmp_path / "empty.db"
    init_database(db_path=db_path)

    with pytest.raises(Exception):
        create_agent_run(
            project_id=str(uuid.uuid4()),  # not in this database
            purpose="fk_test",
            db_path=db_path,
        )


def test_create_project_accepts_db_path_parameter():
    """create_project must also accept a db_path so callers can co-locate the row."""
    import inspect
    sig = inspect.signature(create_project)
    assert "db_path" in sig.parameters, (
        "create_project must accept db_path so the project row and subsequent "
        "agent_run rows can target the same database"
    )


def test_create_project_writes_to_explicit_db_path(isolated_db):
    """create_project with db_path must write the project row to that database."""
    project = create_project(
        name="Explicit DB Project",
        workspace_path="/tmp/test_workspace",
        db_path=isolated_db,
    )
    assert project is not None
    assert project.id is not None

    conn = sqlite3.connect(str(isolated_db))
    try:
        cursor = conn.execute(
            "SELECT id, name FROM projects WHERE id = ?", (project.id,)
        )
        row = cursor.fetchone()
    finally:
        conn.close()
    assert row is not None, "Project row must be present in the explicit db_path database"
    assert row[0] == project.id
    assert row[1] == "Explicit DB Project"


def test_db_path_resolves_consistently_across_cwd_changes(tmp_path, monkeypatch):
    """When db_path is absolute, cwd changes must not affect which DB is used."""
    db_path = tmp_path / "stable.db"
    init_database(db_path=db_path)

    project = create_project(
        name="CWD-Stable Project",
        workspace_path=str(tmp_path),
        db_path=db_path,
    )

    # Change cwd to somewhere else — this would cause cwd-resolved DB to differ
    other_dir = tmp_path / "subdir"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    # create_agent_run with an absolute db_path must still work correctly
    run = create_agent_run(
        project_id=project.id,
        purpose="cwd_stable_test",
        db_path=db_path,
    )
    assert run is not None
    assert run.project_id == project.id
