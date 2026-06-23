"""Tests that disk_reconciler refuses promotion when any integration AC regresses."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest

from bob3.orchestrator.disk_reconciler import (
    NOT_RECONCILED,
    handle_failing_integration_ac,
    reconcile_from_disk,
)


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
        (project_id, "integration-test-project", str(db_path.parent), 0.0),
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


# ---------------------------------------------------------------------------
# handle_failing_integration_ac unit tests
# ---------------------------------------------------------------------------


def test_handle_failing_integration_ac_returns_not_reconciled_on_failure(tmp_path):
    """Returns NOT_RECONCILED when an integration AC fails on disk."""
    # No pkg file present — integration check will fail.
    criteria = ["integration: bob3.nonexistent.module"]
    result = handle_failing_integration_ac(criteria, tmp_path)
    assert result == NOT_RECONCILED


def test_handle_failing_integration_ac_returns_ok_when_wired(tmp_path):
    """Returns 'OK' when an integration criterion passes (module imported)."""
    pkg = tmp_path / "src" / "bob3" / "mypkg2"
    pkg.mkdir(parents=True)
    (pkg / "mod2.py").write_text("def foo(): pass\n")
    caller = tmp_path / "src" / "bob3" / "caller2.py"
    caller.write_text("from bob3.mypkg2.mod2 import foo\n")
    criteria = ["integration: bob3.mypkg2.mod2"]
    result = handle_failing_integration_ac(criteria, tmp_path)
    assert result == "OK"


def test_handle_failing_integration_ac_ignores_non_integration_criteria(tmp_path):
    """Non-integration criteria are ignored by handle_failing_integration_ac."""
    # No files at all, but the only criterion is 'File exists:' — should return OK.
    criteria = ["File exists: whatever.py"]
    result = handle_failing_integration_ac(criteria, tmp_path)
    assert result == "OK"


def test_handle_failing_integration_ac_empty_criteria(tmp_path):
    """Empty criterion list returns 'OK'."""
    result = handle_failing_integration_ac([], tmp_path)
    assert result == "OK"


def test_handle_failing_integration_ac_mixed_returns_not_reconciled_on_fail(tmp_path):
    """Returns NOT_RECONCILED even if only one of multiple integration ACs fails."""
    # First integration AC is wired, second is not.
    pkg = tmp_path / "src" / "bob3" / "wired"
    pkg.mkdir(parents=True)
    (pkg / "mod.py").write_text("def bar(): pass\n")
    caller = tmp_path / "src" / "bob3" / "wired_caller.py"
    caller.write_text("from bob3.wired.mod import bar\n")

    criteria = [
        "integration: bob3.wired.mod",
        "integration: bob3.missing.package",
    ]
    result = handle_failing_integration_ac(criteria, tmp_path)
    assert result == NOT_RECONCILED


# ---------------------------------------------------------------------------
# reconcile_from_disk refuses promotion when integration AC regresses
# ---------------------------------------------------------------------------


def test_reconcile_refuses_when_integration_ac_fails(tmp_path, monkeypatch):
    """Feature is not promoted when its integration AC fails on disk.

    Uses a module name free of prose-connector substrings so that
    resolve_integration_ac returns False (not a prose-demoted PASS).
    """
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    # File exists, but integration wiring is missing.
    (tmp_path / "f.py").write_text("x = 1\n")
    _add_feature(
        db_path, project_id, feature_id, "Integration regression",
        status="ready",
        acceptance_criteria=[
            "File exists: f.py",
            "integration: bob3.missing.module",
        ],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_reconcile_refuses_only_failing_integration_feature(tmp_path, monkeypatch):
    """Only the feature with the failing integration AC is blocked; others promote."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    f_good = str(uuid.uuid4())
    f_bad = str(uuid.uuid4())
    _add_project(db_path, project_id)

    (tmp_path / "good.py").write_text("x = 1\n")
    (tmp_path / "bad.py").write_text("y = 2\n")

    _add_feature(
        db_path, project_id, f_good, "Good feature", "ready",
        ["File exists: good.py"],
    )
    _add_feature(
        db_path, project_id, f_bad, "Bad integration", "ready",
        ["File exists: bad.py", "integration: bob3.broken_module"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 1
    assert _get_feature_status(db_path, f_good) == "completed"
    assert _get_feature_status(db_path, f_bad) == "ready"
