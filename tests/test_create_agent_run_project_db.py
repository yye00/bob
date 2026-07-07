"""AC tests: create_agent_run MUST write to the project's own database.

Root-cause coverage for the synthesized=0/118 generation failure: when the
agent_run INSERT resolves a *different* SQLite file than the one holding the
project row, the FK (sub_agent_runs.project_id REFERENCES projects(id)) fails
instantly, synthesize_for_feature swallows the exception and returns None, and
every feature falls back to a thin deterministic stub below the score gate.

The fix threads an explicit ``db_path`` from the caller (who already knows the
project_id) through to the INSERT so the write targets the exact same database
the project_id was read from — regardless of cwd or BOB_DATABASE_PATH.

These tests exercise ``bob.db.create_agent_run`` (the AC's canonical entry
point).
"""
from __future__ import annotations

import pathlib
import sqlite3
import tempfile

import pytest

from bob.db import create_agent_run, create_project, init_database


def _make_project_db(db_path: pathlib.Path) -> str:
    """Create a fresh DB with a single project row; return its project_id."""
    init_database(db_path=db_path)
    project = create_project(
        name="proj",
        workspace_path=str(db_path.parent),
        db_path=db_path,
    )
    return project.id


def _row_present(db_path: pathlib.Path, run_id: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT 1 FROM sub_agent_runs WHERE id = ?", (run_id,)
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def test_entry_point_is_bob_db_create_agent_run():
    """AC: Function defined: bob.db.create_agent_run."""
    assert callable(create_agent_run)


def test_row_written_to_project_db():
    """The agent_run row lands in the db_path that holds the project."""
    with tempfile.TemporaryDirectory() as td:
        project_db = pathlib.Path(td) / "project.db"
        project_id = _make_project_db(project_db)

        run = create_agent_run(
            project_id=project_id,
            purpose="synthesize",
            db_path=project_db,
        )

        assert run.project_id == project_id
        assert _row_present(project_db, run.id)


def test_row_not_written_to_cwd_resolved_db(monkeypatch):
    """Explicit db_path must beat a divergent cwd/BOB_DATABASE_PATH db.

    Simulates the original failure: the project lives in project_db, but the
    ambient (cwd/env) database is stale_db. Passing db_path=project_db must
    keep the write on project_db and NOT touch stale_db.
    """
    with tempfile.TemporaryDirectory() as td:
        project_db = pathlib.Path(td) / "project.db"
        project_id = _make_project_db(project_db)

        stale_db = pathlib.Path(td) / "stale.db"
        init_database(db_path=stale_db)
        monkeypatch.setenv("BOB_DATABASE_PATH", str(stale_db))

        run = create_agent_run(
            project_id=project_id,
            purpose="synthesize",
            db_path=project_db,
        )

        assert _row_present(project_db, run.id)
        assert not _row_present(stale_db, run.id)


def test_fk_violation_when_project_absent_from_target_db():
    """Writing to a db that lacks the project row must raise (not silently pass).

    This is the exact condition that used to be swallowed. The fix does not
    hide it — but with correct db_path threading the caller never hits it.
    """
    with tempfile.TemporaryDirectory() as td:
        project_db = pathlib.Path(td) / "project.db"
        project_id = _make_project_db(project_db)

        wrong_db = pathlib.Path(td) / "wrong.db"
        init_database(db_path=wrong_db)

        with pytest.raises(sqlite3.IntegrityError):
            create_agent_run(
                project_id=project_id,
                purpose="synthesize",
                db_path=wrong_db,
            )


def test_missing_project_id_raises_valueerror():
    """Empty project_id is rejected deterministically (error path)."""
    with tempfile.TemporaryDirectory() as td:
        db_path = pathlib.Path(td) / "project.db"
        init_database(db_path=db_path)
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            create_agent_run(project_id="", purpose="x", db_path=db_path)
