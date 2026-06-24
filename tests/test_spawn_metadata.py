"""Tests for feature 1809afa5: bob3 init re-run after spawn fixes stale metadata.

Verifies:
  - bob3.spawn.verify_project_metadata exists and is callable
  - verify_project_metadata detects and fixes stale project name
  - verify_project_metadata detects pytest tmpdir spec_path leaks
  - The orchestrator's _run_locked wires verify_project_metadata at startup
    (integration AC: bob3.run_loop)
"""
from __future__ import annotations

import importlib
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# AC: Function defined: bob3.spawn.verify_project_metadata
# ---------------------------------------------------------------------------

def test_verify_project_metadata_importable_from_spawn():
    """bob3.spawn.verify_project_metadata must be importable."""
    import bob3.spawn as spawn_mod
    assert hasattr(spawn_mod, "verify_project_metadata"), (
        "bob3.spawn does not export verify_project_metadata"
    )
    assert callable(spawn_mod.verify_project_metadata)


def test_projectmetadatacheckresult_importable_from_spawn():
    """bob3.spawn.ProjectMetadataCheckResult must be importable."""
    import bob3.spawn as spawn_mod
    assert hasattr(spawn_mod, "ProjectMetadataCheckResult"), (
        "bob3.spawn does not export ProjectMetadataCheckResult"
    )


def test_verify_project_metadata_importable_from_run_loop():
    """bob3.run_loop.verify_project_metadata must be importable."""
    import bob3.run_loop as rl
    assert hasattr(rl, "verify_project_metadata"), (
        "bob3.run_loop does not export verify_project_metadata"
    )
    assert callable(rl.verify_project_metadata)


# ---------------------------------------------------------------------------
# Helper: create a minimal sqlite DB with a projects row
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path, name: str, spec_path: str = "") -> Path:
    db_path = tmp_path / "bob3.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, spec_path TEXT)"
    )
    conn.execute(
        "INSERT INTO projects (id, name, spec_path) VALUES (?, ?, ?)",
        ("proj-1", name, spec_path),
    )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Core behaviour: name correction
# ---------------------------------------------------------------------------

def test_stale_name_detected_and_corrected(tmp_path):
    """When projects.name differs from workspace basename, it must be updated."""
    from bob3.spawn import verify_project_metadata

    # DB says "bob64" but workspace is actually "bob65"
    db_path = _make_db(tmp_path, name="bob64")
    workspace = tmp_path / "bob65"
    workspace.mkdir()

    result = verify_project_metadata(workspace=workspace, db_path=db_path)

    assert result.name_was_stale is True
    assert result.corrected_name == "bob65"
    assert result.workspace_basename == "bob65"

    # Verify the DB was actually updated
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT name FROM projects LIMIT 1").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "bob65"


def test_correct_name_not_updated(tmp_path):
    """When projects.name already matches workspace basename, no update occurs."""
    from bob3.spawn import verify_project_metadata

    workspace = tmp_path / "bob65"
    workspace.mkdir()
    db_path = _make_db(tmp_path, name="bob65")

    result = verify_project_metadata(workspace=workspace, db_path=db_path)

    assert result.name_was_stale is False
    assert result.corrected_name is None
    assert result.workspace_basename == "bob65"


def test_result_is_named_tuple():
    """verify_project_metadata must return a ProjectMetadataCheckResult NamedTuple."""
    from bob3.spawn import verify_project_metadata, ProjectMetadataCheckResult
    import inspect

    # Inspect that ProjectMetadataCheckResult is a NamedTuple
    assert hasattr(ProjectMetadataCheckResult, "_fields"), (
        "ProjectMetadataCheckResult does not have _fields (not a NamedTuple?)"
    )
    expected_fields = {"name_was_stale", "spec_path_was_stale", "corrected_name", "workspace_basename"}
    assert expected_fields <= set(ProjectMetadataCheckResult._fields), (
        f"Missing fields in ProjectMetadataCheckResult: "
        f"{expected_fields - set(ProjectMetadataCheckResult._fields)}"
    )


# ---------------------------------------------------------------------------
# Pytest tmpdir leak detection
# ---------------------------------------------------------------------------

