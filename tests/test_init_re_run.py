"""Tests for bob.init_re_run — startup check after spawn_next_generation.sh.

Covers verify_project_metadata and reinit_after_spawn, verifying that stale
project name and spec_path from rsync-copied parent DB are detected and corrected.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _make_db(tmp_path: Path, name: str = "bob59", spec_path: str = "") -> Path:
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.execute("INSERT INTO projects (name, spec_path) VALUES (?, ?)", (name, spec_path))
    conn.commit()
    conn.close()
    return db


def _make_empty_db(tmp_path: Path) -> Path:
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spec_path TEXT)"
    )
    conn.commit()
    conn.close()
    return db


class TestVerifyProjectMetadata:
    """verify_project_metadata detects and corrects stale project metadata."""

    def test_stale_name_is_corrected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob66")

        from bob.init_re_run import verify_project_metadata
        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob99"
        assert result.workspace_basename == "bob99"

        # Verify DB was actually updated
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob99"

    def test_name_already_correct_returns_not_stale(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob99")

        from bob.init_re_run import verify_project_metadata
        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob99"

    def test_stale_spec_path_detected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        stale_spec = "/tmp/pytest-of-user/pytest-42/test_spawn0/spec.yaml"
        db = _make_db(tmp_path, name="bob99", spec_path=stale_spec)

        from bob.init_re_run import verify_project_metadata
        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True

    def test_clean_spec_path_not_flagged(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        good_spec = "/home/user/dark-factory/bob99/examples/bootstrap_v0.66.yaml"
        db = _make_db(tmp_path, name="bob99", spec_path=good_spec)

        from bob.init_re_run import verify_project_metadata
        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_none_workspace_defaults_to_cwd(self, tmp_path):
        db = _make_db(tmp_path, name="bob59")

        from bob.init_re_run import verify_project_metadata
        from bob.run_loop import ProjectMetadataCheckResult
        result = verify_project_metadata(workspace=None, db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)
        assert isinstance(result.workspace_basename, str)

    def test_empty_string_workspace_no_raise(self, tmp_path):
        db = _make_db(tmp_path, name="bob59")

        from bob.init_re_run import verify_project_metadata
        from bob.run_loop import ProjectMetadataCheckResult
        result = verify_project_metadata(workspace="", db_path=db)

        assert isinstance(result, ProjectMetadataCheckResult)

    def test_invalid_workspace_type_raises_value_error(self, tmp_path):
        db = _make_db(tmp_path, name="bob59")

        from bob.init_re_run import verify_project_metadata
        with pytest.raises(ValueError):
            verify_project_metadata(workspace=42, db_path=db)  # type: ignore[arg-type]

    def test_both_stale_name_and_stale_spec_detected(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        stale_spec = "/tmp/pytest-of-ci/pytest-1/test_spawn0/spec.yaml"
        db = _make_db(tmp_path, name="bob66", spec_path=stale_spec)

        from bob.init_re_run import verify_project_metadata
        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.spec_path_was_stale is True

    def test_empty_projects_table_returns_not_stale(self, tmp_path):
        workspace = tmp_path / "bob60"
        workspace.mkdir()
        db = _make_empty_db(tmp_path)

        from bob.init_re_run import verify_project_metadata
        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None


class TestReinitAfterSpawn:
    """reinit_after_spawn is a spawn-specific alias for verify_project_metadata."""

    def test_reinit_after_spawn_corrects_stale_name(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob66")

        from bob.init_re_run import reinit_after_spawn
        result = reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob99"

    def test_reinit_after_spawn_no_op_when_fresh(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob99")

        from bob.init_re_run import reinit_after_spawn
        result = reinit_after_spawn(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None

    def test_reinit_after_spawn_invalid_workspace_raises(self, tmp_path):
        db = _make_db(tmp_path, name="bob59")

        from bob.init_re_run import reinit_after_spawn
        with pytest.raises(ValueError):
            reinit_after_spawn(workspace=["not", "a", "path"], db_path=db)  # type: ignore[arg-type]

    def test_reinit_and_verify_return_same_result_shape(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob66")

        from bob.init_re_run import reinit_after_spawn, verify_project_metadata
        from bob.run_loop import ProjectMetadataCheckResult

        r = reinit_after_spawn(workspace=workspace, db_path=db)
        assert isinstance(r, ProjectMetadataCheckResult)
        assert hasattr(r, "name_was_stale")
        assert hasattr(r, "spec_path_was_stale")
        assert hasattr(r, "corrected_name")
        assert hasattr(r, "workspace_basename")


class TestRunLoopIntegration:
    """init_re_run integrates with bob.run_loop.verify_project_metadata."""

    def test_init_re_run_and_run_loop_produce_consistent_results(self, tmp_path):
        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path, name="bob66")

        from bob.init_re_run import verify_project_metadata as init_rerun_verify
        from bob.run_loop import verify_project_metadata as run_loop_verify

        # First call via init_re_run corrects the name
        r1 = init_rerun_verify(workspace=workspace, db_path=db)
        assert r1.name_was_stale is True

        # Second call via run_loop sees the corrected state
        r2 = run_loop_verify(workspace=workspace, db_path=db)
        assert r2.name_was_stale is False
        assert r2.workspace_basename == "bob99"
