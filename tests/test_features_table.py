"""Tests for bob3.features_table — spec_slot column management."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest


def _create_db(db_path: Path, with_spec_slot: bool = False) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        if with_spec_slot:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL DEFAULT 'proj',
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    spec_slot TEXT DEFAULT NULL
                )
            """)
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL DEFAULT 'proj',
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                )
            """)
        conn.commit()
    finally:
        conn.close()


def _insert_feature(db_path: Path, name: str, spec_slot: str | None = None, status: str = "pending") -> str:
    fid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        if "spec_slot" in cols:
            conn.execute(
                "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, ?, ?)",
                (fid, name, spec_slot, status),
            )
        else:
            conn.execute(
                "INSERT INTO features (id, name, status) VALUES (?, ?, ?)",
                (fid, name, status),
            )
        conn.commit()
    finally:
        conn.close()
    return fid


def _has_column(db_path: Path, column: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(features)").fetchall()}
        return column in cols
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_features_table_module_importable():
    """bob3.features_table must be importable."""
    import bob3.features_table  # noqa: F401


def test_add_spec_slot_column_is_callable():
    """add_spec_slot_column must be a callable."""
    from bob3.features_table import add_spec_slot_column

    assert callable(add_spec_slot_column)


# ---------------------------------------------------------------------------
# add_spec_slot_column — adds column
# ---------------------------------------------------------------------------


def test_add_spec_slot_column_adds_column(tmp_path):
    """add_spec_slot_column must create spec_slot column when absent."""
    from bob3.features_table import add_spec_slot_column

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)
    assert not _has_column(db_path, "spec_slot")

    add_spec_slot_column(db_path=db_path)
    assert _has_column(db_path, "spec_slot")


def test_add_spec_slot_column_is_idempotent(tmp_path):
    """add_spec_slot_column must be safe to call multiple times without error."""
    from bob3.features_table import add_spec_slot_column

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)

    add_spec_slot_column(db_path=db_path)
    add_spec_slot_column(db_path=db_path)  # must not raise

    assert _has_column(db_path, "spec_slot")


def test_add_spec_slot_column_preserves_existing_rows(tmp_path):
    """add_spec_slot_column must not destroy existing feature rows."""
    from bob3.features_table import add_spec_slot_column

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)
    _insert_feature(db_path, "Feature A")
    _insert_feature(db_path, "Feature B")

    add_spec_slot_column(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    finally:
        conn.close()
    assert count == 2


def test_add_spec_slot_column_new_rows_default_to_null(tmp_path):
    """After adding column, existing rows must have spec_slot=NULL (default)."""
    from bob3.features_table import add_spec_slot_column

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)
    _insert_feature(db_path, "Feature A")

    add_spec_slot_column(db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        null_count = conn.execute(
            "SELECT COUNT(*) FROM features WHERE spec_slot IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    assert null_count == 1


# ---------------------------------------------------------------------------
# add_spec_slot_column — backfill via spec YAML
# ---------------------------------------------------------------------------


def test_add_spec_slot_column_backfills_from_yaml(tmp_path):
    """add_spec_slot_column with spec_path must populate spec_slot from YAML."""
    from bob3.features_table import add_spec_slot_column

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)

    fid = _insert_feature(db_path, "My Great Feature")

    spec_yaml = tmp_path / "spec.yaml"
    spec_yaml.write_text(
        "features:\n"
        "  F-R1-001:\n"
        "    title: My Great Feature\n"
        "    description: Some feature\n"
    )

    add_spec_slot_column(db_path=db_path, spec_path=spec_yaml)

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT spec_slot FROM features WHERE id = ?", (fid,)
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == "F-R1-001"


def test_add_spec_slot_column_unmatched_names_stay_null(tmp_path):
    """Features whose names don't match spec keys must remain NULL after backfill."""
    from bob3.features_table import add_spec_slot_column

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)
    _insert_feature(db_path, "Unknown Feature")

    spec_yaml = tmp_path / "spec.yaml"
    spec_yaml.write_text(
        "features:\n"
        "  F-R1-001:\n"
        "    title: A Different Feature\n"
    )

    add_spec_slot_column(db_path=db_path, spec_path=spec_yaml)

    conn = sqlite3.connect(str(db_path))
    try:
        null_count = conn.execute(
            "SELECT COUNT(*) FROM features WHERE spec_slot IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()

    assert null_count == 1


# ---------------------------------------------------------------------------
# backfill_spec_slot — return count
# ---------------------------------------------------------------------------


def test_backfill_spec_slot_returns_updated_count(tmp_path):
    """backfill_spec_slot must return the number of rows that gained a spec_slot."""
    from bob3.features_table import backfill_spec_slot

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)
    _insert_feature(db_path, "Feature One")
    _insert_feature(db_path, "Feature Two")
    _insert_feature(db_path, "Feature Unmapped")

    spec_yaml = tmp_path / "spec.yaml"
    spec_yaml.write_text(
        "features:\n"
        "  F-R1-001:\n"
        "    title: Feature One\n"
        "  F-R1-002:\n"
        "    title: Feature Two\n"
    )

    updated = backfill_spec_slot(db_path=db_path, spec_path=spec_yaml)
    assert updated == 2


def test_backfill_spec_slot_zero_when_no_matches(tmp_path):
    """backfill_spec_slot must return 0 when no names match the spec."""
    from bob3.features_table import backfill_spec_slot

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=False)
    _insert_feature(db_path, "Completely Unrelated Name")

    spec_yaml = tmp_path / "spec.yaml"
    spec_yaml.write_text(
        "features:\n"
        "  F-R1-001:\n"
        "    title: Something Else\n"
    )

    updated = backfill_spec_slot(db_path=db_path, spec_path=spec_yaml)
    assert updated == 0


def test_backfill_spec_slot_skips_already_filled(tmp_path):
    """backfill_spec_slot must not re-count rows that already have a spec_slot."""
    from bob3.features_table import backfill_spec_slot, add_spec_slot_column

    db_path = tmp_path / "test.db"
    _create_db(db_path, with_spec_slot=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO features (id, name, spec_slot, status) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), "Feature One", "F-R1-001", "pending"),
    )
    conn.commit()
    conn.close()

    spec_yaml = tmp_path / "spec.yaml"
    spec_yaml.write_text(
        "features:\n"
        "  F-R1-001:\n"
        "    title: Feature One\n"
    )

    # Already filled — backfill should report 0 new rows updated
    updated = backfill_spec_slot(db_path=db_path, spec_path=spec_yaml)
    assert updated == 0
