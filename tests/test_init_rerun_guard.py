"""Tests for bob3.init_rerun_guard.verify_and_reinit_after_spawn.

Verifies that the guard correctly detects and corrects stale project metadata
left by spawn_next_generation.sh rsync-copying the parent DB without re-running
bob3 init.
"""

from __future__ import annotations

import sqlite3
import pathlib
import pytest

from bob3.init_rerun_guard import verify_and_reinit_after_spawn


def _create_db(path: pathlib.Path, name: str, spec_path: str = "") -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            spec_path TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO projects (id, name, spec_path) VALUES (?, ?, ?)",
        ("proj-001", name, spec_path),
    )
    conn.commit()
    conn.close()


def _create_empty_db(path: pathlib.Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS projects "
        "(id TEXT PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.commit()
    conn.close()


class TestVerifyAndReinitAfterSpawn:
    def test_stale_name_is_detected_and_corrected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        _create_db(db, name="bob66")

        result = verify_and_reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob99"
        assert result.workspace_basename == "bob99"
        assert result.spec_path_was_stale is False

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "bob99"

    def test_correct_name_is_no_op(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        _create_db(db, name="bob99")

        result = verify_and_reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob99"
        assert result.spec_path_was_stale is False

    def test_stale_spec_path_detected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        stale_spec = "/tmp/pytest-of-user/pytest-42/test_foo0/minimal.yaml"
        _create_db(db, name="bob99", spec_path=stale_spec)

        result = verify_and_reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True
        assert result.name_was_stale is False

    def test_both_stale_name_and_spec_path_detected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        stale_spec = "/tmp/pytest-of-ci/pytest-1/test_spawn0/spec.yaml"
        _create_db(db, name="bob66", spec_path=stale_spec)

        result = verify_and_reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob99"
        assert result.spec_path_was_stale is True

    def test_empty_projects_table_returns_false_no_raise(self, tmp_path):
        workspace = tmp_path / "bob60"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        _create_empty_db(db)

        result = verify_and_reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob60"
        assert result.spec_path_was_stale is False

    def test_none_workspace_defaults_to_cwd(self, tmp_path):
        db = tmp_path / "bob3.db"
        _create_empty_db(db)

        result = verify_and_reinit_after_spawn(workspace=None, db_path=db)

        assert isinstance(result.name_was_stale, bool)
        assert isinstance(result.workspace_basename, str)
        assert len(result.workspace_basename) > 0

    def test_clean_spec_path_not_flagged(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        good_spec = "/home/yelkhamr/dark-factory/bob99/examples/bootstrap_v0.66.yaml"
        _create_db(db, name="bob99", spec_path=good_spec)

        result = verify_and_reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False
        assert result.name_was_stale is False

    def test_integer_workspace_raises_value_error(self, tmp_path):
        db = tmp_path / "bob3.db"
        _create_empty_db(db)

        with pytest.raises(ValueError):
            verify_and_reinit_after_spawn(workspace=42, db_path=db)  # type: ignore[arg-type]

    def test_list_workspace_raises_value_error(self, tmp_path):
        db = tmp_path / "bob3.db"
        _create_empty_db(db)

        with pytest.raises(ValueError):
            verify_and_reinit_after_spawn(workspace=["bob99"], db_path=db)  # type: ignore[arg-type]

    def test_returns_project_metadata_check_result(self, tmp_path):
        from bob3.run_loop import ProjectMetadataCheckResult

        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = tmp_path / "bob3.db"
        _create_db(db, name="bob99")

        result = verify_and_reinit_after_spawn(workspace=workspace, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
