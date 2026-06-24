"""Tests that disk_reconciler skips features when required artifacts are missing."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest

from bob.orchestrator.disk_reconciler import reconcile_from_disk


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
        (project_id, "skip-test-project", str(db_path.parent), 0.0),
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


def test_skips_when_file_artifact_missing(tmp_path, monkeypatch):
    """Feature is not promoted when a required file artifact does not exist."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    # Do NOT create the required file artifact.

    _add_feature(
        db_path, project_id, feature_id, "Missing artifact feature",
        status="ready",
        acceptance_criteria=["File exists: src/missing_module.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_skips_when_function_artifact_missing(tmp_path, monkeypatch):
    """Feature is not promoted when required function is absent from disk."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    # File exists but does NOT define the function.
    (tmp_path / "mymod.py").write_text("x = 1\n")

    _add_feature(
        db_path, project_id, feature_id, "Missing function feature",
        status="ready",
        acceptance_criteria=["Function defined: mymod.nonexistent_fn"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_skips_when_one_of_many_artifacts_missing(tmp_path, monkeypatch):
    """Feature is not promoted when even one of many artifacts is missing."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    # First file present, second missing.
    (tmp_path / "present1.py").write_text("x = 1\n")
    (tmp_path / "present2.py").write_text("y = 2\n")
    # absent3.py intentionally not created.

    _add_feature(
        db_path, project_id, feature_id, "Partial artifacts",
        status="ready",
        acceptance_criteria=[
            "File exists: present1.py",
            "File exists: present2.py",
            "File exists: absent3.py",
        ],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_skips_when_pytest_artifact_missing(tmp_path, monkeypatch):
    """Feature is not promoted when a required pytest file does not exist."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    # Do NOT create the test file.

    _add_feature(
        db_path, project_id, feature_id, "Missing pytest artifact",
        status="ready",
        acceptance_criteria=["pytest: tests/test_nonexistent.py"],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_promotes_when_all_artifacts_present(tmp_path, monkeypatch):
    """Feature IS promoted once all artifacts are present on disk."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")

    _add_feature(
        db_path, project_id, feature_id, "All artifacts present",
        status="ready",
        acceptance_criteria=[
            "File exists: a.py",
            "File exists: b.py",
        ],
    )

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 1
    assert _get_feature_status(db_path, feature_id) == "completed"
