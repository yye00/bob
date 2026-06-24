"""Tests for bob3.database and bob3.orchestrator.initialize_project_database.

Verifies the two-layer fix for the DB mismatch that caused synthesized=0/118:
  (1) create_agent_run accepts an explicit db_path so FK inserts land in the
      correct database regardless of cwd or BOB3_DATABASE_PATH.
  (2) initialize_project_database resolves and exports an absolute DB path so
      all sub-agents and subsequent connect() calls share the same file.
"""
import os
import pathlib
import sqlite3
import uuid

import pytest

import bob3.database as db_module
from bob3 import db
from bob3 import orchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_db(tmp_path):
    """Initialised SQLite database in a temp directory."""
    db_path = tmp_path / "project.db"
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project_in_db(isolated_db):
    """A project row in the isolated database; returns (project, db_path)."""
    project = db.create_project(
        name="TestProject-" + uuid.uuid4().hex[:8],
        workspace_path=str(isolated_db.parent),
        db_path=isolated_db,
    )
    return project, isolated_db


# ---------------------------------------------------------------------------
# bob3.database — module-level checks
# ---------------------------------------------------------------------------

def test_database_module_importable():
    assert db_module is not None


def test_create_agent_run_defined_on_database_module():
    assert hasattr(db_module, "create_agent_run")
    assert callable(db_module.create_agent_run)


# ---------------------------------------------------------------------------
# create_agent_run — explicit db_path routes to the right file
# ---------------------------------------------------------------------------

def test_create_agent_run_writes_to_explicit_db_path(project_in_db, tmp_path, monkeypatch):
    """Row lands in the explicitly supplied database, not the env-resolved one."""
    project, project_db = project_in_db

    shadow_db = tmp_path / "shadow.db"
    db.init_database(db_path=shadow_db)
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(shadow_db))

    run = db.create_agent_run(
        project_id=project.id,
        purpose="explicit_path_test",
        db_path=project_db,
    )

    conn = sqlite3.connect(str(project_db))
    row = conn.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn.close()
    assert row is not None, "row must be in the explicit db_path"

    conn2 = sqlite3.connect(str(shadow_db))
    shadow_row = conn2.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn2.close()
    assert shadow_row is None, "row must NOT be written to the env-resolved database"


def test_create_agent_run_returns_sub_agent_run_with_matching_fields(project_in_db):
    """Return value mirrors the arguments passed in."""
    project, project_db = project_in_db
    purpose = "verify_return_value"
    run = db.create_agent_run(
        project_id=project.id,
        purpose=purpose,
        db_path=project_db,
    )
    assert run.project_id == project.id
    assert run.purpose == purpose
    assert run.id  # non-empty UUID


def test_create_agent_run_fk_failure_without_explicit_db_path(tmp_path, monkeypatch):
    """Without db_path, writing to a DB that lacks the project row raises."""
    orphan_db = tmp_path / "orphan.db"
    db.init_database(db_path=orphan_db)
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(orphan_db))

    fake_project_id = str(uuid.uuid4())
    with pytest.raises(Exception):
        db.create_agent_run(
            project_id=fake_project_id,
            purpose="fk_failure_test",
        )


# ---------------------------------------------------------------------------
# initialize_project_database
# ---------------------------------------------------------------------------

def test_initialize_project_database_defined_on_orchestrator():
    assert hasattr(orchestrator, "initialize_project_database")
    assert callable(orchestrator.initialize_project_database)


def test_initialize_project_database_explicit_db_path(tmp_path, monkeypatch):
    """Explicit db_path wins over all other resolution mechanisms."""
    explicit = (tmp_path / "explicit.db").resolve()
    result = orchestrator.initialize_project_database(db_path=explicit)
    assert result == explicit
    assert os.environ.get("BOB3_DATABASE_PATH") == str(explicit)


def test_initialize_project_database_env_var(tmp_path, monkeypatch):
    """BOB3_DATABASE_PATH is honoured when no explicit db_path is given."""
    env_db = (tmp_path / "env.db").resolve()
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db))
    result = orchestrator.initialize_project_database()
    assert result == env_db


def test_initialize_project_database_project_path(tmp_path, monkeypatch):
    """When no env var or db_path, the DB is resolved from project_path."""
    monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
    result = orchestrator.initialize_project_database(project_path=tmp_path)
    assert result == (tmp_path / "bob3.db").resolve()
    assert os.environ.get("BOB3_DATABASE_PATH") == str(result)


def test_initialize_project_database_exports_env_var(tmp_path, monkeypatch):
    """The resolved path is always exported to BOB3_DATABASE_PATH."""
    explicit = (tmp_path / "exported.db").resolve()
    monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
    orchestrator.initialize_project_database(db_path=explicit)
    assert os.environ["BOB3_DATABASE_PATH"] == str(explicit)


def test_initialize_project_database_returns_absolute_path(tmp_path, monkeypatch):
    """Return value is always an absolute path."""
    monkeypatch.delenv("BOB3_DATABASE_PATH", raising=False)
    result = orchestrator.initialize_project_database(project_path=tmp_path)
    assert result.is_absolute()
