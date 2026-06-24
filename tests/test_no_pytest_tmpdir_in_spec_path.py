"""Tests: projects.spec_path must not point to a pytest tmpdir.

The bug: rsync copies the parent generation's bob.db. If the parent ran
tests and a test had called ``bob init`` with a tempdir spec, the projects
row ends up with spec_path = '/tmp/pytest-of-.../minimal.yaml'. This test
suite verifies:

1. The startup check in run_loop detects a stale/tmp spec_path and updates it.
2. The init command's UPSERT logic correctly overwrites spec_path on re-init.
3. A live DB (bob.db in this workspace) does not have a tmpdir spec_path.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import pathlib
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import uuid

import pytest

from bob import db as bob_db
from bob.db import get_connection, init_database


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Path:
    """Create a minimal bob.db in tmp_path with one project row."""
    db_path = tmp_path / "bob.db"
    bob_db.init_database(db_path=db_path)
    conn = sqlite3.connect(str(db_path))
    project_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects (id, name, workspace_path, spec_path, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, "bob9", str(tmp_path), "/tmp/pytest-of-root/test_foo/minimal.yaml", "planning"),
    )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Unit: init command UPSERT overwrites stale spec_path on re-init
# ---------------------------------------------------------------------------

def test_init_upsert_overwrites_tmpdir_spec_path(tmp_path):
    """Running init on an existing DB with a tmpdir spec_path updates the row."""
    db_path = _make_db(tmp_path)

    # Verify the stale state
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT spec_path FROM projects LIMIT 1").fetchone()
    conn.close()
    assert row[0].startswith("/tmp"), f"Precondition: expected /tmp spec_path, got {row[0]}"

    # Re-init with a real spec path
    real_spec = tmp_path / "examples" / "bootstrap_v0.9.yaml"
    real_spec.parent.mkdir(parents=True, exist_ok=True)
    real_spec.write_text("features: []\n")

    # Simulate what spawn_next_generation.sh does: run init with --name and --spec
    from bob.cli import main as bob_main
    from click.testing import CliRunner

    runner = CliRunner()
    with patch.dict(os.environ, {"BOB_DATABASE_PATH": str(db_path)}):
        # Patch MCP so init doesn't try to start the real MCP server
        with patch("bob.cli.start_mcp_server"), \
             patch("bob.cli.stop_mcp_server"), \
             patch("bob.cli._check_runtime_dependencies"):
            result = runner.invoke(
                bob_main,
                ["init", str(tmp_path), "--name", "bob10", "--spec", str(real_spec)],
            )

    assert result.exit_code == 0, f"init failed: {result.output}\n{result.exception}"

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT name, spec_path FROM projects LIMIT 1").fetchone()
    conn.close()

    name, spec_path = row
    stale_path = "/tmp/pytest-of-root/test_foo/minimal.yaml"
    assert name == "bob10", f"Expected name='bob10', got {name!r}"
    assert stale_path not in (spec_path or ""), (
        f"spec_path still points to original stale tmpdir: {spec_path}"
    )
    assert str(real_spec) in (spec_path or ""), (
        f"spec_path not updated to real spec: {spec_path}"
    )


def test_init_upsert_updates_name_without_spec(tmp_path):
    """Running init on an existing DB without --spec still updates name."""
    db_path = _make_db(tmp_path)

    from bob.cli import main as bob_main
    from click.testing import CliRunner

    runner = CliRunner()
    with patch.dict(os.environ, {"BOB_DATABASE_PATH": str(db_path)}):
        with patch("bob.cli.start_mcp_server"), \
             patch("bob.cli.stop_mcp_server"), \
             patch("bob.cli._check_runtime_dependencies"):
            result = runner.invoke(
                bob_main,
                ["init", str(tmp_path), "--name", "bob10"],
            )

    assert result.exit_code == 0, f"init failed: {result.output}"

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
    conn.close()

    assert row[0] == "bob10", f"Expected name='bob10', got {row[0]!r}"


# ---------------------------------------------------------------------------
# Unit: run_loop startup check updates stale project name
# ---------------------------------------------------------------------------

def test_run_loop_startup_check_fixes_stale_name(tmp_path, monkeypatch):
    """_verify_project_name_matches_workspace updates DB when name is stale."""
    db_path = _make_db(tmp_path)

    # The workspace dir is named 'bob10', but the project row says 'bob9'
    workspace = tmp_path  # tmp_path basename != 'bob9'
    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    # Get the project id
    conn = sqlite3.connect(str(db_path))
    project_id = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()[0]
    conn.close()

    from bob.orchestrator.run_loop import _verify_project_name_matches_workspace

    updated = _verify_project_name_matches_workspace(
        project_id=project_id,
        workspace=workspace,
        db_path=db_path,
    )
    assert updated is True, "Expected the function to detect and update the stale name"

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
    conn.close()

    expected_name = workspace.name
    assert row[0] == expected_name, (
        f"After startup check, expected name={expected_name!r}, got {row[0]!r}"
    )


def test_run_loop_startup_check_noop_when_name_matches(tmp_path, monkeypatch):
    """_verify_project_name_matches_workspace returns False when name already correct."""
    db_path = bob_db.init_database(db_path=tmp_path / "bob.db") or tmp_path / "bob.db"
    db_path = tmp_path / "bob.db"
    bob_db.init_database(db_path=db_path)

    workspace_name = tmp_path.name
    conn = sqlite3.connect(str(db_path))
    project_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects (id, name, workspace_path, spec_path, status) VALUES (?, ?, ?, ?, ?)",
        (project_id, workspace_name, str(tmp_path), None, "planning"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("BOB_DATABASE_PATH", str(db_path))

    from bob.orchestrator.run_loop import _verify_project_name_matches_workspace

    updated = _verify_project_name_matches_workspace(
        project_id=project_id,
        workspace=tmp_path,
        db_path=db_path,
    )
    assert updated is False, "Expected no update when name already matches workspace basename"


# ---------------------------------------------------------------------------
# Integration: live DB in this workspace must not have a tmpdir spec_path
# ---------------------------------------------------------------------------

def test_live_db_spec_path_not_in_tmpdir():
    """The bob.db in this workspace must not have a /tmp spec_path."""
    workspace = Path(__file__).parents[1]
    db_path = workspace / "bob.db"

    if not db_path.exists():
        pytest.skip("bob.db not found in workspace; skipping live DB check")

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT name, spec_path FROM projects").fetchall()
    conn.close()

    tmpdir_rows = [
        (name, sp) for name, sp in rows
        if sp and ("/tmp/pytest" in sp or "/tmp/" in sp)
    ]
    assert not tmpdir_rows, (
        f"Live bob.db has project row(s) with tmpdir spec_path: {tmpdir_rows}"
    )
