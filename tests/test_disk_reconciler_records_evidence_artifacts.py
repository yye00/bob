"""Tests that disk_reconciler records disk_reconciliation evidence artifacts."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest

from bob.orchestrator.disk_reconciler import (
    promote_to_completed,
    reconcile_from_disk,
)


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
        (project_id, "evidence-test-project", str(db_path.parent), 0.0),
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


def _get_evidence(db_path: pathlib.Path, feature_id: str, ev_type: str) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "SELECT content FROM evidence_artifacts WHERE feature_id = ? AND type = ?",
        (feature_id, ev_type),
    )
    rows = cur.fetchall()
    conn.close()
    return [json.loads(r[0]) for r in rows]


def test_reconcile_records_disk_reconciliation_evidence(tmp_path, monkeypatch):
    """Promotion creates a 'disk_reconciliation' evidence artifact."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "myfile.py").write_text("x = 1\n")
    _add_feature(
        db_path, project_id, feature_id, "Evidence feature",
        status="ready",
        acceptance_criteria=["File exists: myfile.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    reconcile_from_disk(project_id, workspace=tmp_path)

    evidence = _get_evidence(db_path, feature_id, "disk_reconciliation")
    assert len(evidence) == 1


def test_evidence_contains_feature_id(tmp_path, monkeypatch):
    """Evidence artifact JSON contains the feature_id field."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "f.py").write_text("x = 1\n")
    _add_feature(
        db_path, project_id, feature_id, "ID check",
        status="ready",
        acceptance_criteria=["File exists: f.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    reconcile_from_disk(project_id, workspace=tmp_path)

    evidence = _get_evidence(db_path, feature_id, "disk_reconciliation")
    assert evidence[0]["feature_id"] == feature_id


def test_evidence_contains_checks_list(tmp_path, monkeypatch):
    """Evidence artifact JSON contains a 'checks' list with criterion results."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "check.py").write_text("x = 1\n")
    _add_feature(
        db_path, project_id, feature_id, "Checks list",
        status="ready",
        acceptance_criteria=["File exists: check.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    reconcile_from_disk(project_id, workspace=tmp_path)

    evidence = _get_evidence(db_path, feature_id, "disk_reconciliation")
    checks = evidence[0]["checks"]
    assert isinstance(checks, list)
    assert len(checks) >= 1
    assert checks[0]["criterion"] == "File exists: check.py"
    assert checks[0]["passed"] is True


def test_evidence_not_recorded_when_ac_fails(tmp_path, monkeypatch):
    """No evidence artifact is created when promotion is refused."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    # Do NOT create the file.
    _add_feature(
        db_path, project_id, feature_id, "Failing feature",
        status="ready",
        acceptance_criteria=["File exists: absent.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    reconcile_from_disk(project_id, workspace=tmp_path)

    evidence = _get_evidence(db_path, feature_id, "disk_reconciliation")
    assert len(evidence) == 0


def test_promote_to_completed_records_evidence(tmp_path, monkeypatch):
    """promote_to_completed directly records a disk_reconciliation evidence artifact."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    _add_feature(
        db_path, project_id, feature_id, "Direct promote",
        status="ready",
        acceptance_criteria=None,
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    checks = [{"criterion": "File exists: x.py", "passed": True, "detail": "ok"}]
    result = promote_to_completed(project_id, feature_id, "Direct promote", checks)

    assert result is True
    evidence = _get_evidence(db_path, feature_id, "disk_reconciliation")
    assert len(evidence) == 1
    assert evidence[0]["feature_id"] == feature_id
    assert evidence[0]["checks"] == checks


def test_evidence_has_reconciled_at_timestamp(tmp_path, monkeypatch):
    """Evidence artifact JSON contains a 'reconciled_at' timestamp string."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "ts.py").write_text("x = 1\n")
    _add_feature(
        db_path, project_id, feature_id, "Timestamp",
        status="ready",
        acceptance_criteria=["File exists: ts.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    reconcile_from_disk(project_id, workspace=tmp_path)

    evidence = _get_evidence(db_path, feature_id, "disk_reconciliation")
    assert "reconciled_at" in evidence[0]
    assert isinstance(evidence[0]["reconciled_at"], str)
    assert len(evidence[0]["reconciled_at"]) > 0
