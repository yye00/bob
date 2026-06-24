"""Tests for DB path resolution in create_agent_run.

Verifies that create_agent_run writes to an explicit db_path when supplied
rather than silently resolving from cwd or BOB_DATABASE_PATH.
This closes the root cause of synthesized=0/118 FK failures.
"""
import os
import pathlib
import sqlite3
import uuid

import pytest

from bob import db


@pytest.fixture()
def isolated_db(tmp_path):
    """Return an initialized database path in a temp directory."""
    db_path = tmp_path / "project.db"
    db.init_database(db_path=db_path)
    return db_path


@pytest.fixture()
def project_in_db(isolated_db):
    """Create a project row in the isolated database and return (project, db_path)."""
    project = db.create_project(
        name="TestProject",
        workspace_path=str(isolated_db.parent),
        db_path=isolated_db,
    )
    return project, isolated_db


def test_create_agent_run_writes_to_explicit_db_path(project_in_db, tmp_path, monkeypatch):
    """When db_path is supplied, the row lands in THAT database, not the env one."""
    project, project_db = project_in_db
    # Point env var at a DIFFERENT (empty) database
    shadow_db = tmp_path / "shadow.db"
    db.init_database(db_path=shadow_db)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(shadow_db))

    run = db.create_agent_run(
        project_id=project.id,
        purpose="test_explicit_path",
        db_path=project_db,
    )

    # Row must be in project_db
    conn = sqlite3.connect(str(project_db))
    row = conn.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn.close()
    assert row is not None, "agent_run row must exist in the explicitly passed db_path"

    # Row must NOT be in the shadow db
    conn2 = sqlite3.connect(str(shadow_db))
    shadow_row = conn2.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn2.close()
    assert shadow_row is None, "agent_run row must NOT be written to the env-resolved database"


def test_create_agent_run_falls_back_to_env_when_no_db_path(project_in_db, monkeypatch):
    """When db_path is omitted, create_agent_run resolves from BOB_DATABASE_PATH."""
    project, project_db = project_in_db
    monkeypatch.setenv("BOB_DATABASE_PATH", str(project_db))

    run = db.create_agent_run(
        project_id=project.id,
        purpose="test_env_fallback",
        # no db_path — must resolve from env
    )

    conn = sqlite3.connect(str(project_db))
    row = conn.execute("SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)).fetchone()
    conn.close()
    assert row is not None, "agent_run must be written to the BOB_DATABASE_PATH db"


def test_get_database_path_prefers_env_over_cwd(tmp_path, monkeypatch):
    """get_database_path() returns the env-var path when BOB_DATABASE_PATH is set."""
    env_db = tmp_path / "env_db.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(env_db))
    resolved = db.get_database_path()
    assert resolved == env_db


def test_get_database_path_falls_back_to_cwd(tmp_path, monkeypatch):
    """get_database_path() returns cwd/bob.db when env var is not set."""
    monkeypatch.delenv("BOB_DATABASE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    resolved = db.get_database_path()
    assert resolved == tmp_path / "bob.db"


def test_create_agent_run_returns_subagentrun_model(project_in_db):
    """create_agent_run returns a SubAgentRun dataclass with all expected fields."""
    from bob.models import SubAgentRun
    project, project_db = project_in_db

    run = db.create_agent_run(
        project_id=project.id,
        purpose="model_check",
        db_path=project_db,
    )

    assert isinstance(run, SubAgentRun)
    assert run.project_id == project.id
    assert run.purpose == "model_check"
    assert run.status == "running"
    assert run.id is not None
    assert run.created_at is not None


def test_database_path_logged_at_debug(project_in_db, caplog):
    """create_agent_run logs the resolved DB path at DEBUG level."""
    import logging
    project, project_db = project_in_db

    with caplog.at_level(logging.DEBUG, logger="bob.db"):
        db.create_agent_run(
            project_id=project.id,
            purpose="log_check",
            db_path=project_db,
        )

    log_text = caplog.text
    assert str(project_db) in log_text, (
        "create_agent_run must log the resolved db path for observability"
    )
