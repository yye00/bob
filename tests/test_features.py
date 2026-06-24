"""Tests for bob.features — spec_slot column management and backfill.

Verifies that backfill_spec_slot correctly populates spec_slot for existing
rows by matching feature names against a spec YAML file.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
import yaml


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT 'proj',
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                spec_slot TEXT DEFAULT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _insert_feature(db_path: Path, name: str, spec_slot: str = None, status: str = "completed") -> str:
    fid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, ?, ?)",
            (fid, name, spec_slot, status),
        )
        conn.commit()
    finally:
        conn.close()
    return fid


def _write_spec(spec_path: Path, features: dict) -> None:
    with open(spec_path, "w") as f:
        yaml.dump({"features": features}, f)


def _get_spec_slot(db_path: Path, fid: str) -> str | None:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT spec_slot FROM features WHERE id = ?", (fid,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_backfill_spec_slot_is_importable():
    """backfill_spec_slot must be importable from bob.features."""
    from bob.features import backfill_spec_slot  # noqa: F401

    assert callable(backfill_spec_slot)


def test_backfill_spec_slot_matches_by_name(tmp_path):
    """backfill_spec_slot must update spec_slot for rows matching feature name in spec."""
    from bob.features import backfill_spec_slot

    db_path = tmp_path / "bob.db"
    spec_path = tmp_path / "spec.yaml"
    _init_db(db_path)
    fid = _insert_feature(db_path, "Convergence detector")
    _write_spec(spec_path, {
        "F-R7-001": {"title": "Convergence detector"},
    })

    updated = backfill_spec_slot(db_path, spec_path)
    assert updated == 1
    assert _get_spec_slot(db_path, fid) == "F-R7-001"


def test_backfill_spec_slot_returns_update_count(tmp_path):
    """backfill_spec_slot must return the number of rows updated."""
    from bob.features import backfill_spec_slot

    db_path = tmp_path / "bob.db"
    spec_path = tmp_path / "spec.yaml"
    _init_db(db_path)
    _insert_feature(db_path, "Feature Alpha")
    _insert_feature(db_path, "Feature Beta")
    _write_spec(spec_path, {
        "F-R1-001": {"title": "Feature Alpha"},
        "F-R1-002": {"title": "Feature Beta"},
    })

    updated = backfill_spec_slot(db_path, spec_path)
    assert updated == 2


def test_backfill_spec_slot_idempotent(tmp_path):
    """Running backfill_spec_slot twice must not double-count or overwrite."""
    from bob.features import backfill_spec_slot

    db_path = tmp_path / "bob.db"
    spec_path = tmp_path / "spec.yaml"
    _init_db(db_path)
    fid = _insert_feature(db_path, "Stable Feature")
    _write_spec(spec_path, {
        "F-R2-010": {"title": "Stable Feature"},
    })

    first = backfill_spec_slot(db_path, spec_path)
    second = backfill_spec_slot(db_path, spec_path)

    assert first == 1
    assert second == 0  # already filled, nothing to update
    assert _get_spec_slot(db_path, fid) == "F-R2-010"


def test_backfill_spec_slot_skips_already_filled(tmp_path):
    """Rows with an existing spec_slot must not be overwritten."""
    from bob.features import backfill_spec_slot

    db_path = tmp_path / "bob.db"
    spec_path = tmp_path / "spec.yaml"
    _init_db(db_path)
    fid = _insert_feature(db_path, "Pre-filled Feature", spec_slot="F-R0-EXISTING")
    _write_spec(spec_path, {
        "F-R1-NEW": {"title": "Pre-filled Feature"},
    })

    updated = backfill_spec_slot(db_path, spec_path)
    assert updated == 0
    assert _get_spec_slot(db_path, fid) == "F-R0-EXISTING"


def test_backfill_spec_slot_no_match_returns_zero(tmp_path):
    """Features not found in spec must not be updated; returns 0."""
    from bob.features import backfill_spec_slot

    db_path = tmp_path / "bob.db"
    spec_path = tmp_path / "spec.yaml"
    _init_db(db_path)
    fid = _insert_feature(db_path, "Unknown Feature")
    _write_spec(spec_path, {
        "F-R1-001": {"title": "Different Feature Name"},
    })

    updated = backfill_spec_slot(db_path, spec_path)
    assert updated == 0
    assert _get_spec_slot(db_path, fid) is None


def test_backfill_spec_slot_adds_column_if_missing(tmp_path):
    """backfill_spec_slot must add the spec_slot column if it doesn't exist yet."""
    from bob.features import backfill_spec_slot

    db_path = tmp_path / "bob.db"
    spec_path = tmp_path / "spec.yaml"

    # Create table WITHOUT spec_slot column
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE features (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    conn.execute(
        "INSERT INTO features (id, name) VALUES (?, ?)",
        (str(uuid.uuid4()), "Legacy Feature"),
    )
    conn.commit()
    conn.close()

    _write_spec(spec_path, {
        "F-R0-LEGACY": {"title": "Legacy Feature"},
    })

    updated = backfill_spec_slot(db_path, spec_path)
    assert updated >= 0  # migration ran without error

    # Confirm column now exists
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
    conn.close()
    assert "spec_slot" in cols
