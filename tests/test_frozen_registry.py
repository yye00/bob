"""Tests for frozen-registry mode.

Covers:
- freeze_registry() sets the frozen flag and emits a warning
- is_registry_frozen() reflects the current state
- import_registry() raises RuntimeError when frozen
- load_transfer_registry_if_configured() returns None when frozen
- activate_frozen_registry_if_configured() reads BOB3_FROZEN_REGISTRY env var
- telemetry lines include frozen_registry=true when active
- freeze_registry() is idempotent
"""

from __future__ import annotations

import json
import os
import uuid
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

import bob3.registry_transfer as registry_transfer_module
from bob3.registry_transfer import (
    activate_frozen_registry_if_configured,
    freeze_registry,
    is_registry_frozen,
    import_registry,
    export_registry,
    load_transfer_registry_if_configured,
)
from bob3.db import get_connection, init_database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "bob3.db"
    init_database(db_path=db_path)
    return db_path


def _insert_project(conn, project_id: str | None = None) -> str:
    if project_id is None:
        project_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects (id, name, workspace_path, created_at) "
        "VALUES (?, ?, ?, datetime('now'))",
        (project_id, f"project-{project_id[:8]}", f"/tmp/{project_id}"),
    )
    conn.commit()
    return project_id


# ---------------------------------------------------------------------------
# Tests: freeze_registry() / is_registry_frozen()
# ---------------------------------------------------------------------------

def test_freeze_registry_sets_flag():
    """freeze_registry() must set the frozen flag to True."""
    assert not is_registry_frozen()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        freeze_registry(warn=False)
    assert is_registry_frozen()


def test_freeze_registry_emits_warning():
    """freeze_registry() must emit a UserWarning when warn=True."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        freeze_registry(warn=True)
    assert any(issubclass(warning.category, UserWarning) for warning in w), (
        "Expected a UserWarning from freeze_registry(warn=True)"
    )
    warning_messages = [str(warning.message) for warning in w if issubclass(warning.category, UserWarning)]
    assert any("FROZEN" in msg.upper() or "frozen" in msg.lower() for msg in warning_messages)


def test_freeze_registry_no_warning_when_warn_false():
    """freeze_registry(warn=False) must not emit a UserWarning."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        freeze_registry(warn=False)
    user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
    assert user_warnings == [], "Expected no UserWarning when warn=False"


def test_freeze_registry_idempotent():
    """Calling freeze_registry() twice is safe and keeps the flag set."""
    freeze_registry(warn=False)
    freeze_registry(warn=False)
    assert is_registry_frozen()


def test_is_registry_frozen_initially_false():
    """Before any freeze call the registry must not be frozen."""
    assert not is_registry_frozen()


# ---------------------------------------------------------------------------
# Tests: import_registry() blocked when frozen
# ---------------------------------------------------------------------------

def test_import_registry_raises_when_frozen(tmp_path):
    """import_registry() must raise RuntimeError in frozen mode."""
    db_path = _make_db(tmp_path)
    conn = get_connection(db_path=db_path)
    project_id = _insert_project(conn)
    conn.close()

    # Build a minimal valid export file
    export_data = {
        "project_id": project_id,
        "bug_ledger": [],
        "calibration_data": [],
        "skill_lessons": {},
    }
    export_path = tmp_path / "export.json"
    export_path.write_text(json.dumps(export_data), encoding="utf-8")

    freeze_registry(warn=False)

    with pytest.raises(RuntimeError, match="frozen"):
        import_registry(export_path, project_id, db_path=db_path)


# ---------------------------------------------------------------------------
# Tests: load_transfer_registry_if_configured() skipped when frozen
# ---------------------------------------------------------------------------

def test_load_transfer_registry_skipped_when_frozen(tmp_path, monkeypatch):
    """load_transfer_registry_if_configured() returns None in frozen mode."""
    db_path = _make_db(tmp_path)
    conn = get_connection(db_path=db_path)
    project_id = _insert_project(conn)
    conn.close()

    export_data = {
        "project_id": project_id,
        "bug_ledger": [],
        "calibration_data": [],
        "skill_lessons": {},
    }
    export_path = tmp_path / "transfer.json"
    export_path.write_text(json.dumps(export_data), encoding="utf-8")
    monkeypatch.setenv("BOB3_REGISTRY_TRANSFER_PATH", str(export_path))

    freeze_registry(warn=False)
    result = load_transfer_registry_if_configured(project_id, db_path=db_path)
    assert result is None


