"""Tests that convergence detection does NOT use UUID (id) as the comparison key.

Acceptance criterion:
- pytest: tests/test_convergence_by_spec_slot_rejects_uuid_comparison.py

Rationale: bob mints fresh UUIDs in every `bob init`, so if check_convergence
compared by features.id, the cross-generation symmetric difference would always
be 100% — the bug this feature fixes.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database
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


def _insert_feature_with_id(db_path, project_id, feature_id, spec_slot, status="completed"):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO features (id, project_id, name, spec_slot, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (feature_id, project_id, f"Feat {spec_slot}", spec_slot, status),
        )
        conn.commit()
    finally:
        conn.close()


class TestConvergenceIgnoresUUID:
    def test_same_spec_slot_different_uuids_are_converged(self, tmp_path, monkeypatch):
        """Two dbs with the same spec_slots but different UUIDs must be converged.

        This is the core regression test for the original bug: UUID comparison
        would report 100% divergence even when both generations implemented
        the same features.
        """
        from bob.migrations.add_spec_slot import get_completed_spec_slots
        from bob.db import init_database

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_a))
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        pid_a = _make_project(db_a)
        pid_b = _make_project(db_b)

        slot = "F-R5-100"
        # Deliberately use different UUIDs for the same logical feature
        _insert_feature_with_id(db_a, pid_a, str(uuid.uuid4()), slot)
        _insert_feature_with_id(db_b, pid_b, str(uuid.uuid4()), slot)

        slots_a = get_completed_spec_slots(db_a)
        slots_b = get_completed_spec_slots(db_b)
        diff = slots_a.symmetric_difference(slots_b)
        assert diff == set(), (
            f"Convergence check must ignore UUID and use spec_slot; got diff={diff}"
        )

    def test_compares_by_spec_slot_returns_true(self):
        """compares_by_spec_slot() must return True (sentinel invariant)."""
        from bob.orchestrator.convergence import compares_by_spec_slot

        assert compares_by_spec_slot() is True

    def test_set_diff_uses_spec_slot_returns_true(self):
        """set_diff_uses_spec_slot() must return True (sentinel invariant)."""
        from bob.orchestrator.convergence import set_diff_uses_spec_slot

        assert set_diff_uses_spec_slot() is True

    def test_get_completed_spec_slots_returns_strings_not_uuids(self, db_path):
        """get_completed_spec_slots must return spec_slot values, not UUID id values."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots

        pid = _make_project(db_path)
        fid = str(uuid.uuid4())
        slot = "F-R7-777"
        _insert_feature_with_id(db_path, pid, fid, slot)

        slots = get_completed_spec_slots(db_path)
        # The slot string must appear, not the UUID
        assert slot in slots
        assert fid not in slots
