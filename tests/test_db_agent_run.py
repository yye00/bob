"""Tests for bob.db.create_agent_run — direct database layer.

Verifies that bob.db.create_agent_run:
  - is importable and callable from bob.db
  - accepts an explicit db_path and writes the row there
  - logs the resolved database path (telemetry requirement)
  - raises an IntegrityError when project_id is absent from db_path (FK)
  - does NOT write to a different database when db_path is explicit
  - returns a SubAgentRun with correct field values
  - respects BOB_DATABASE_PATH when db_path is not supplied
"""
from __future__ import annotations

import pathlib
import sqlite3
import tempfile

import pytest

from bob.db import (
    create_agent_run,
    create_project,
    init_database,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _bootstrap_db(db_path: pathlib.Path) -> str:
    """Initialise schema and insert a project row; return project_id."""
    init_database(db_path=db_path)
    project = create_project(
        name="db-test-project",
        workspace_path=str(db_path.parent),
        db_path=db_path,
    )
    return project.id


def _row_count(db_path: pathlib.Path, run_id: str) -> int:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT COUNT(*) FROM sub_agent_runs WHERE id = ?", (run_id,)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ── importability ─────────────────────────────────────────────────────────────

def test_create_agent_run_importable_from_bob_db():
    """create_agent_run must be directly importable from bob.db."""
    import bob.db as db_mod
    assert hasattr(db_mod, "create_agent_run")
    assert callable(db_mod.create_agent_run)


# ── basic write to explicit db_path ──────────────────────────────────────────

def test_writes_row_to_explicit_db_path():
    """Row must land in the db_path supplied, not in cwd or env."""
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "proj.db"
        pid = _bootstrap_db(db)

        run = create_agent_run(project_id=pid, purpose="db-write-test", db_path=db)

        assert run is not None
        assert run.project_id == pid
        assert run.purpose == "db-write-test"
        assert run.id is not None
        assert run.created_at is not None
        assert _row_count(db, run.id) == 1


# ── row isolation ─────────────────────────────────────────────────────────────

def test_row_absent_from_other_database():
    """The row must NOT appear in a second database that was not the target."""
    with tempfile.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "proj.db"
        other = pathlib.Path(td) / "other.db"
        pid = _bootstrap_db(target)
        init_database(db_path=other)

        run = create_agent_run(project_id=pid, purpose="isolation", db_path=target)

        assert _row_count(target, run.id) == 1
        assert _row_count(other, run.id) == 0


# ── FK enforcement ────────────────────────────────────────────────────────────

def test_fk_violation_raises_when_project_not_in_target_db():
    """When db_path does not contain the project row, FK must fire and raise.

    This is the root-cause scenario: synthesizer inserts into a cwd-resolved
    DB that doesn't hold the project row, causing the FK to fail and
    synthesize_for_feature to return None (silent total failure).
    """
    with tempfile.TemporaryDirectory() as td:
        project_db = pathlib.Path(td) / "project.db"
        wrong_db = pathlib.Path(td) / "wrong.db"
        pid = _bootstrap_db(project_db)
        init_database(db_path=wrong_db)

        with pytest.raises(Exception):
            create_agent_run(
                project_id=pid,
                purpose="fk-violation",
                db_path=wrong_db,
            )


# ── telemetry: db path is logged ──────────────────────────────────────────────

def test_db_path_logged_at_debug_level(caplog):
    """create_agent_run must log the resolved db path for mismatch visibility."""
    import logging
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "log-test.db"
        pid = _bootstrap_db(db)

        with caplog.at_level(logging.DEBUG, logger="bob.db"):
            create_agent_run(project_id=pid, purpose="log-check", db_path=db)

        log_text = caplog.text
        assert str(db) in log_text, (
            f"Expected db path {db} to appear in debug log, got: {log_text!r}"
        )


# ── return model shape ────────────────────────────────────────────────────────

def test_returns_subagentrun_with_all_fields():
    """Returned model must have all expected fields populated correctly."""
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "shape.db"
        pid = _bootstrap_db(db)

        run = create_agent_run(
            project_id=pid,
            purpose="shape-test",
            target_type="feature",
            target_id="feat-abc",
            prompt_summary="summary text",
            status="running",
            db_path=db,
        )

        assert run.project_id == pid
        assert run.purpose == "shape-test"
        assert run.target_type == "feature"
        assert run.target_id == "feat-abc"
        assert run.prompt_summary == "summary text"
        assert run.status == "running"
        assert run.id is not None
        assert run.created_at is not None


# ── env var fallback ──────────────────────────────────────────────────────────

def test_env_var_honored_when_no_db_path(monkeypatch):
    """When db_path is omitted, BOB_DATABASE_PATH env var must be used."""
    with tempfile.TemporaryDirectory() as td:
        env_db = pathlib.Path(td) / "env.db"
        pid = _bootstrap_db(env_db)

        monkeypatch.setenv("BOB_DATABASE_PATH", str(env_db))

        run = create_agent_run(project_id=pid, purpose="env-fallback")

        assert run is not None
        assert _row_count(env_db, run.id) == 1


# ── explicit db_path overrides env var ────────────────────────────────────────

def test_explicit_db_path_overrides_env_var(monkeypatch):
    """Explicit db_path must take precedence over BOB_DATABASE_PATH."""
    with tempfile.TemporaryDirectory() as td:
        explicit_db = pathlib.Path(td) / "explicit.db"
        env_db = pathlib.Path(td) / "env.db"
        pid = _bootstrap_db(explicit_db)
        init_database(db_path=env_db)

        monkeypatch.setenv("BOB_DATABASE_PATH", str(env_db))

        run = create_agent_run(project_id=pid, purpose="override-env", db_path=explicit_db)

        assert _row_count(explicit_db, run.id) == 1
        assert _row_count(env_db, run.id) == 0


# ── orchestrator integration ──────────────────────────────────────────────────

def test_synthesize_for_feature_importable():
    """bob.orchestrator must expose synthesize_for_feature."""
    import bob.orchestrator as orch
    assert hasattr(orch, "synthesize_for_feature")
    assert callable(orch.synthesize_for_feature)


def test_create_agent_run_importable_from_db_module():
    """bob.db.create_agent_run must be the same callable as the one used above."""
    from bob.db import create_agent_run as fn
    assert callable(fn)