# ---------------------------------------------------------------------------
# Tests: activate_frozen_registry_if_configured()
# ---------------------------------------------------------------------------

def test_activate_frozen_registry_env_var_1(monkeypatch):
    """BOB3_FROZEN_REGISTRY=1 activates frozen mode."""
    monkeypatch.setenv("BOB3_FROZEN_REGISTRY", "1")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        activated = activate_frozen_registry_if_configured()
    assert activated is True
    assert is_registry_frozen()


def test_activate_frozen_registry_env_var_true(monkeypatch):
    """BOB3_FROZEN_REGISTRY=true activates frozen mode."""
    monkeypatch.setenv("BOB3_FROZEN_REGISTRY", "true")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        activated = activate_frozen_registry_if_configured()
    assert activated is True
    assert is_registry_frozen()


def test_activate_frozen_registry_env_var_yes(monkeypatch):
    """BOB3_FROZEN_REGISTRY=yes activates frozen mode."""
    monkeypatch.setenv("BOB3_FROZEN_REGISTRY", "yes")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        activated = activate_frozen_registry_if_configured()
    assert activated is True
    assert is_registry_frozen()


def test_activate_frozen_registry_env_var_unset(monkeypatch):
    """Unset BOB3_FROZEN_REGISTRY does not activate frozen mode."""
    monkeypatch.delenv("BOB3_FROZEN_REGISTRY", raising=False)
    activated = activate_frozen_registry_if_configured()
    assert activated is False
    assert not is_registry_frozen()


def test_activate_frozen_registry_env_var_zero(monkeypatch):
    """BOB3_FROZEN_REGISTRY=0 does not activate frozen mode."""
    monkeypatch.setenv("BOB3_FROZEN_REGISTRY", "0")
    activated = activate_frozen_registry_if_configured()
    assert activated is False
    assert not is_registry_frozen()


# ---------------------------------------------------------------------------
# Tests: telemetry includes frozen_registry field
# ---------------------------------------------------------------------------

def test_telemetry_frozen_registry_false_by_default(tmp_path, monkeypatch):
    """Telemetry lines must include frozen_registry=false when not frozen."""
    monkeypatch.chdir(tmp_path)
    run_jsonl = tmp_path / ".bob3" / "run.jsonl"

    from bob3.telemetry import emit_telemetry_line
    emit_telemetry_line("run-abc", feature_id="feat-1")

    assert run_jsonl.exists(), f"Expected telemetry file at {run_jsonl}"
    lines = run_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "Expected at least one telemetry line"
    record = json.loads(lines[-1])
    assert "frozen_registry" in record
    assert record["frozen_registry"] is False


def test_telemetry_frozen_registry_true_when_frozen(tmp_path, monkeypatch):
    """Telemetry lines must include frozen_registry=true when frozen mode is active."""
    monkeypatch.chdir(tmp_path)
    run_jsonl = tmp_path / ".bob3" / "run.jsonl"

    freeze_registry(warn=False)

    from bob3.telemetry import emit_telemetry_line
    emit_telemetry_line("run-xyz", feature_id="feat-frozen")

    assert run_jsonl.exists(), f"Expected telemetry file at {run_jsonl}"
    lines = run_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "Expected at least one telemetry line"
    record = json.loads(lines[-1])
    assert "frozen_registry" in record
    assert record["frozen_registry"] is True


# ---------------------------------------------------------------------------
# Tests: export still works in frozen mode (reads are not blocked)
# ---------------------------------------------------------------------------

def test_export_registry_works_when_frozen(tmp_path):
    """export_registry() must still work when the registry is frozen."""
    db_path = _make_db(tmp_path)
    conn = get_connection(db_path=db_path)
    project_id = _insert_project(conn)
    conn.close()

    freeze_registry(warn=False)

    out_path = tmp_path / "export.json"
    # Should not raise
    export_registry(project_id, out_path, db_path=db_path)
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["project_id"] == project_id
