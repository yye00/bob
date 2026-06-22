"""Tests for bob3.parent_gen_db_inheritance_seed_time.

Covers :func:`parent_gen_db_inheritance_seed_time` — the seed-time function
that stamps bob_(N+1) child features with provenance from bob_N's DB.
"""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import uuid
from datetime import datetime

import pytest

from bob3.parent_gen_db_inheritance_seed_time import parent_gen_db_inheritance_seed_time


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj-1',
    spec_slot TEXT,
    status TEXT DEFAULT 'pending',
    updated_at TEXT,
    parent_status TEXT,
    parent_completed_at TEXT,
    parent_evidence_hash TEXT
);
CREATE TABLE IF NOT EXISTS evidence_artifacts (
    id TEXT PRIMARY KEY,
    feature_id TEXT,
    content TEXT,
    is_current INTEGER DEFAULT 1,
    created_at TEXT
);
"""


def _init_db(path: pathlib.Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _insert_feature(
    path: pathlib.Path,
    *,
    spec_slot: str | None,
    status: str = "completed",
    updated_at: str | None = None,
) -> str:
    fid = str(uuid.uuid4())
    ts = updated_at or datetime.now().isoformat()
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO features (id, project_id, spec_slot, status, updated_at)"
        " VALUES (?,?,?,?,?)",
        (fid, "proj-1", spec_slot, status, ts),
    )
    conn.commit()
    conn.close()
    return fid


def _insert_evidence(path: pathlib.Path, feature_id: str, content: str) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "INSERT INTO evidence_artifacts (id, feature_id, content, is_current, created_at)"
        " VALUES (?,?,?,1,?)",
        (str(uuid.uuid4()), feature_id, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def _read_feature(path: pathlib.Path, feature_id: str) -> dict:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM features WHERE id = ?", (feature_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_parent_gen_db_inheritance_seed_time(tmp_path):
    """Core happy-path: matching spec_slot stamps child row with parent provenance."""
    parent_db = tmp_path / "parent.db"
    child_db = tmp_path / "child.db"

    _init_db(parent_db)
    _init_db(child_db)

    # Insert a completed parent feature with evidence
    parent_fid = _insert_feature(
        parent_db, spec_slot="F-R7-400", status="completed", updated_at="2026-01-01T12:00:00"
    )
    evidence_content = "test evidence payload"
    _insert_evidence(parent_db, parent_fid, evidence_content)
    expected_hash = hashlib.sha256(evidence_content.encode()).hexdigest()

    # Insert a matching child feature (pending, same spec_slot)
    child_fid = _insert_feature(child_db, spec_slot="F-R7-400", status="pending")

    # Run the seed-time inheritance function
    result = parent_gen_db_inheritance_seed_time(
        parent_db_path=parent_db,
        child_db_path=child_db,
    )

    # Verify the child row was stamped
    child_row = _read_feature(child_db, child_fid)
    assert child_row["parent_status"] == "completed"
    assert child_row["parent_completed_at"] == "2026-01-01T12:00:00"
    assert child_row["parent_evidence_hash"] == expected_hash

    # Result should report 1 stamped
    assert result.stamped == 1
    assert result.skipped_no_slot == 0
    assert result.skipped_no_parent_match == 0


def test_parent_gen_db_inheritance_seed_time_needs_human(tmp_path):
    """needs_human parent status is also inherited."""
    parent_db = tmp_path / "parent.db"
    child_db = tmp_path / "child.db"
    _init_db(parent_db)
    _init_db(child_db)

    parent_fid = _insert_feature(
        parent_db, spec_slot="F-R7-401", status="needs_human", updated_at="2026-02-01T08:00:00"
    )
    child_fid = _insert_feature(child_db, spec_slot="F-R7-401", status="pending")

    result = parent_gen_db_inheritance_seed_time(
        parent_db_path=parent_db, child_db_path=child_db
    )

    child_row = _read_feature(child_db, child_fid)
    assert child_row["parent_status"] == "needs_human"
    assert child_row["parent_completed_at"] == "2026-02-01T08:00:00"
    assert child_row["parent_evidence_hash"] is None  # no evidence inserted
    assert result.stamped == 1


def test_parent_gen_db_inheritance_seed_time_regression(tmp_path):
    """regression parent status is also inherited."""
    parent_db = tmp_path / "parent.db"
    child_db = tmp_path / "child.db"
    _init_db(parent_db)
    _init_db(child_db)

    _insert_feature(parent_db, spec_slot="F-R7-402", status="regression")
    child_fid = _insert_feature(child_db, spec_slot="F-R7-402", status="pending")

    result = parent_gen_db_inheritance_seed_time(
        parent_db_path=parent_db, child_db_path=child_db
    )

    child_row = _read_feature(child_db, child_fid)
    assert child_row["parent_status"] == "regression"
    assert result.stamped == 1


def test_parent_gen_db_inheritance_seed_time_pending_not_inherited(tmp_path):
    """pending parent features are NOT inherited."""
    parent_db = tmp_path / "parent.db"
    child_db = tmp_path / "child.db"
    _init_db(parent_db)
    _init_db(child_db)

    _insert_feature(parent_db, spec_slot="F-R7-403", status="pending")
    child_fid = _insert_feature(child_db, spec_slot="F-R7-403", status="pending")

    result = parent_gen_db_inheritance_seed_time(
        parent_db_path=parent_db, child_db_path=child_db
    )

    child_row = _read_feature(child_db, child_fid)
    assert child_row["parent_status"] is None
    assert result.stamped == 0
    assert result.skipped_no_parent_match == 1


def test_parent_gen_db_inheritance_seed_time_no_slot_skipped(tmp_path):
    """Child features without spec_slot are skipped."""
    parent_db = tmp_path / "parent.db"
    child_db = tmp_path / "child.db"
    _init_db(parent_db)
    _init_db(child_db)

    _insert_feature(parent_db, spec_slot="F-R7-404", status="completed")
    child_fid = _insert_feature(child_db, spec_slot=None, status="pending")

    result = parent_gen_db_inheritance_seed_time(
        parent_db_path=parent_db, child_db_path=child_db
    )

    child_row = _read_feature(child_db, child_fid)
    assert child_row["parent_status"] is None
    assert result.skipped_no_slot == 1
    assert result.stamped == 0


def test_parent_gen_db_inheritance_seed_time_missing_parent_db(tmp_path):
    """Missing parent DB raises FileNotFoundError."""
    child_db = tmp_path / "child.db"
    _init_db(child_db)

    with pytest.raises(FileNotFoundError):
        parent_gen_db_inheritance_seed_time(
            parent_db_path=tmp_path / "nonexistent.db",
            child_db_path=child_db,
        )


def test_parent_gen_db_inheritance_seed_time_missing_child_db(tmp_path):
    """Missing child DB raises FileNotFoundError."""
    parent_db = tmp_path / "parent.db"
    _init_db(parent_db)

    with pytest.raises(FileNotFoundError):
        parent_gen_db_inheritance_seed_time(
            parent_db_path=parent_db,
            child_db_path=tmp_path / "nonexistent.db",
        )


def test_parent_gen_db_inheritance_seed_time_no_match_skipped(tmp_path):
    """Child slot with no matching parent is counted as skipped_no_parent_match."""
    parent_db = tmp_path / "parent.db"
    child_db = tmp_path / "child.db"
    _init_db(parent_db)
    _init_db(child_db)

    # Parent has slot A, child has slot B — no match
    _insert_feature(parent_db, spec_slot="F-R7-500", status="completed")
    child_fid = _insert_feature(child_db, spec_slot="F-R7-999", status="pending")

    result = parent_gen_db_inheritance_seed_time(
        parent_db_path=parent_db, child_db_path=child_db
    )

    child_row = _read_feature(child_db, child_fid)
    assert child_row["parent_status"] is None
    assert result.skipped_no_parent_match == 1
    assert result.stamped == 0


def test_parent_gen_db_inheritance_seed_time_multiple_slots(tmp_path):
    """Multiple matching slots all get stamped."""
    parent_db = tmp_path / "parent.db"
    child_db = tmp_path / "child.db"
    _init_db(parent_db)
    _init_db(child_db)

    slots = ["F-R7-100", "F-R7-200", "F-R7-300"]
    for slot in slots:
        _insert_feature(parent_db, spec_slot=slot, status="completed")
        _insert_feature(child_db, spec_slot=slot, status="pending")

    result = parent_gen_db_inheritance_seed_time(
        parent_db_path=parent_db, child_db_path=child_db
    )

    assert result.stamped == 3
    assert result.skipped_no_slot == 0
    assert result.skipped_no_parent_match == 0
