"""Boundary tests for disk_state_reconciler.reconcile_from_disk (feature 91320c77).

Empty, zero, or minimum inputs return a well-defined result rather than raising.
"""

from __future__ import annotations

import pathlib
import sqlite3
import uuid

import pytest

from disk_state_reconciler import reconcile_from_disk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: pathlib.Path) -> pathlib.Path:
    from bob3 import db as bob3_db
    db_path = tmp_path / "bob3.db"
    bob3_db.init_database(db_path=db_path)
    return db_path


def _add_project(db_path: pathlib.Path, project_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO projects (id, name, workspace_path, total_cost_usd) VALUES (?, ?, ?, ?)",
        (project_id, "test-project", str(db_path.parent), 0.0),
    )
    conn.commit()
    conn.close()


def _add_feature(
    db_path: pathlib.Path,
    project_id: str,
    feature_id: str,
    name: str,
    status: str,
    acceptance_criteria,
) -> None:
    import json
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    ac_json = json.dumps(acceptance_criteria) if acceptance_criteria is not None else None
    conn.execute(
        "INSERT INTO features (id, project_id, name, status, acceptance_criteria) "
        "VALUES (?, ?, ?, ?, ?)",
        (feature_id, project_id, name, status, ac_json),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------

def test_reconcile_project_with_no_features_returns_zero(tmp_path, monkeypatch):
    """reconcile_from_disk returns 0 (not raises) for a project with no features."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    result = reconcile_from_disk(project_id, workspace=tmp_path)

    assert result == 0


def test_reconcile_feature_with_empty_ac_list_returns_zero(tmp_path, monkeypatch):
    """reconcile_from_disk skips features whose AC list is empty []."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "empty-ac-feature", "ready", [])

    result = reconcile_from_disk(project_id, workspace=tmp_path)

    assert result == 0


def test_reconcile_feature_with_null_ac_returns_zero(tmp_path, monkeypatch):
    """reconcile_from_disk skips features whose acceptance_criteria is NULL."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "null-ac-feature", "ready", None)

    result = reconcile_from_disk(project_id, workspace=tmp_path)

    assert result == 0


def test_reconcile_with_minimum_single_ac_that_passes(tmp_path, monkeypatch):
    """reconcile_from_disk with exactly one passing AC promotes the feature."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    sentinel = tmp_path / "minimal.py"
    sentinel.write_text("# minimal\n")

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "minimal-feature", "ready",
                 ["File exists: minimal.py"])

    result = reconcile_from_disk(project_id, workspace=tmp_path)

    assert result == 1


def test_reconcile_returns_int_not_none(tmp_path, monkeypatch):
    """reconcile_from_disk always returns an int, not None."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    result = reconcile_from_disk(project_id, workspace=tmp_path)

    assert isinstance(result, int)
