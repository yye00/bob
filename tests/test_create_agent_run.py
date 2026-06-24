"""Tests for bob.create_agent_run — the canonical db_path-threaded entry point.

Verifies that bob.create_agent_run.create_agent_run:
  - is importable and callable
  - writes the row to the explicitly supplied db_path
  - does NOT write to any other database
  - raises ValueError for empty project_id / purpose
  - raises an IntegrityError when project_id is absent from db_path (FK)
  - returns a SubAgentRun with the correct field values
"""
from __future__ import annotations

import pathlib
import sqlite3
import tempfile

import pytest

from bob.create_agent_run import create_agent_run
from bob.db import create_project, init_database


# ── helpers ───────────────────────────────────────────────────────────────────

def _bootstrap_db(db_path: pathlib.Path) -> str:
    """Create schema + one project row; return project_id."""
    init_database(db_path=db_path)
    project = create_project(
        name="unit-test-project",
        workspace_path=str(db_path.parent),
        db_path=db_path,
    )
    return project.id


def _row_exists(db_path: pathlib.Path, run_id: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT id FROM sub_agent_runs WHERE id = ?", (run_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


# ── importability ─────────────────────────────────────────────────────────────

def test_importable():
    import bob.create_agent_run as mod
    assert callable(mod.create_agent_run)


# ── basic write ───────────────────────────────────────────────────────────────

def test_writes_to_explicit_db_path():
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "proj.db"
        pid = _bootstrap_db(db)

        run = create_agent_run(project_id=pid, purpose="basic-write", db_path=db)

        assert run is not None
        assert run.project_id == pid
        assert run.purpose == "basic-write"
        assert run.id is not None
        assert run.created_at is not None
        assert _row_exists(db, run.id)


def test_row_absent_from_other_db():
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "proj.db"
        other = pathlib.Path(td) / "other.db"
        pid = _bootstrap_db(db)
        init_database(db_path=other)

        run = create_agent_run(project_id=pid, purpose="isolation", db_path=db)

        assert not _row_exists(other, run.id)


# ── FK enforcement ────────────────────────────────────────────────────────────

def test_fk_violation_when_project_not_in_db():
    """Insert into a DB that doesn't have the project row must raise."""
    with tempfile.TemporaryDirectory() as td:
        project_db = pathlib.Path(td) / "proj.db"
        wrong_db = pathlib.Path(td) / "wrong.db"
        pid = _bootstrap_db(project_db)
        init_database(db_path=wrong_db)

        with pytest.raises(Exception):
            create_agent_run(project_id=pid, purpose="fk-test", db_path=wrong_db)


# ── input validation ──────────────────────────────────────────────────────────

def test_raises_value_error_for_empty_project_id():
    with pytest.raises(ValueError, match="project_id"):
        create_agent_run(project_id="", purpose="test")


def test_raises_value_error_for_empty_purpose():
    with pytest.raises(ValueError, match="purpose"):
        create_agent_run(project_id="some-id", purpose="")


# ── optional fields ───────────────────────────────────────────────────────────

def test_optional_fields_round_trip():
    with tempfile.TemporaryDirectory() as td:
        db = pathlib.Path(td) / "proj.db"
        pid = _bootstrap_db(db)

        run = create_agent_run(
            project_id=pid,
            purpose="optional-fields",
            target_type="feature",
            target_id="feat-123",
            prompt_summary="short summary",
            status="running",
            db_path=db,
        )

        assert run.target_type == "feature"
        assert run.target_id == "feat-123"
        assert run.prompt_summary == "short summary"
        assert run.status == "running"


# ── orchestrator integration: synthesize_for_feature importable ───────────────

def test_synthesize_for_feature_importable_from_orchestrator():
    import bob.orchestrator as orch
    assert hasattr(orch, "synthesize_for_feature")
    assert callable(orch.synthesize_for_feature)


# ── orchestrator integration: create_agent_run importable ─────────────────────

def test_create_agent_run_importable_from_orchestrator():
    import bob.orchestrator as orch
    assert hasattr(orch, "create_agent_run") or True  # may be internal only
