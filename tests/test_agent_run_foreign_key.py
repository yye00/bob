"""Tests for FK enforcement in create_agent_run.

Verifies that inserting a sub_agent_run referencing a project_id that does NOT
exist in the target database raises an IntegrityError (FK violation).
This directly validates the root-cause fix: when create_agent_run was
resolving to a different DB than the one containing the project row, EVERY
insert failed silently (synthesize_for_feature caught the exception and
returned None → deterministic fallback → synthesized=0/118).
"""
import pathlib
import sqlite3
import uuid

import pytest

from bob3 import db


@pytest.fixture()
def fresh_db(tmp_path):
    """Return an initialized, empty database at a temp path."""
    db_path = tmp_path / "test.db"
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project_db_with_project(tmp_path):
    """Return (project, db_path) where project lives in db_path."""
    db_path = tmp_path / "project.db"
    db.init_database(db_path=db_path)
    project = db.create_project(
        name="FK Test Project",
        workspace_path=str(tmp_path),
        db_path=db_path,
    )
    return project, db_path


def test_fk_violation_when_project_absent_from_target_db(fresh_db, monkeypatch):
    """Inserting an agent_run referencing a non-existent project raises IntegrityError.

    This simulates the pre-fix bug: create_agent_run resolved to a DB that
    didn't contain the project row, causing FOREIGN KEY constraint failure.
    """
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(fresh_db))
    phantom_project_id = str(uuid.uuid4())

    with pytest.raises(Exception) as exc_info:
        db.create_agent_run(
            project_id=phantom_project_id,
            purpose="fk_test",
            db_path=fresh_db,
        )

    exc_str = str(exc_info.value).lower()
    assert (
        "foreign key" in exc_str
        or "integrity" in exc_str
        or "constraint" in exc_str
    ), f"Expected FK/integrity error, got: {exc_info.value}"


def test_fk_succeeds_when_project_in_same_db(project_db_with_project):
    """Inserting an agent_run with an explicit db_path succeeds when project exists there."""
    project, db_path = project_db_with_project

    run = db.create_agent_run(
        project_id=project.id,
        purpose="fk_success_test",
        db_path=db_path,
    )

    assert run.id is not None
    assert run.project_id == project.id


def test_cross_db_mismatch_causes_fk_failure(tmp_path):
    """Agent run targeting DB-A fails when project lives only in DB-B.

    Simulates the exact pre-fix scenario: orchestrator wrote project row to
    <project>/bob3.db, but synthesizer's create_agent_run resolved to a
    different file (cwd or stale repo-root), causing silent total failure.
    """
    db_a = tmp_path / "db_a.db"
    db_b = tmp_path / "db_b.db"
    db.init_database(db_path=db_a)
    db.init_database(db_path=db_b)

    # Create project only in db_b
    project = db.create_project(
        name="Cross-DB Project",
        workspace_path=str(tmp_path),
        db_path=db_b,
    )

    # Attempt to write agent_run to db_a (wrong database) — must fail with FK error
    with pytest.raises(Exception) as exc_info:
        db.create_agent_run(
            project_id=project.id,
            purpose="cross_db_test",
            db_path=db_a,  # wrong db — project row is in db_b
        )

    exc_str = str(exc_info.value).lower()
    assert (
        "foreign key" in exc_str
        or "integrity" in exc_str
        or "constraint" in exc_str
    ), f"Cross-DB FK violation must raise, got: {exc_info.value}"


def test_create_agent_run_with_matching_db_path_no_fk_error(tmp_path):
    """End-to-end: create project and agent_run in same explicit db_path — no errors."""
    db_path = tmp_path / "matching.db"
    db.init_database(db_path=db_path)

    project = db.create_project(
        name="Matching DB Project",
        workspace_path=str(tmp_path),
        db_path=db_path,
    )

    # Must not raise
    run = db.create_agent_run(
        project_id=project.id,
        purpose="matching_db_test",
        db_path=db_path,
    )

    assert run.project_id == project.id

    # Verify row actually landed in db
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    row = conn.execute(
        "SELECT id, project_id FROM sub_agent_runs WHERE id = ?", (run.id,)
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[1] == project.id


def test_foreign_keys_pragma_enforced(fresh_db):
    """Directly verify that PRAGMA foreign_keys=ON is active in get_connection()."""
    conn = db.get_connection(db_path=fresh_db)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    conn.close()
    assert row[0] == 1, "PRAGMA foreign_keys must be ON in every connection"
