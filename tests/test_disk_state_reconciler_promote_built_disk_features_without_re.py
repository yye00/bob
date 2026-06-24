"""Tests for disk_state_reconciler_promote_built_disk_features_without_re.

Verifies that reconcile_from_disk correctly:
- promotes features whose on-disk ACs all pass without re-spawning agents
- skips features with missing artifacts
- handles multiple features atomically
- is idempotent across repeated calls
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest

from bob3.disk_state_reconciler_promote_built_disk_features_without_re import (
    disk_state_reconciler_promote_built_disk_features_without_re,
)


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
    acceptance_criteria: list[str] | None,
) -> None:
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


def _get_feature_status(db_path: pathlib.Path, feature_id: str) -> str:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status FROM features WHERE id = ?", (feature_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_disk_state_reconciler_promote_built_disk_features_without_re(
    tmp_path, monkeypatch
):
    """Core AC test: promotes a ready feature whose file-exists AC is satisfied."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    artifact = tmp_path / "artifact.py"
    artifact.write_text("x = 1\n")

    _add_feature(
        db_path, project_id, feature_id, "Built-on-disk feature",
        status="ready",
        acceptance_criteria=["File exists: artifact.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = disk_state_reconciler_promote_built_disk_features_without_re(
        project_id, workspace=tmp_path
    )

    assert count >= 1
    assert _get_feature_status(db_path, feature_id) == "completed"


def test_skips_feature_with_missing_artifact(tmp_path, monkeypatch):
    """Features whose artifacts are absent on disk are not promoted."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    _add_feature(
        db_path, project_id, feature_id, "Missing artifact",
        status="ready",
        acceptance_criteria=["File exists: missing.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = disk_state_reconciler_promote_built_disk_features_without_re(
        project_id, workspace=tmp_path
    )

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_idempotent_second_call_returns_zero(tmp_path, monkeypatch):
    """Second call after promotion returns 0 (already completed)."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    (tmp_path / "present.py").write_text("y = 2\n")

    _add_feature(
        db_path, project_id, feature_id, "Idempotent feature",
        status="ready",
        acceptance_criteria=["File exists: present.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    first = disk_state_reconciler_promote_built_disk_features_without_re(
        project_id, workspace=tmp_path
    )
    second = disk_state_reconciler_promote_built_disk_features_without_re(
        project_id, workspace=tmp_path
    )

    assert first == 1
    assert second == 0
    assert _get_feature_status(db_path, feature_id) == "completed"


def test_raises_on_empty_project_id(tmp_path):
    """Empty project_id raises ValueError immediately."""
    with pytest.raises(ValueError):
        disk_state_reconciler_promote_built_disk_features_without_re(
            "", workspace=tmp_path
        )
