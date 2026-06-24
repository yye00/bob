"""Tests for create_agent_run DB isolation and FK enforcement.

Verifies that create_agent_run writes to the project's database when an
explicit db_path is supplied, and that FK constraints are enforced when the
referenced project_id does not exist in that database.
"""
from __future__ import annotations

import pathlib
import sqlite3
import uuid

import pytest

from bob.db import (
    create_agent_run,
    create_project,
    init_database,
)


@pytest.fixture()
def isolated_db(tmp_path: pathlib.Path) -> pathlib.Path:
    db_path = tmp_path / "test.db"
    init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project_and_db(isolated_db: pathlib.Path):
    project = create_project(
        name="Test Project",
        workspace_path=str(isolated_db.parent),
        db_path=isolated_db,
    )
    return project, isolated_db


def test_create_agent_run_uses_explicit_db_path(project_and_db):
    """create_agent_run with explicit db_path writes the row to that database."""
    project, db_path = project_and_db
    run = create_agent_run(
        project_id=project.id,
        purpose="test_explicit_db_path",
        db_path=db_path,
    )
    assert run is not None
    assert run.id is not None
    assert run.project_id == project.id

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


def test_create_agent_run_foreign_key_enforcement(isolated_db: pathlib.Path):
    """create_agent_run with a project_id absent from the DB must raise due to FK."""
    with pytest.raises(Exception):
        create_agent_run(
            project_id=str(uuid.uuid4()),  # not in this database
            purpose="fk_enforcement_test",
            db_path=isolated_db,
        )


def test_foreign_key_success_with_matching_database(project_and_db):
    """create_agent_run succeeds when project_id and db_path refer to the same database."""
    project, db_path = project_and_db
    run = create_agent_run(
        project_id=project.id,
        purpose="fk_success_matching_db",
        db_path=db_path,
    )
    assert run is not None
    assert run.project_id == project.id

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT project_id FROM sub_agent_runs WHERE id = ?", (run.id,)
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == project.id
