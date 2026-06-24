"""Tests for bob.project_metadata_validator.

Verifies:
- verify_project_name_matches_workspace: detects stale vs correct project names.
- reinit_stale_projects: corrects stale rows and returns updated IDs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bob.project_metadata_validator import (
    verify_project_name_matches_workspace,
    reinit_stale_projects,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path, name: str = "bob89", spec_path: str = "") -> Path:
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects "
        "(id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.execute(
        "INSERT INTO projects (id, name, spec_path) VALUES (?, ?, ?)",
        ("proj-001", name, spec_path),
    )
    conn.commit()
    conn.close()
    return db


def _make_empty_db(tmp_path: Path) -> Path:
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects "
        "(id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# verify_project_name_matches_workspace
# ---------------------------------------------------------------------------

class TestVerifyProjectNameMatchesWorkspace:
    def test_matching_name_returns_true(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob89")
        assert verify_project_name_matches_workspace(workspace=workspace, db_path=db) is True

    def test_mismatched_name_returns_false(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob66")
        assert verify_project_name_matches_workspace(workspace=workspace, db_path=db) is False

    def test_empty_table_returns_false(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = _make_empty_db(tmp_path)
        assert verify_project_name_matches_workspace(workspace=workspace, db_path=db) is False

    def test_none_workspace_defaults_to_cwd(self, tmp_path):
        """None workspace defaults to cwd — no exception raised, returns a bool."""
        db = _make_db(tmp_path, name="anything")
        result = verify_project_name_matches_workspace(workspace=None, db_path=db)
        assert isinstance(result, bool)

    def test_empty_string_workspace_defaults_to_cwd(self, tmp_path):
        db = _make_db(tmp_path, name="anything")
        result = verify_project_name_matches_workspace(workspace="", db_path=db)
        assert isinstance(result, bool)

    def test_missing_db_returns_false(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        missing_db = tmp_path / "nonexistent.db"
        result = verify_project_name_matches_workspace(workspace=workspace, db_path=missing_db)
        assert result is False

    def test_invalid_workspace_type_raises_value_error(self, tmp_path):
        db = _make_db(tmp_path, name="bob89")
        with pytest.raises(ValueError):
            verify_project_name_matches_workspace(workspace=42, db_path=db)  # type: ignore[arg-type]

    def test_list_workspace_raises_value_error(self, tmp_path):
        db = _make_db(tmp_path, name="bob89")
        with pytest.raises(ValueError):
            verify_project_name_matches_workspace(workspace=["bob89"], db_path=db)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# reinit_stale_projects
# ---------------------------------------------------------------------------

class TestReinitStaleProjects:
    def test_stale_name_is_corrected(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob66")

        corrected = reinit_stale_projects(workspace=workspace, db_path=db)

        assert corrected == ["proj-001"]

        # Verify the DB was actually updated
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob89"

    def test_correct_name_returns_empty_list(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob89")

        corrected = reinit_stale_projects(workspace=workspace, db_path=db)

        assert corrected == []

    def test_empty_table_returns_empty_list(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = _make_empty_db(tmp_path)

        corrected = reinit_stale_projects(workspace=workspace, db_path=db)

        assert corrected == []

    def test_multiple_stale_rows_all_corrected(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = tmp_path / "bob.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE projects "
            "(id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
        )
        conn.execute("INSERT INTO projects VALUES (?, ?, ?)", ("p1", "bob66", ""))
        conn.execute("INSERT INTO projects VALUES (?, ?, ?)", ("p2", "bob70", ""))
        conn.commit()
        conn.close()

        corrected = reinit_stale_projects(workspace=workspace, db_path=db)

        assert sorted(corrected) == ["p1", "p2"]

        conn = sqlite3.connect(str(db))
        names = [r[0] for r in conn.execute("SELECT name FROM projects").fetchall()]
        conn.close()
        assert all(n == "bob89" for n in names)

    def test_stale_spec_path_does_not_stop_name_correction(self, tmp_path):
        """A pytest-tmpdir spec_path is logged but name correction still proceeds."""
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        stale_spec = "/tmp/pytest-of-user/pytest-42/test_foo0/spec.yaml"
        db = _make_db(tmp_path, name="bob66", spec_path=stale_spec)

        corrected = reinit_stale_projects(workspace=workspace, db_path=db)

        assert "proj-001" in corrected

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob89"

    def test_none_workspace_defaults_to_cwd(self, tmp_path):
        db = _make_db(tmp_path, name="anything")
        result = reinit_stale_projects(workspace=None, db_path=db)
        assert isinstance(result, list)

    def test_invalid_workspace_type_raises_value_error(self, tmp_path):
        db = _make_db(tmp_path, name="bob89")
        with pytest.raises(ValueError):
            reinit_stale_projects(workspace=99, db_path=db)  # type: ignore[arg-type]

    def test_missing_db_returns_empty_list(self, tmp_path):
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        missing_db = tmp_path / "no_such.db"

        result = reinit_stale_projects(workspace=workspace, db_path=missing_db)
        assert result == []

    def test_idempotent_second_call_no_updates(self, tmp_path):
        """Calling reinit twice is a no-op on the second call."""
        workspace = tmp_path / "bob89"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob66")

        first = reinit_stale_projects(workspace=workspace, db_path=db)
        assert first == ["proj-001"]

        second = reinit_stale_projects(workspace=workspace, db_path=db)
        assert second == []
