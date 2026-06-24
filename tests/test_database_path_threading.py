"""Tests for database path threading through orchestrator and create_agent_run.

Verifies that:
- set_database_path sets BOB_DATABASE_PATH and returns the absolute path
- create_agent_run respects an explicit db_path over env/cwd resolution
- The FK constraint is satisfied when project_id and db_path target the same DB
- The env var set by set_database_path propagates to create_agent_run when no db_path given
"""
import os
import pathlib
import sqlite3

import pytest

from bob import db
from bob.orchestrator import set_database_path


@pytest.fixture()
def project_db(tmp_path):
    """Return a path to an initialized database with one project row."""
    db_path = tmp_path / "project.db"
    db.init_database(db_path=db_path)
    project = db.create_project(
        name="ThreadingTestProject",
        workspace_path=str(tmp_path),
        db_path=db_path,
    )
    return db_path, project


def test_set_database_path_sets_env_var(tmp_path, monkeypatch):
    """set_database_path stores the resolved absolute path in BOB_DATABASE_PATH."""
    monkeypatch.delenv("BOB_DATABASE_PATH", raising=False)
    target = tmp_path / "mydb.db"
    result = set_database_path(target)
    assert result == target.resolve()
    assert os.environ["BOB_DATABASE_PATH"] == str(target.resolve())


def test_set_database_path_resolves_relative(tmp_path, monkeypatch):
    """set_database_path converts a relative path to absolute."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOB_DATABASE_PATH", raising=False)
    result = set_database_path(pathlib.Path("relative.db"))
    assert result.is_absolute()
    assert result == (tmp_path / "relative.db").resolve()


def test_set_database_path_returns_path_object(tmp_path, monkeypatch):
    """set_database_path returns a pathlib.Path."""
    monkeypatch.delenv("BOB_DATABASE_PATH", raising=False)
    result = set_database_path(tmp_path / "any.db")
    assert isinstance(result, pathlib.Path)


def test_create_agent_run_uses_explicit_db_path(project_db, tmp_path, monkeypatch):
    """When db_path is given to create_agent_run, the row lands in that DB only."""
    db_path, project = project_db

    # Point env at a different shadow db so we can confirm it's NOT used
    shadow = tmp_path / "shadow.db"
    db.init_database(db_path=shadow)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(shadow))

    run = db.create_agent_run(
        project_id=project.id,
        purpose="threading_explicit",
        db_path=db_path,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn.close()
    assert row is not None

    conn2 = sqlite3.connect(str(shadow))
    shadow_row = conn2.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn2.close()
    assert shadow_row is None


def test_create_agent_run_via_env_after_set_database_path(project_db, monkeypatch):
    """set_database_path followed by create_agent_run (no db_path) writes to the right DB."""
    db_path, project = project_db
    monkeypatch.delenv("BOB_DATABASE_PATH", raising=False)

    set_database_path(db_path)

    run = db.create_agent_run(
        project_id=project.id,
        purpose="threading_via_env",
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn.close()
    assert row is not None, "Row must exist in the DB set via set_database_path"


def test_create_agent_run_fk_succeeds_same_db(project_db):
    """create_agent_run does not raise a FK error when project_id and db_path match."""
    db_path, project = project_db
    # Must not raise sqlite3.IntegrityError
    run = db.create_agent_run(
        project_id=project.id,
        purpose="fk_check",
        db_path=db_path,
    )
    assert run.project_id == project.id


def test_create_agent_run_fk_fails_different_db(project_db, tmp_path):
    """create_agent_run raises when the project_id does not exist in the target db_path."""
    _db_path, project = project_db
    other_db = tmp_path / "other.db"
    db.init_database(db_path=other_db)

    with pytest.raises(Exception):
        db.create_agent_run(
            project_id=project.id,  # project only exists in project_db, not other_db
            purpose="should_fail_fk",
            db_path=other_db,
        )
