"""Tests that convergence comparison correctly handles rows with spec_slot=NULL.

Acceptance criterion:
- pytest: tests/test_convergence_by_spec_slot_handles_null_slot_rows.py
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(p))
    from bob3.db import init_database
    init_database(db_path=p)
    return p


def _make_project(db_path) -> str:
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO projects (id, name, workspace_path, status, created_at, updated_at) "
            "VALUES (?, 'Proj', '/tmp/t', 'planning', datetime('now'), datetime('now'))",
            (pid,),
        )
        conn.commit()
    finally:
        conn.close()
    return pid


def _insert_feature(db_path, project_id, spec_slot, status="completed"):
    fid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO features (id, project_id, name, spec_slot, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (fid, project_id, f"Feat {spec_slot}", spec_slot, status),
        )
        conn.commit()
    finally:
        conn.close()
    return fid


class TestNullSlotRowsHandling:
    def test_null_slot_rows_excluded_from_set(self, db_path):
        """get_completed_spec_slots must exclude rows where spec_slot IS NULL."""
        from bob3.migrations.add_spec_slot import get_completed_spec_slots

        pid = _make_project(db_path)
        _insert_feature(db_path, pid, "F-R1-100")
        _insert_feature(db_path, pid, None)  # NULL spec_slot

        slots = get_completed_spec_slots(db_path)
        assert None not in slots
        assert "F-R1-100" in slots
        assert len(slots) == 1

    def test_all_null_slots_returns_empty_set(self, db_path):
        """A db where all features have spec_slot=NULL returns an empty set."""
        from bob3.migrations.add_spec_slot import get_completed_spec_slots

        pid = _make_project(db_path)
        _insert_feature(db_path, pid, None)
        _insert_feature(db_path, pid, None)

        slots = get_completed_spec_slots(db_path)
        assert slots == set()

    def test_mixed_null_and_non_null_returns_only_non_null(self, db_path):
        """Only non-NULL spec_slots should appear in the comparison set."""
        from bob3.migrations.add_spec_slot import get_completed_spec_slots

        pid = _make_project(db_path)
        _insert_feature(db_path, pid, "F-R2-010")
        _insert_feature(db_path, pid, None)
        _insert_feature(db_path, pid, "F-R2-020")
        _insert_feature(db_path, pid, None)

        slots = get_completed_spec_slots(db_path)
        assert slots == {"F-R2-010", "F-R2-020"}

    def test_null_slot_rows_do_not_affect_convergence_result(self, tmp_path, monkeypatch):
        """Two dbs with identical real slots converge even if both have NULL rows."""
        from bob3.migrations.add_spec_slot import get_completed_spec_slots
        from bob3.db import init_database

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_a))
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        pid_a = _make_project(db_a)
        pid_b = _make_project(db_b)

        _insert_feature(db_a, pid_a, "F-R1-100")
        _insert_feature(db_a, pid_a, None)  # noise — should be ignored
        _insert_feature(db_b, pid_b, "F-R1-100")
        _insert_feature(db_b, pid_b, None)  # noise — should be ignored

        slots_a = get_completed_spec_slots(db_a)
        slots_b = get_completed_spec_slots(db_b)
        diff = slots_a.symmetric_difference(slots_b)
        assert diff == set(), f"Expected converged, got diff={diff}"
