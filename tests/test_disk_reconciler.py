"""Tests for bob3.orchestrator.disk_reconciler (feature 2f69b554).

Tests cover:
- evaluate_ac_against_disk for each AC type (File exists, Function defined,
  pytest, integration)
- reconcile_from_disk: promotes features whose all ACs pass on disk
- reconcile_from_disk: skips features with failing ACs
- reconcile_from_disk: creates evidence artifact on promotion
- reconcile_from_disk: only considers 'ready' and 'pending' features
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import tempfile
import uuid

import pytest

from bob3.orchestrator.disk_reconciler import evaluate_ac_against_disk, reconcile_from_disk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a minimal bob3 SQLite database in tmp_path."""
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


def _get_evidence_types(db_path: pathlib.Path, feature_id: str) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "SELECT type FROM evidence_artifacts WHERE feature_id = ?", (feature_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# evaluate_ac_against_disk — File exists
# ---------------------------------------------------------------------------


def test_evaluate_file_exists_passes(tmp_path):
    """File exists criterion passes when file is present."""
    (tmp_path / "myfile.py").write_text("x = 1\n")
    passed, detail = evaluate_ac_against_disk("File exists: myfile.py", tmp_path)
    assert passed is True
    assert isinstance(detail, str)


def test_evaluate_file_exists_fails_missing(tmp_path):
    """File exists criterion fails when file is absent."""
    passed, detail = evaluate_ac_against_disk("File exists: missing.py", tmp_path)
    assert passed is False


def test_evaluate_file_exists_nested_path(tmp_path):
    """File exists criterion handles nested paths."""
    nested = tmp_path / "src" / "pkg" / "module.py"
    nested.parent.mkdir(parents=True)
    nested.write_text("def foo(): pass\n")
    passed, _ = evaluate_ac_against_disk("File exists: src/pkg/module.py", tmp_path)
    assert passed is True


# ---------------------------------------------------------------------------
# evaluate_ac_against_disk — Function defined
# ---------------------------------------------------------------------------


def test_evaluate_function_defined_passes(tmp_path):
    """Function defined criterion passes when function exists in any .py."""
    src = tmp_path / "src" / "bob3"
    src.mkdir(parents=True)
    (src / "mymod.py").write_text("def my_function():\n    return 42\n")
    passed, _ = evaluate_ac_against_disk(
        "Function defined: bob3.mymod.my_function", tmp_path
    )
    assert passed is True


def test_evaluate_function_defined_fails_missing(tmp_path):
    """Function defined criterion fails when function is absent."""
    (tmp_path / "dummy.py").write_text("x = 1\n")
    passed, _ = evaluate_ac_against_disk(
        "Function defined: bob3.nonexistent.missing_fn", tmp_path
    )
    assert passed is False


def test_evaluate_function_defined_class_counts(tmp_path):
    """Function defined accepts a class definition too."""
    (tmp_path / "foo.py").write_text("class MyClass:\n    pass\n")
    passed, _ = evaluate_ac_against_disk("Function defined: pkg.foo.MyClass", tmp_path)
    assert passed is True


# ---------------------------------------------------------------------------
# evaluate_ac_against_disk — pytest
# ---------------------------------------------------------------------------


def test_evaluate_pytest_passing_test(tmp_path):
    """pytest criterion passes when the specified test file passes."""
    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "def test_trivial():\n    assert 1 + 1 == 2\n"
    )
    passed, detail = evaluate_ac_against_disk(
        "pytest: tests/test_sample.py", tmp_path
    )
    assert passed is True


def test_evaluate_pytest_failing_test(tmp_path):
    """pytest criterion fails when test fails."""
    test_file = tmp_path / "tests" / "test_fail.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_broken():\n    assert False\n")
    passed, _ = evaluate_ac_against_disk("pytest: tests/test_fail.py", tmp_path)
    assert passed is False


def test_evaluate_pytest_missing_file(tmp_path):
    """pytest criterion fails when test file does not exist."""
    passed, _ = evaluate_ac_against_disk(
        "pytest: tests/test_no_such.py", tmp_path
    )
    assert passed is False


# ---------------------------------------------------------------------------
# evaluate_ac_against_disk — integration
# ---------------------------------------------------------------------------


def test_evaluate_integration_wired(tmp_path):
    """integration criterion passes when module exists AND is imported."""
    pkg = tmp_path / "src" / "bob3" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "mymod.py").write_text("def foo(): pass\n")
    caller = tmp_path / "src" / "bob3" / "caller.py"
    caller.write_text("from bob3.mypkg.mymod import foo\n")
    passed, _ = evaluate_ac_against_disk("integration: bob3.mypkg.mymod", tmp_path)
    assert passed is True


