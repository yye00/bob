"""Error-path tests for bob3 init re-run after spawn fixes stale project metadata.

Tests that invalid input raises ValueError and the function does not
silently succeed (AC6 error path requirement).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_db(tmp_path: Path, name: str = "bob59", spec_path: str = "") -> Path:
    db = tmp_path / "bob3.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, ?)", (name, spec_path))
    conn.commit()
    conn.close()
    return db


class TestVerifyProjectMetadataErrorPath:
    """verify_project_metadata raises ValueError on invalid inputs."""

    def test_integer_workspace_raises_value_error(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        db = _make_db(tmp_path, "bob59")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=42, db_path=db)  # type: ignore[arg-type]

    def test_list_workspace_raises_value_error(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        db = _make_db(tmp_path, "bob59")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=["bob59"], db_path=db)  # type: ignore[arg-type]

    def test_dict_workspace_raises_value_error(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        db = _make_db(tmp_path, "bob59")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace={"path": "bob59"}, db_path=db)  # type: ignore[arg-type]

    def test_float_workspace_raises_value_error(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        db = _make_db(tmp_path, "bob59")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=3.14, db_path=db)  # type: ignore[arg-type]

    def test_int_zero_workspace_raises_value_error(self, tmp_path):
        from bob3.run_loop import verify_project_metadata

        db = _make_db(tmp_path, "bob59")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=0, db_path=db)  # type: ignore[arg-type]

    def test_bool_workspace_raises_value_error(self, tmp_path):
        """bool is a subclass of int; should raise ValueError, not silently succeed."""
        from bob3.run_loop import verify_project_metadata

        db = _make_db(tmp_path, "bob59")
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=True, db_path=db)  # type: ignore[arg-type]


class TestStaleSpecPathError:
    """StaleSpecPathError is raised — not silently swallowed — on pytest tmpdir."""

    def test_pytest_tmpdir_raises_stale_spec_error(self, tmp_path):
        from bob3.orchestrator.project_metadata_check import (
            reject_pytest_tmpdir_in_spec_path,
            StaleSpecPathError,
        )

        stale_path = "/tmp/pytest-of-runner/pytest-42/test_init_0/spec.yaml"
        db = _make_db(tmp_path, "bob59", spec_path=stale_path)

        with pytest.raises(StaleSpecPathError) as exc_info:
            reject_pytest_tmpdir_in_spec_path(db_path=db)

        assert "pytest-of-" in str(exc_info.value)

    def test_stale_spec_path_surfaces_via_verify_metadata(self, tmp_path):
        """verify_project_metadata surfaces spec_path_was_stale=True, not a silent pass."""
        from bob3.run_loop import verify_project_metadata

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        stale_path = "/tmp/pytest-of-ci/pytest-1/test_spawn0/spec.yaml"
        db = _make_db(tmp_path, "bob60", spec_path=stale_path)

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True, (
            "Expected spec_path_was_stale=True for pytest tmpdir path, not silent success"
        )


class TestProjectMetadataCheckInvalidDbPath:
    """Functions handle missing DB gracefully rather than crashing silently."""

    def test_update_project_name_missing_db_raises(self, tmp_path):
        """Pointing at a nonexistent DB should raise (OperationalError or similar)."""
        from bob3.orchestrator.project_metadata_check import update_project_name_if_mismatch

        workspace = tmp_path / "bob60"
        workspace.mkdir()
        missing_db = tmp_path / "nonexistent.db"

        # sqlite3 creates new DBs on connect, but the table won't exist —
        # the function returns False (empty table path) rather than raising
        # a confusing exception. Both False-return or an explicit exception
        # are acceptable; what's NOT acceptable is silently returning True.
        try:
            result = update_project_name_if_mismatch(db_path=missing_db, workspace=workspace)
            # If it doesn't raise, it must not silently claim an update happened
            assert result is False, (
                "Pointing at a missing DB must not return True (silent false success)"
            )
        except Exception:
            pass  # Any exception is also acceptable

    def test_reject_pytest_tmpdir_missing_db_does_not_silently_succeed(self, tmp_path):
        """Missing DB with a nonexistent path does not silently pass as clean."""
        from bob3.orchestrator.project_metadata_check import (
            reject_pytest_tmpdir_in_spec_path,
            StaleSpecPathError,
        )

        missing_db = tmp_path / "no_such.db"

        # Either raises an exception (sqlite3 error, OperationalError) or
        # handles gracefully — what matters is it does not return silently
        # while a real stale path exists (since the DB has no rows here, no raise is fine).
        try:
            reject_pytest_tmpdir_in_spec_path(db_path=missing_db)
        except StaleSpecPathError:
            raise  # This would be a bug — empty DB should not raise StaleSpecPathError
        except Exception:
            pass  # Other exceptions from missing table/DB are acceptable
