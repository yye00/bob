"""Tests for bob3_init_re_run_after_spawn_fixes_stale_project_metadata.

Verifies that the startup check correctly detects and corrects stale project
metadata that results from spawn_next_generation.sh rsync-copying the parent DB.
"""

from __future__ import annotations

import sqlite3
import pathlib
import pytest

from bob3.bob3_init_re_run_after_spawn_fixes_stale_project_metadata import (
    bob3_init_re_run_after_spawn_fixes_stale_project_metadata,
)


def _create_db(path: pathlib.Path, name: str, spec_path: str = "") -> None:
    """Helper to create a minimal bob3.db with a projects row."""
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


def test_bob3_init_re_run_after_spawn_fixes_stale_project_metadata(tmp_path):
    """Core AC test: stale name is detected and corrected; result reflects the fix."""
    workspace = tmp_path / "bob99"
    workspace.mkdir()
    db = workspace / "bob3.db"

    # DB has parent's name "bob66" but workspace is "bob99"
    _create_db(db, name="bob66")

    result = bob3_init_re_run_after_spawn_fixes_stale_project_metadata(
        workspace=workspace,
        db_path=db,
    )

    assert result.name_was_stale is True
    assert result.corrected_name == "bob99"
    assert result.workspace_basename == "bob99"
    assert result.spec_path_was_stale is False

    # Verify the DB was actually updated
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "bob99"


def test_name_already_correct_returns_no_stale(tmp_path):
    """No-op when the project name already matches the workspace basename."""
    workspace = tmp_path / "bob99"
    workspace.mkdir()
    db = workspace / "bob3.db"

    _create_db(db, name="bob99")

    result = bob3_init_re_run_after_spawn_fixes_stale_project_metadata(
        workspace=workspace,
        db_path=db,
    )

    assert result.name_was_stale is False
    assert result.corrected_name is None
    assert result.workspace_basename == "bob99"
    assert result.spec_path_was_stale is False


def test_stale_spec_path_detected(tmp_path):
    """spec_path containing pytest tmpdir prefix is detected as stale."""
    workspace = tmp_path / "bob99"
    workspace.mkdir()
    db = workspace / "bob3.db"

    stale_spec = "/tmp/pytest-of-user/pytest-42/test_foo0/minimal.yaml"
    _create_db(db, name="bob99", spec_path=stale_spec)

    result = bob3_init_re_run_after_spawn_fixes_stale_project_metadata(
        workspace=workspace,
        db_path=db,
    )

    assert result.spec_path_was_stale is True
    assert result.name_was_stale is False


def test_stale_name_and_stale_spec_path_both_detected(tmp_path):
    """Both stale name and stale spec_path are detected in the same run."""
    workspace = tmp_path / "bob99"
    workspace.mkdir()
    db = workspace / "bob3.db"

    stale_spec = "/tmp/pytest-of-user/pytest-123/spec.yaml"
    _create_db(db, name="bob66", spec_path=stale_spec)

    result = bob3_init_re_run_after_spawn_fixes_stale_project_metadata(
        workspace=workspace,
        db_path=db,
    )

    assert result.name_was_stale is True
    assert result.corrected_name == "bob99"
    assert result.spec_path_was_stale is True


def test_clean_spec_path_not_flagged(tmp_path):
    """A real (non-tmpdir) spec_path is not flagged as stale."""
    workspace = tmp_path / "bob99"
    workspace.mkdir()
    db = workspace / "bob3.db"

    good_spec = "/home/yelkhamr/dark-factory/bob99/examples/bootstrap_v0.66.yaml"
    _create_db(db, name="bob99", spec_path=good_spec)

    result = bob3_init_re_run_after_spawn_fixes_stale_project_metadata(
        workspace=workspace,
        db_path=db,
    )

    assert result.spec_path_was_stale is False
    assert result.name_was_stale is False


def test_workspace_basename_always_returned(tmp_path):
    """workspace_basename field always reflects the actual workspace name."""
    workspace = tmp_path / "my_custom_workspace"
    workspace.mkdir()
    db = workspace / "bob3.db"

    _create_db(db, name="my_custom_workspace")

    result = bob3_init_re_run_after_spawn_fixes_stale_project_metadata(
        workspace=workspace,
        db_path=db,
    )

    assert result.workspace_basename == "my_custom_workspace"
