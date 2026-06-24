"""Idempotency tests for bob.orchestrator.disk_reconciler (feature 2f69b554).

Tests verify that calling reconcile_from_disk multiple times is safe:
- Already-completed features are not double-promoted
- Evidence artifacts are not duplicated
- The promoted count correctly reflects only new promotions each call
- Calling on an empty project is safe
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest

from bob.orchestrator.disk_reconciler import reconcile_from_disk


# ---------------------------------------------------------------------------
# Helpers (duplicated from test_disk_reconciler.py for isolation)
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
        (project_id, "idempotent-test-project", str(db_path.parent), 0.0),
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


def _count_evidence(db_path: pathlib.Path, feature_id: str, ev_type: str) -> int:
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "SELECT COUNT(*) FROM evidence_artifacts WHERE feature_id = ? AND type = ?",
        (feature_id, ev_type),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


# ---------------------------------------------------------------------------
# Idempotency: calling reconcile_from_disk multiple times is safe
# ---------------------------------------------------------------------------


def test_reconcile_idempotent_second_call_returns_zero(tmp_path, monkeypatch):
    """Second call promotes 0 features when first already completed them."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "file.py").write_text("x = 1\n")
    _add_feature(
        db_path, project_id, feature_id, "Idempotent feature",
        status="ready",
        acceptance_criteria=["File exists: file.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    first = reconcile_from_disk(project_id, workspace=tmp_path)
    second = reconcile_from_disk(project_id, workspace=tmp_path)

    assert first == 1
    assert second == 0


def test_reconcile_idempotent_status_stays_completed(tmp_path, monkeypatch):
    """Feature remains 'completed' after multiple reconcile_from_disk calls."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "stable.py").write_text("def foo(): pass\n")
    _add_feature(
        db_path, project_id, feature_id, "Stable feature",
        status="ready",
        acceptance_criteria=["File exists: stable.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    reconcile_from_disk(project_id, workspace=tmp_path)
    reconcile_from_disk(project_id, workspace=tmp_path)
    reconcile_from_disk(project_id, workspace=tmp_path)

    assert _get_feature_status(db_path, feature_id) == "completed"


def test_reconcile_idempotent_no_duplicate_evidence(tmp_path, monkeypatch):
    """Calling reconcile_from_disk multiple times does NOT duplicate evidence artifacts."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "ev.py").write_text("x = 1\n")
    _add_feature(
        db_path, project_id, feature_id, "Evidence dedup",
        status="ready",
        acceptance_criteria=["File exists: ev.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    reconcile_from_disk(project_id, workspace=tmp_path)
    reconcile_from_disk(project_id, workspace=tmp_path)

    count = _count_evidence(db_path, feature_id, "disk_reconciliation")
    assert count == 1


def test_reconcile_idempotent_empty_project_is_safe(tmp_path, monkeypatch):
    """Calling reconcile_from_disk on a project with no features never raises."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    for _ in range(3):
        count = reconcile_from_disk(project_id, workspace=tmp_path)
        assert count == 0


def test_reconcile_idempotent_partial_promotion(tmp_path, monkeypatch):
    """Only newly-passing features are promoted on repeated calls."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    f_pass = str(uuid.uuid4())
    f_fail = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "present.py").write_text("x = 1\n")

    _add_feature(db_path, project_id, f_pass, "Passing", "ready",
                 ["File exists: present.py"])
    _add_feature(db_path, project_id, f_fail, "Initially failing", "ready",
                 ["File exists: absent.py"])

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    first = reconcile_from_disk(project_id, workspace=tmp_path)
    assert first == 1
    assert _get_feature_status(db_path, f_pass) == "completed"
    assert _get_feature_status(db_path, f_fail) == "ready"

    # Now satisfy the second feature's AC
    (tmp_path / "absent.py").write_text("y = 2\n")
    second = reconcile_from_disk(project_id, workspace=tmp_path)
    assert second == 1
    assert _get_feature_status(db_path, f_fail) == "completed"

    # Third call: nothing left to promote
    third = reconcile_from_disk(project_id, workspace=tmp_path)
    assert third == 0


def test_reconcile_idempotent_multiple_features_no_double_count(tmp_path, monkeypatch):
    """Multiple calls only count each feature once across all calls."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    ids = [str(uuid.uuid4()) for _ in range(5)]
    _add_project(db_path, project_id)

    for i, fid in enumerate(ids):
        fname = f"feat{i}.py"
        (tmp_path / fname).write_text("x = 1\n")
        _add_feature(db_path, project_id, fid, f"Feature {i}", "ready",
                     [f"File exists: {fname}"])

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    total = 0
    for _ in range(4):
        total += reconcile_from_disk(project_id, workspace=tmp_path)

    # All 5 promoted exactly once across 4 calls
    assert total == 5
    for fid in ids:
        assert _get_feature_status(db_path, fid) == "completed"
