"""Tests for AC: bob.spawn.verify_project_metadata — stale project metadata after rsync.

spawn_next_generation.sh rsync-copies the parent DB, which retains the parent's
projects.name and may have a stale spec_path from a pytest tmpdir. These tests
verify that verify_project_metadata detects and corrects both conditions.
"""
from __future__ import annotations

import pathlib
import sqlite3
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------

def test_spawn_module_importable():
    """bob.spawn must be importable as a module."""
    import bob.spawn  # noqa: F401


def test_verify_project_metadata_importable():
    """bob.spawn.verify_project_metadata must be a callable."""
    from bob.spawn import verify_project_metadata
    assert callable(verify_project_metadata)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: pathlib.Path, name: str, spec_path: str = "") -> pathlib.Path:
    """Create a minimal bob.db with a single projects row."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "bob.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, spec_path TEXT)"
    )
    conn.execute(
        "INSERT INTO projects (name, spec_path) VALUES (?, ?)",
        (name, spec_path),
    )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# Core behaviour tests
# ---------------------------------------------------------------------------

class TestVerifyProjectMetadataNameCheck:
    """projects.name staleness detection and correction."""

    def test_correct_name_returns_not_stale(self, tmp_path):
        """When projects.name already matches basename, name_was_stale is False."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path / "db", name="bob99")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is False
        assert result.corrected_name is None
        assert result.workspace_basename == "bob99"

    def test_stale_name_is_corrected(self, tmp_path):
        """When projects.name is stale (old gen), name_was_stale is True and DB is updated."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "bob62"
        workspace.mkdir()
        db = _make_db(tmp_path / "db", name="bob61")  # stale parent name

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.name_was_stale is True
        assert result.corrected_name == "bob62"
        assert result.workspace_basename == "bob62"

        # Verify DB was actually updated
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
        conn.close()
        assert row[0] == "bob62"

    def test_stale_name_idempotent_after_correction(self, tmp_path):
        """Second call after correction sees no staleness."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "bob62"
        workspace.mkdir()
        db = _make_db(tmp_path / "db", name="bob61")

        # First call corrects
        verify_project_metadata(workspace=workspace, db_path=db)
        # Second call sees correct name
        result2 = verify_project_metadata(workspace=workspace, db_path=db)

        assert result2.name_was_stale is False
        assert result2.corrected_name is None


class TestVerifyProjectMetadataSpecPathCheck:
    """spec_path pytest-tmpdir leak detection."""

    def test_clean_spec_path_not_stale(self, tmp_path):
        """Normal spec_path does not trigger spec_path_was_stale."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(
            tmp_path / "db",
            name="bob99",
            spec_path="/home/user/dark-factory/bob99/examples/bootstrap_v0.61.yaml",
        )

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False

    def test_pytest_tmpdir_spec_path_flagged(self, tmp_path):
        """spec_path containing 'pytest-of-' is flagged as stale."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(
            tmp_path / "db",
            name="bob99",
            spec_path="/tmp/pytest-of-user/test_foo0/minimal.yaml",
        )

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is True

    def test_empty_spec_path_not_stale(self, tmp_path):
        """Empty spec_path is not considered a tmpdir leak."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path / "db", name="bob99", spec_path="")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.spec_path_was_stale is False


class TestVerifyProjectMetadataReturnType:
    """Return type shape and field names."""

    def test_result_has_required_fields(self, tmp_path):
        """Result has name_was_stale, spec_path_was_stale, corrected_name, workspace_basename."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path / "db", name="bob99")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert hasattr(result, "name_was_stale")
        assert hasattr(result, "spec_path_was_stale")
        assert hasattr(result, "corrected_name")
        assert hasattr(result, "workspace_basename")

    def test_result_workspace_basename_correct(self, tmp_path):
        """workspace_basename always reflects the passed workspace dir name."""
        from bob.spawn import verify_project_metadata

        workspace = tmp_path / "my-project"
        workspace.mkdir()
        db = _make_db(tmp_path / "db", name="my-project")

        result = verify_project_metadata(workspace=workspace, db_path=db)

        assert result.workspace_basename == "my-project"


class TestVerifyProjectMetadataRunLoopIntegration:
    """Verify bob.run_loop also exposes verify_project_metadata (integration AC)."""

    def test_run_loop_exports_verify_project_metadata(self):
        """bob.run_loop.verify_project_metadata must be callable."""
        from bob.run_loop import verify_project_metadata
        assert callable(verify_project_metadata)

    def test_spawn_and_run_loop_return_same_type(self, tmp_path):
        """Both entry points return identical result types."""
        from bob.spawn import verify_project_metadata as spawn_vpm
        from bob.run_loop import verify_project_metadata as run_loop_vpm

        workspace = tmp_path / "bob99"
        workspace.mkdir()
        db = _make_db(tmp_path / "db", name="bob99")

        r1 = spawn_vpm(workspace=workspace, db_path=db)
        r2 = run_loop_vpm(workspace=workspace, db_path=db)

        assert type(r1) is type(r2)
        assert r1.workspace_basename == r2.workspace_basename
        assert r1.name_was_stale == r2.name_was_stale
