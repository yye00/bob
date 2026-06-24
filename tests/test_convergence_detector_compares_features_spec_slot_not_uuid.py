"""Tests for convergence_detector_compares_features_spec_slot_not_uuid.

Acceptance criteria:
- File exists: src/bob/convergence_detector_compares_features_spec_slot_not_uuid.py
- Function defined: bob.convergence_detector_compares_features_spec_slot_not_uuid.convergence_detector_compares_features_spec_slot_not_uuid
- pytest: tests/test_convergence_detector_compares_features_spec_slot_not_uuid.py::test_convergence_detector_compares_features_spec_slot_not_uuid
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_db(db_path: Path) -> None:
    """Create a minimal features table with spec_slot support."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                workspace_path TEXT NOT NULL DEFAULT '/tmp/test',
                status TEXT NOT NULL DEFAULT 'planning',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS features (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                acceptance_criteria TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                spec_slot TEXT DEFAULT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _add_features(db_path: Path, slots: list[str], status: str = "completed") -> None:
    """Insert features with the given spec_slots."""
    conn = sqlite3.connect(str(db_path))
    try:
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (pid, "test-project"),
        )
        for slot in slots:
            conn.execute(
                "INSERT INTO features (id, project_id, name, spec_slot, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), pid, f"Feature {slot}", slot, status),
            )
        conn.commit()
    finally:
        conn.close()


def _add_feature_with_uuid_only(db_path: Path, name: str) -> str:
    """Insert a feature with NULL spec_slot; return its UUID."""
    conn = sqlite3.connect(str(db_path))
    try:
        pid = str(uuid.uuid4())
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (pid, "test-project"),
        )
        fid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO features (id, project_id, name, spec_slot, status) "
            "VALUES (?, ?, ?, NULL, 'completed')",
            (fid, pid, name),
        )
        conn.commit()
        return fid
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Primary acceptance-criteria test
# ---------------------------------------------------------------------------


def test_convergence_detector_compares_features_spec_slot_not_uuid(tmp_path):
    """Convergence detector uses spec_slot for comparison, not UUID id.

    This is the primary AC test.  It verifies:
    1. The function is importable from the correct module.
    2. Two DBs with identical spec_slots but completely different UUIDs are
       considered CONVERGED (i.e. UUID is not the comparison key).
    3. Two DBs with different spec_slots are NOT converged.
    4. UUIDs alone (spec_slot=NULL) are excluded from the comparison.
    """
    from bob.convergence_detector_compares_features_spec_slot_not_uuid import (
        convergence_detector_compares_features_spec_slot_not_uuid,
    )

    # --- Case 1: same spec_slots, completely different UUIDs → converged ---
    db_a = tmp_path / "gen_a.db"
    db_b = tmp_path / "gen_b.db"
    _init_db(db_a)
    _init_db(db_b)

    shared_slots = ["F-R1-100", "F-R1-200", "F-R1-300"]
    _add_features(db_a, shared_slots)
    _add_features(db_b, shared_slots)

    converged, diff = convergence_detector_compares_features_spec_slot_not_uuid(db_a, db_b)
    assert converged is True, (
        "Expected converged=True for identical spec_slot sets, "
        f"but diff was non-empty: {diff}"
    )
    assert diff == set(), f"Expected empty diff but got: {diff}"

    # --- Case 2: different spec_slots → NOT converged ---
    db_c = tmp_path / "gen_c.db"
    db_d = tmp_path / "gen_d.db"
    _init_db(db_c)
    _init_db(db_d)

    _add_features(db_c, ["F-R1-100", "F-R1-200"])
    _add_features(db_d, ["F-R1-100", "F-R1-999"])  # F-R1-999 differs

    converged2, diff2 = convergence_detector_compares_features_spec_slot_not_uuid(db_c, db_d)
    assert converged2 is False, (
        "Expected converged=False for diverged spec_slot sets"
    )
    assert len(diff2) > 0, "Expected non-empty diff for diverged generations"
    assert "F-R1-999" in diff2 or "F-R1-200" in diff2, (
        f"Expected differing slot in diff, got: {diff2}"
    )

    # --- Case 3: UUID-only features (spec_slot=NULL) are excluded ---
    db_e = tmp_path / "gen_e.db"
    db_f = tmp_path / "gen_f.db"
    _init_db(db_e)
    _init_db(db_f)

    # Both DBs have a UUID-only feature but different UUIDs — must still converge
    _add_feature_with_uuid_only(db_e, "UUID-only feature in E")
    _add_feature_with_uuid_only(db_f, "UUID-only feature in F")

    converged3, diff3 = convergence_detector_compares_features_spec_slot_not_uuid(db_e, db_f)
    assert converged3 is True, (
        "NULL spec_slot features should be excluded; two DBs with only "
        f"UUID-only (NULL spec_slot) features should converge. diff={diff3}"
    )


# ---------------------------------------------------------------------------
# Additional tests for robustness
# ---------------------------------------------------------------------------


class TestConvergenceDetectorModule:
    def test_function_is_importable(self):
        """The function must be importable from its module."""
        from bob.convergence_detector_compares_features_spec_slot_not_uuid import (
            convergence_detector_compares_features_spec_slot_not_uuid,
        )
        assert callable(convergence_detector_compares_features_spec_slot_not_uuid)

    def test_returns_tuple(self, tmp_path):
        """Function must return a (bool, set) tuple."""
        from bob.convergence_detector_compares_features_spec_slot_not_uuid import (
            convergence_detector_compares_features_spec_slot_not_uuid,
        )
        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        _init_db(db_a)
        _init_db(db_b)

        result = convergence_detector_compares_features_spec_slot_not_uuid(db_a, db_b)
        assert isinstance(result, tuple)
        assert len(result) == 2
        converged, diff = result
        assert isinstance(converged, bool)
        assert isinstance(diff, set)

    def test_empty_dbs_converge(self, tmp_path):
        """Two empty databases (no features) are considered converged."""
        from bob.convergence_detector_compares_features_spec_slot_not_uuid import (
            convergence_detector_compares_features_spec_slot_not_uuid,
        )
        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        _init_db(db_a)
        _init_db(db_b)

        converged, diff = convergence_detector_compares_features_spec_slot_not_uuid(db_a, db_b)
        assert converged is True
        assert diff == set()

    def test_only_completed_features_compared(self, tmp_path):
        """Non-completed features (pending/failed) must not affect convergence."""
        from bob.convergence_detector_compares_features_spec_slot_not_uuid import (
            convergence_detector_compares_features_spec_slot_not_uuid,
        )
        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        _init_db(db_a)
        _init_db(db_b)

        # db_a: F-R1-100 completed + F-R1-200 pending
        _add_features(db_a, ["F-R1-100"], status="completed")
        _add_features(db_a, ["F-R1-200"], status="pending")

        # db_b: F-R1-100 completed only
        _add_features(db_b, ["F-R1-100"], status="completed")

        converged, diff = convergence_detector_compares_features_spec_slot_not_uuid(db_a, db_b)
        # F-R1-200 is pending, not completed, so must be excluded → converged
        assert converged is True, (
            f"Non-completed features must be excluded. diff={diff}"
        )

    def test_backfill_spec_slot_function_importable(self):
        """backfill_spec_slot must also be importable from the module."""
        from bob.convergence_detector_compares_features_spec_slot_not_uuid import (
            backfill_spec_slot,
        )
        assert callable(backfill_spec_slot)