def test_evaluate_integration_not_imported(tmp_path):
    """integration criterion fails when module exists but is never imported.

    Uses a module name free of prose-connector substrings (avoids the
    _is_prose_body false-positive where 'or' in 'orphan' triggers demotion).
    """
    pkg = tmp_path / "src" / "bob3" / "missing"
    pkg.mkdir(parents=True)
    (pkg / "pkg.py").write_text("x = 1\n")
    # No other file imports it — bare dotted path, no prose connectors
    passed, _ = evaluate_ac_against_disk("integration: bob3.missing.pkg", tmp_path)
    assert passed is False


# ---------------------------------------------------------------------------
# reconcile_from_disk — full promotion path
# ---------------------------------------------------------------------------


def test_reconcile_promotes_ready_feature(tmp_path, monkeypatch):
    """A 'ready' feature whose File exists AC passes is promoted to 'completed'."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    # Create the file the AC expects.
    target = tmp_path / "myfile.py"
    target.write_text("x = 1\n")

    _add_feature(
        db_path, project_id, feature_id, "Test feature",
        status="ready",
        acceptance_criteria=["File exists: myfile.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 1
    assert _get_feature_status(db_path, feature_id) == "completed"


def test_reconcile_creates_evidence_artifact(tmp_path, monkeypatch):
    """Promotion records a disk_reconciliation evidence artifact."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "f.py").write_text("def myfunc(): pass\n")

    _add_feature(
        db_path, project_id, feature_id, "Evidence test",
        status="ready",
        acceptance_criteria=["File exists: f.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    reconcile_from_disk(project_id, workspace=tmp_path)

    evidence_types = _get_evidence_types(db_path, feature_id)
    assert "disk_reconciliation" in evidence_types


def test_reconcile_promotes_pending_feature(tmp_path, monkeypatch):
    """A 'pending' feature (post-seed, pre-run) is also eligible for promotion."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "exists.py").write_text("x = 1\n")

    _add_feature(
        db_path, project_id, feature_id, "Pending feature",
        status="pending",
        acceptance_criteria=["File exists: exists.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 1
    assert _get_feature_status(db_path, feature_id) == "completed"


def test_reconcile_skips_when_ac_fails(tmp_path, monkeypatch):
    """Feature is not promoted when at least one AC fails on disk."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    # Do NOT create the expected file.

    _add_feature(
        db_path, project_id, feature_id, "Failing AC",
        status="ready",
        acceptance_criteria=["File exists: missing_file.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_reconcile_skips_no_ac(tmp_path, monkeypatch):
    """Feature with no acceptance_criteria is not promoted."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    _add_feature(
        db_path, project_id, feature_id, "No AC",
        status="ready",
        acceptance_criteria=None,
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_reconcile_skips_already_completed(tmp_path, monkeypatch):
    """Already-completed features are not double-processed."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "x.py").write_text("x = 1\n")

    _add_feature(
        db_path, project_id, feature_id, "Already done",
        status="completed",
        acceptance_criteria=["File exists: x.py"],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0


def test_reconcile_returns_zero_when_nothing_to_do(tmp_path, monkeypatch):
    """Return 0 when project has no ready/pending features."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    _add_project(db_path, project_id)

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0


def test_reconcile_all_acs_must_pass(tmp_path, monkeypatch):
    """Feature is not promoted if any one AC fails, even if others pass."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    feature_id = str(uuid.uuid4())
    _add_project(db_path, project_id)
    (tmp_path / "present.py").write_text("x = 1\n")
    # absent.py intentionally not created

    _add_feature(
        db_path, project_id, feature_id, "Mixed ACs",
        status="ready",
        acceptance_criteria=[
            "File exists: present.py",
            "File exists: absent.py",
        ],
    )

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 0
    assert _get_feature_status(db_path, feature_id) == "ready"


def test_reconcile_multiple_features(tmp_path, monkeypatch):
    """Multiple features are promoted independently in a single call."""
    db_path = _make_db(tmp_path)
    project_id = str(uuid.uuid4())
    f1 = str(uuid.uuid4())
    f2 = str(uuid.uuid4())
    f3 = str(uuid.uuid4())
    _add_project(db_path, project_id)

    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    # c.py intentionally missing

    _add_feature(db_path, project_id, f1, "Feature A", "ready", ["File exists: a.py"])
    _add_feature(db_path, project_id, f2, "Feature B", "ready", ["File exists: b.py"])
    _add_feature(db_path, project_id, f3, "Feature C", "ready", ["File exists: c.py"])

    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    count = reconcile_from_disk(project_id, workspace=tmp_path)

    assert count == 2
    assert _get_feature_status(db_path, f1) == "completed"
    assert _get_feature_status(db_path, f2) == "completed"
    assert _get_feature_status(db_path, f3) == "ready"