def test_pytest_tmpdir_spec_path_detected(tmp_path):
    """spec_path containing 'pytest-of-' is flagged as stale."""
    from bob3.spawn import verify_project_metadata

    workspace = tmp_path / "bob65"
    workspace.mkdir()
    stale_spec = "/tmp/pytest-of-root/test_session0/minimal.yaml"
    db_path = _make_db(tmp_path, name="bob65", spec_path=stale_spec)

    result = verify_project_metadata(workspace=workspace, db_path=db_path)

    assert result.spec_path_was_stale is True


def test_clean_spec_path_not_flagged(tmp_path):
    """A real spec_path (no pytest-of- prefix) must not be flagged as stale."""
    from bob3.spawn import verify_project_metadata

    workspace = tmp_path / "bob65"
    workspace.mkdir()
    # Use a path that definitively does NOT contain "pytest-of-"
    real_spec = "/home/yelkhamr/dark-factory/bob65/examples/bootstrap_v0.64.yaml"
    db_path = _make_db(tmp_path, name="bob65", spec_path=real_spec)

    result = verify_project_metadata(workspace=workspace, db_path=db_path)

    assert result.spec_path_was_stale is False


def test_empty_db_no_crash(tmp_path):
    """When the projects table is empty, verify_project_metadata must not raise."""
    from bob3.spawn import verify_project_metadata

    db_path = tmp_path / "bob3.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, spec_path TEXT)"
    )
    conn.commit()
    conn.close()

    workspace = tmp_path / "bob65"
    workspace.mkdir()

    result = verify_project_metadata(workspace=workspace, db_path=db_path)

    assert result.name_was_stale is False
    assert result.spec_path_was_stale is False


def test_logs_correction_on_stale_name(tmp_path, caplog):
    """A stale name must produce a log message at INFO level."""
    from bob3.spawn import verify_project_metadata

    workspace = tmp_path / "bob65"
    workspace.mkdir()
    db_path = _make_db(tmp_path, name="bob64")

    with caplog.at_level(logging.INFO, logger="bob3"):
        verify_project_metadata(workspace=workspace, db_path=db_path)

    messages = caplog.text
    assert "bob65" in messages or "corrected" in messages.lower() or "stale" in messages.lower(), (
        "Expected a log message about the stale name correction"
    )


# ---------------------------------------------------------------------------
# AC: integration: bob3.run_loop — _run_locked calls verify_project_metadata
# ---------------------------------------------------------------------------

def test_run_locked_calls_verify_project_metadata():
    """orchestrator.run_loop._run_locked must import and call verify_project_metadata."""
    import ast
    import inspect
    from bob3.orchestrator import run_loop as orl

    source = inspect.getsource(orl.OrchestrationLoop._run_locked)
    # The integration was added as a try/except block calling verify_project_metadata
    assert "verify_project_metadata" in source, (
        "_run_locked does not call verify_project_metadata — integration AC not met"
    )


def test_run_locked_integration_imports_from_bob3_run_loop():
    """The _run_locked integration must import from bob3.run_loop (not orchestrator)."""
    import inspect
    from bob3.orchestrator import run_loop as orl

    source = inspect.getsource(orl.OrchestrationLoop._run_locked)
    assert "from bob3.run_loop import verify_project_metadata" in source, (
        "_run_locked does not import verify_project_metadata from bob3.run_loop"
    )


def test_verify_project_metadata_called_at_startup_before_resume(tmp_path):
    """verify_project_metadata must be called before _resume_interrupted_work."""
    import inspect
    from bob3.orchestrator import run_loop as orl

    source = inspect.getsource(orl.OrchestrationLoop._run_locked)
    meta_pos = source.find("verify_project_metadata")
    resume_pos = source.find("_resume_interrupted_work")

    assert meta_pos != -1, "verify_project_metadata not found in _run_locked source"
    assert resume_pos != -1, "_resume_interrupted_work not found in _run_locked source"
    assert meta_pos < resume_pos, (
        "verify_project_metadata call appears AFTER _resume_interrupted_work — "
        "must run at startup before any other loop work"
    )


def test_spawn_verify_is_same_fn_as_run_loop_verify():
    """bob3.spawn.verify_project_metadata must be the same callable as bob3.run_loop's."""
    from bob3 import spawn as spawn_mod
    from bob3 import run_loop as rl_mod

    assert spawn_mod.verify_project_metadata is rl_mod.verify_project_metadata, (
        "bob3.spawn.verify_project_metadata is not the same object as "
        "bob3.run_loop.verify_project_metadata — spawn.py must re-export from run_loop"
    )
