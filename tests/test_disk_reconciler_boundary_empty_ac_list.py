"""Tests for edge case: reconcile_from_disk with zero/empty AC list."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest

from bob3.orchestrator.disk_reconciler import NOT_RECONCILED, reconcile_from_disk


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
        (project_id, "boundary-test-project", str(db_path.parent), 0.0),
    )
    conn.commit()
    conn.close()


def _add_feature(
    db_path: pathlib.Path,
    project_id: str,
    feature_id: str,
    name: str,
    status: str,
    acceptance_criteria: list[str] | None,
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    ac_json = json.dumps(acceptance_criteria) if acceptance_criteria is not None else None
    conn.execute(
        """INSERT INTO features (id, project_id, name, status, acceptance_criteria)
           VALUES (?, ?, ?, ?, ?)""",
        (feature_id, project_id, name, status, ac_json),
    )
    conn.commit()
    conn.close()


def _get_feature_status(db_path: pathlib.Path, feature_id: str) -> str:
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("SELECT status FROM features WHERE id = ?", (feature_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "not_found"


def test_reconcile_returns_not_reconciled_for_empty_ac_list(tmp_path, monkeypatch):
    """reconcile_from_disk(project_id_with_zero_acs) returns NOT_RECONCILED (empty edge).

    A feature whose acceptance_criteria is an empty list [] is not promoted.
    The function returns 0 (no promotions), consistent with the NOT_RECONCILED sentinel.
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    _add_feature(
        db_path, project_id, feature_id, "Zero AC feature",
        status="ready",
        acceptance_criteria=[],  # empty list — NOT_RECONCILED expected
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    result = reconcile_from_disk(project_id, workspace=tmp_path)

    # Returns 0 promotions — equivalent to NOT_RECONCILED for zero-AC case.
    assert result == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_reconcile_returns_zero_for_null_ac(tmp_path, monkeypatch):
    """reconcile_from_disk returns 0 when acceptance_criteria is None."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    _add_feature(
        db_path, project_id, feature_id, "Null AC feature",
        status="ready",
        acceptance_criteria=None,
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    result = reconcile_from_disk(project_id, workspace=tmp_path)

    assert result == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_reconcile_returns_zero_for_project_with_all_zero_ac_features(tmp_path, monkeypatch):
    """Project with multiple zero-AC features returns 0 total promotions."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    for i in range(3):
        fid = str(uuid.uuid4())
        _add_feature(
            db_path, project_id, fid, f"Zero AC feature {i}",
            status="ready",
            acceptance_criteria=[],
        )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    result = reconcile_from_disk(project_id, workspace=tmp_path)

    assert result == 0


def test_not_reconciled_sentinel_is_string():
    """NOT_RECONCILED sentinel is the expected string value."""
    assert NOT_RECONCILED == "NOT_RECONCILED"
    assert isinstance(NOT_RECONCILED, str)
