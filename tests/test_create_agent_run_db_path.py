"""Tests for create_agent_run db_path threading.

Verifies that bob3.database.create_agent_run writes to the explicitly
supplied db_path rather than the cwd-resolved one. This is the root-cause
fix for the synthesized=0/118 generation failure: when cwd diverges from
the project database, FK constraints (sub_agent_runs.project_id REFERENCES
projects(id)) fail silently and synthesize_for_feature returns None.
"""
from __future__ import annotations

import os
import pathlib
import sqlite3
import tempfile

import pytest

import bob3.database as db_module
from bob3.database import create_agent_run
from bob3.db import create_project, init_database


def _make_project_db(db_path: pathlib.Path) -> str:
    """Initialize a fresh SQLite DB, insert a project row, return project_id."""
    init_database(db_path=db_path)
    project = create_project(
        name="test-project",
        workspace_path=str(db_path.parent),
        db_path=db_path,
    )
    return project.id


# ── importability ─────────────────────────────────────────────────────────────

def test_create_agent_run_importable_from_database():
    """bob3.database.create_agent_run must be importable and callable."""
    assert hasattr(db_module, "create_agent_run")
    assert callable(db_module.create_agent_run)


# ── correct db_path threading ─────────────────────────────────────────────────

def test_create_agent_run_writes_to_explicit_db_path():
    """Row must land in the db_path file, not in the cwd db."""
    with tempfile.TemporaryDirectory() as td:
        target_db = pathlib.Path(td) / "project.db"
        project_id = _make_project_db(target_db)

        # A second db in a different location — simulates a stale cwd db.
        stale_db = pathlib.Path(td) / "stale.db"

        run = create_agent_run(
            project_id=project_id,
            purpose="test-purpose",
            db_path=target_db,
        )

        assert run is not None
        assert run.project_id == project_id
        assert run.purpose == "test-purpose"

        # Confirm the row is physically present in target_db.
        conn = sqlite3.connect(str(target_db))
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.execute(
            "SELECT id, project_id FROM sub_agent_runs WHERE id = ?", (run.id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "create_agent_run row must exist in target_db"
        assert row[1] == project_id


def test_create_agent_run_row_absent_from_other_db():
    """The row must NOT appear in a second db that was not the target."""
    with tempfile.TemporaryDirectory() as td:
        target_db = pathlib.Path(td) / "project.db"
        project_id = _make_project_db(target_db)

        other_db = pathlib.Path(td) / "other.db"
        init_database(db_path=other_db)

        run = create_agent_run(
            project_id=project_id,
            purpose="isolation-check",
            db_path=target_db,
        )

        conn = sqlite3.connect(str(other_db))
        cursor = conn.execute(
            "SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is None, "Row must not leak into other_db"


def test_create_agent_run_fk_violation_when_db_mismatch():
    """Insert targeting a DB that does not hold the project row must raise.

    This is the original silent-failure scenario: project lives in DB-A,
    synthesizer inserts into DB-B (cwd-resolved), FK fails, synthesize_for_feature
    catches and returns None.
    """
    with tempfile.TemporaryDirectory() as td:
        project_db = pathlib.Path(td) / "project.db"
        project_id = _make_project_db(project_db)

        # A separate, empty DB — project_id does not exist here.
        wrong_db = pathlib.Path(td) / "wrong.db"
        init_database(db_path=wrong_db)

        with pytest.raises(Exception):
            # FK (sub_agent_runs.project_id REFERENCES projects(id)) must fire.
            create_agent_run(
                project_id=project_id,
                purpose="fk-violation-test",
                db_path=wrong_db,
            )


def test_create_agent_run_returns_subagentrun_model():
    """create_agent_run must return a SubAgentRun-like model with correct fields."""
    with tempfile.TemporaryDirectory() as td:
        db_path = pathlib.Path(td) / "test.db"
        project_id = _make_project_db(db_path)

        run = create_agent_run(
            project_id=project_id,
            purpose="model-shape-check",
            db_path=db_path,
        )

        assert run.project_id == project_id
        assert run.purpose == "model-shape-check"
        assert run.id is not None
        assert run.created_at is not None


def test_create_agent_run_env_var_respected_when_no_db_path(monkeypatch):
    """When db_path is omitted, BOB3_DATABASE_PATH env var must be honored."""
    with tempfile.TemporaryDirectory() as td:
        env_db = pathlib.Path(td) / "env.db"
        project_id = _make_project_db(env_db)

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db))

        run = create_agent_run(
            project_id=project_id,
            purpose="env-var-resolution",
        )

        assert run is not None
        assert run.project_id == project_id

        conn = sqlite3.connect(str(env_db))
        cursor = conn.execute(
            "SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "Row must land in the BOB3_DATABASE_PATH db"


def test_create_agent_run_db_path_overrides_env_var(monkeypatch):
    """Explicit db_path must override BOB3_DATABASE_PATH."""
    with tempfile.TemporaryDirectory() as td:
        explicit_db = pathlib.Path(td) / "explicit.db"
        env_db = pathlib.Path(td) / "env.db"

        project_id = _make_project_db(explicit_db)
        init_database(db_path=env_db)

        monkeypatch.setenv("BOB3_DATABASE_PATH", str(env_db))

        run = create_agent_run(
            project_id=project_id,
            purpose="override-env",
            db_path=explicit_db,
        )

        assert run is not None

        # Row must be in explicit_db, NOT in env_db.
        conn_explicit = sqlite3.connect(str(explicit_db))
        row_explicit = conn_explicit.execute(
            "SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)
        ).fetchone()
        conn_explicit.close()

        conn_env = sqlite3.connect(str(env_db))
        row_env = conn_env.execute(
            "SELECT id FROM sub_agent_runs WHERE id = ?", (run.id,)
        ).fetchone()
        conn_env.close()

        assert row_explicit is not None, "Row must be in explicit_db"
        assert row_env is None, "Row must NOT be in env_db when db_path is explicit"


# ── synthesize_for_feature importability ─────────────────────────────────────

def test_synthesize_for_feature_importable_from_orchestrator():
    """bob3.orchestrator.synthesize_for_feature must be importable."""
    import bob3.orchestrator as orch
    assert hasattr(orch, "synthesize_for_feature"), (
        "synthesize_for_feature must be accessible via bob3.orchestrator"
    )
    assert callable(orch.synthesize_for_feature)
