"""Tests for update_project_name_if_mismatch and verify_project_name_matches_dir."""
from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from bob3 import db as bob3_db
from bob3.orchestrator.project_metadata_check import (
    WorkspaceBasenameMissingError,
    update_project_name_if_mismatch,
    verify_project_name_matches_dir,
)


def _make_db(tmp_path: Path, name: str = "bob9") -> Path:
    db_path = tmp_path / "bob3.db"
    bob3_db.init_database(db_path=db_path)
    project_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO projects (id, name, workspace_path, spec_path, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, name, str(tmp_path), None, "planning"),
    )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# verify_project_name_matches_dir
# ---------------------------------------------------------------------------

def test_verify_returns_true_when_name_matches(tmp_path):
    """Returns True when stored name equals workspace basename."""
    workspace = tmp_path / tmp_path.name
    workspace.mkdir(exist_ok=True)
    db_path = _make_db(workspace, name=workspace.name)

    result = verify_project_name_matches_dir(db_path=db_path, workspace=workspace)
    assert result is True


def test_verify_returns_false_when_name_differs(tmp_path):
    """Returns False when stored name does not match workspace basename."""
    db_path = _make_db(tmp_path, name="stale_bob_name")
    result = verify_project_name_matches_dir(db_path=db_path, workspace=tmp_path)
    assert result is False


def test_verify_returns_false_when_no_projects_row(tmp_path):
    """Returns False when there are no project rows in the DB."""
    db_path = tmp_path / "bob3.db"
    bob3_db.init_database(db_path=db_path)
    result = verify_project_name_matches_dir(db_path=db_path, workspace=tmp_path)
    assert result is False


# ---------------------------------------------------------------------------
# update_project_name_if_mismatch
# ---------------------------------------------------------------------------

def test_update_fixes_stale_name(tmp_path):
    """Atomically updates stale name to match workspace basename."""
    db_path = _make_db(tmp_path, name="old_bob_name")

    updated = update_project_name_if_mismatch(db_path=db_path, workspace=tmp_path)
    assert updated is True

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
    conn.close()

    assert row[0] == tmp_path.name, f"Expected {tmp_path.name!r}, got {row[0]!r}"


def test_update_noop_when_name_already_correct(tmp_path):
    """Returns False without writing when name already matches."""
    db_path = _make_db(tmp_path, name=tmp_path.name)

    updated = update_project_name_if_mismatch(db_path=db_path, workspace=tmp_path)
    assert updated is False


def test_update_returns_false_when_no_project_row(tmp_path):
    """Returns False when the projects table is empty."""
    db_path = tmp_path / "bob3.db"
    bob3_db.init_database(db_path=db_path)

    updated = update_project_name_if_mismatch(db_path=db_path, workspace=tmp_path)
    assert updated is False


def test_update_name_is_idempotent(tmp_path):
    """Calling update twice is safe; second call returns False."""
    db_path = _make_db(tmp_path, name="old_name")

    first = update_project_name_if_mismatch(db_path=db_path, workspace=tmp_path)
    second = update_project_name_if_mismatch(db_path=db_path, workspace=tmp_path)

    assert first is True
    assert second is False


def test_update_raises_when_workspace_has_no_basename():
    """Raises WorkspaceBasenameMissingError for root-like paths with no basename."""
    root_like = Path("/")
    with pytest.raises(WorkspaceBasenameMissingError):
        update_project_name_if_mismatch(workspace=root_like, db_path=Path("/nonexistent/bob3.db"))
