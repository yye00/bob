"""Tests for disk_state_reconciler.reconcile_from_disk (feature 91320c77).

Tests cover:
- reconcile_from_disk promotes features whose all ACs pass on disk
- reconcile_from_disk skips features with failing ACs
- reconcile_from_disk creates disk_reconciliation evidence on promotion
- reconcile_from_disk is idempotent
- reconcile_from_disk only considers 'ready' and 'pending' features
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest

from disk_state_reconciler import reconcile_from_disk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: pathlib.Path) -> pathlib.Path:
    from bob import db as bob_db
    db_path = tmp_path / "bob.db"
    bob_db.init_database(db_path=db_path)
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
    return row[0] if row else "not_found"


def _get_evidence_types(db_path: pathlib.Path, feature_id: str) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT type FROM evidence_artifacts WHERE feature_id = ?", (feature_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_reconcile_promotes_feature_with_file_exists_ac(tmp_path, monkeypatch):
    """reconcile_from_disk promotes a 'ready' feature when its File exists AC passes."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    target_file = tmp_path / "my_module.py"
    target_file.write_text("# module\n")

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "test-feature", "ready",
                 [f"File exists: my_module.py"])

    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 1
    assert _get_feature_status(db_path, feature_id) == "completed"


def test_reconcile_skips_feature_with_missing_file(tmp_path, monkeypatch):
    """reconcile_from_disk skips a feature when a File exists AC fails."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "test-feature", "ready",
                 ["File exists: nonexistent_file.py"])

    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_reconcile_creates_evidence_artifact(tmp_path, monkeypatch):
    """reconcile_from_disk records a disk_reconciliation evidence artifact on promotion."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    target_file = tmp_path / "artifact.py"
    target_file.write_text("# artifact\n")

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "test-feature", "ready",
                 [f"File exists: artifact.py"])

    reconcile_from_disk(project_id, workspace=tmp_path)

    evidence_types = _get_evidence_types(db_path, feature_id)
    assert "disk_reconciliation" in evidence_types


def test_reconcile_is_idempotent(tmp_path, monkeypatch):
    """Calling reconcile_from_disk twice only promotes each feature once."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    target_file = tmp_path / "stable.py"
    target_file.write_text("# stable\n")

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "test-feature", "ready",
                 [f"File exists: stable.py"])

    count1 = reconcile_from_disk(project_id, workspace=tmp_path)
    count2 = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count1 == 1
    assert count2 == 0


def test_reconcile_skips_completed_features(tmp_path, monkeypatch):
    """reconcile_from_disk does not touch features already in 'completed'."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    target_file = tmp_path / "done.py"
    target_file.write_text("# done\n")

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "already-completed", "completed",
                 [f"File exists: done.py"])

    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0


def test_reconcile_promotes_pending_feature(tmp_path, monkeypatch):
    """reconcile_from_disk promotes 'pending' features as well as 'ready' ones."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    target_file = tmp_path / "pending_artifact.py"
    target_file.write_text("# pending\n")

    _add_project(db_path, project_id)
    _add_feature(db_path, project_id, feature_id, "pending-feature", "pending",
                 [f"File exists: pending_artifact.py"])

    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 1
    assert _get_feature_status(db_path, feature_id) == "completed"


def test_reconcile_returns_count_of_promoted(tmp_path, monkeypatch):
    """reconcile_from_disk returns the integer count of features promoted."""
    db_path = _make_db(tmp_path)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    project_id = str(uuid.uuid4())

    _add_project(db_path, project_id)

    # Add 3 features: 2 with satisfied ACs, 1 with failing AC
    for i in range(2):
        fid = str(uuid.uuid4())
        f = tmp_path / f"mod_{i}.py"
        f.write_text(f"# mod {i}\n")
        _add_feature(db_path, project_id, fid, f"feat-{i}", "ready",
                     [f"File exists: mod_{i}.py"])

    fid_fail = str(uuid.uuid4())
    _add_feature(db_path, project_id, fid_fail, "feat-fail", "ready",
                 ["File exists: missing_file.py"])

    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 2
