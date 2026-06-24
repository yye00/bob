"""Tests for check_convergence using spec_slot instead of UUID.

Acceptance criteria:
- pytest: tests/test_convergence_by_spec_slot.py
- integration: tools/weekend_watchdog.sh:check_convergence
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import subprocess
import textwrap

import pytest

WORKSPACE = pathlib.Path(__file__).resolve().parent.parent
WATCHDOG = WORKSPACE / "tools" / "weekend_watchdog.sh"


@pytest.fixture()
def db_path_a(tmp_path, monkeypatch):
    """Create a db for 'generation A' with spec_slot-populated features."""
    p = tmp_path / "gen_a" / "bob.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BOB_DATABASE_PATH", str(p))
    from bob.db import init_database
    init_database(db_path=p)
    return p


@pytest.fixture()
def db_path_b(tmp_path, monkeypatch):
    """Create a db for 'generation B' with spec_slot-populated features."""
    p = tmp_path / "gen_b" / "bob.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    # NOTE: monkeypatch env will already be set to gen_a by db_path_a fixture.
    # We pass db_path explicitly to avoid env collision.
    from bob.db import init_database
    init_database(db_path=p)
    return p


def _add_features(db_path: pathlib.Path, project_id: str, slots: list[str]) -> None:
    """Insert features with the given spec_slots directly into db."""
    import uuid
    conn = sqlite3.connect(str(db_path))
    try:
        for slot in slots:
            fid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO features (id, project_id, name, spec_slot, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'completed', datetime('now'), datetime('now'))",
                (fid, project_id, f"Feature {slot}", slot),
            )
        conn.commit()
    finally:
        conn.close()


def _create_project(db_path: pathlib.Path, name: str = "Test Project") -> str:
    """Create a project in the given db and return its id."""
    import uuid
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO projects (id, name, workspace_path, status, created_at, updated_at) "
            "VALUES (?, ?, '/tmp/test', 'planning', datetime('now'), datetime('now'))",
            (pid, name),
        )
        conn.commit()
    finally:
        conn.close()
    return pid


# ============================================================
# Shell function exists and is callable
# ============================================================


class TestCheckConvergenceFunctionExists:
    def test_watchdog_script_exists(self):
        """weekend_watchdog.sh must exist."""
        assert WATCHDOG.exists(), f"Expected {WATCHDOG} to exist"

    def test_check_convergence_function_defined(self):
        """check_convergence must be defined in weekend_watchdog.sh."""
        content = WATCHDOG.read_text()
        assert "check_convergence" in content, (
            "check_convergence function not found in weekend_watchdog.sh"
        )

    def test_check_convergence_uses_spec_slot(self):
        """check_convergence must reference spec_slot (not features.id)."""
        content = WATCHDOG.read_text()
        # Find the check_convergence function block
        # It should query spec_slot
        assert "spec_slot" in content, (
            "check_convergence does not reference spec_slot — it may still compare by UUID"
        )


# ============================================================
# Python helper: spec_slot set diff logic
# ============================================================


class TestSpecSlotSetDiff:
    """Unit-test the Python-side logic that check_convergence delegates to."""

    def test_identical_slots_returns_empty_diff(self, tmp_path, monkeypatch):
        """Two dbs with the same spec_slots → diff is empty → converged."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"

        # Bootstrap both dbs
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_a))
        from bob.db import init_database
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        pid_a = _create_project(db_a, "Proj A")
        pid_b = _create_project(db_b, "Proj B")

        _add_features(db_a, pid_a, ["F-R1-100", "F-R1-200", "F-R1-300"])
        _add_features(db_b, pid_b, ["F-R1-100", "F-R1-200", "F-R1-300"])

        slots_a = get_completed_spec_slots(db_a)
        slots_b = get_completed_spec_slots(db_b)

        diff = slots_a.symmetric_difference(slots_b)
        assert diff == set(), f"Expected converged (empty diff) but got: {diff}"

    def test_different_slots_returns_nonempty_diff(self, tmp_path, monkeypatch):
        """Two dbs with different spec_slots → diff is non-empty → not converged."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"

        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_a))
        from bob.db import init_database
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        pid_a = _create_project(db_a, "Proj A")
        pid_b = _create_project(db_b, "Proj B")

        _add_features(db_a, pid_a, ["F-R1-100", "F-R1-200"])
        _add_features(db_b, pid_b, ["F-R1-100", "F-R1-300"])  # F-R1-300 != F-R1-200

        slots_a = get_completed_spec_slots(db_a)
        slots_b = get_completed_spec_slots(db_b)

        diff = slots_a.symmetric_difference(slots_b)
        assert len(diff) > 0, "Expected non-empty diff for diverged generations"

    def test_null_spec_slots_excluded(self, tmp_path, monkeypatch):
        """Features with spec_slot=NULL must not be included in the comparison set."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots

        db_a = tmp_path / "a.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db_a))
        from bob.db import init_database
        init_database(db_path=db_a)

        pid_a = _create_project(db_a, "Proj A")
        # Add a feature WITH a spec_slot and one WITHOUT
        _add_features(db_a, pid_a, ["F-R1-100"])

        # Add a feature with NULL spec_slot directly
        import uuid
        conn = sqlite3.connect(str(db_a))
        try:
            fid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO features (id, project_id, name, spec_slot, status, created_at, updated_at) "
                "VALUES (?, ?, 'No-slot feature', NULL, 'completed', datetime('now'), datetime('now'))",
                (fid, pid_a),
            )
            conn.commit()
        finally:
            conn.close()

        slots = get_completed_spec_slots(db_a)
        assert None not in slots
        assert "F-R1-100" in slots
        assert len(slots) == 1


# ============================================================
# get_completed_spec_slots function
# ============================================================


class TestGetCompletedSpecSlots:
    def test_function_importable(self):
        """get_completed_spec_slots must be importable from add_spec_slot."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots
        assert callable(get_completed_spec_slots)

    def test_returns_set(self, tmp_path, monkeypatch):
        """get_completed_spec_slots must return a set."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots

        db = tmp_path / "test.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db))
        from bob.db import init_database
        init_database(db_path=db)

        result = get_completed_spec_slots(db)
        assert isinstance(result, set)

    def test_empty_db_returns_empty_set(self, tmp_path, monkeypatch):
        """An empty database must return an empty set."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots

        db = tmp_path / "test.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db))
        from bob.db import init_database
        init_database(db_path=db)

        result = get_completed_spec_slots(db)
        assert result == set()

    def test_returns_only_completed_features(self, tmp_path, monkeypatch):
        """Only features with status='completed' should be in the set."""
        from bob.migrations.add_spec_slot import get_completed_spec_slots

        db = tmp_path / "test.db"
        monkeypatch.setenv("BOB_DATABASE_PATH", str(db))
        from bob.db import init_database
        init_database(db_path=db)

        pid = _create_project(db, "Proj")

        # Add completed features
        import uuid
        conn = sqlite3.connect(str(db))
        try:
            for slot, status in [("F-R1-100", "completed"), ("F-R1-200", "failed"), ("F-R1-300", "pending")]:
                fid = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO features (id, project_id, name, spec_slot, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                    (fid, pid, f"Feature {slot}", slot, status),
                )
            conn.commit()
        finally:
            conn.close()

        slots = get_completed_spec_slots(db)
        assert "F-R1-100" in slots
        assert "F-R1-200" not in slots
        assert "F-R1-300" not in slots


# ============================================================
# Shell integration: check_convergence exit codes
# ============================================================


class TestCheckConvergenceShellIntegration:
    """Run check_convergence as a bash function via subprocess."""

    def _run_convergence(self, db_a: pathlib.Path, db_b: pathlib.Path) -> tuple[int, str, str]:
        """Helper: call check_convergence from shell and return (rc, stdout, stderr)."""
        script = textwrap.dedent(f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            source "{WATCHDOG}"
            check_convergence "{db_a}" "{db_b}"
        """)
        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr

    def test_converged_exits_0(self, tmp_path, monkeypatch):
        """check_convergence must exit 0 when both dbs have the same spec_slots."""
        monkeypatch.setenv("BOB_DATABASE_PATH", str(tmp_path / "dummy.db"))
        from bob.db import init_database

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        pid_a = _create_project(db_a, "Proj A")
        pid_b = _create_project(db_b, "Proj B")
        _add_features(db_a, pid_a, ["F-R1-100", "F-R1-200"])
        _add_features(db_b, pid_b, ["F-R1-100", "F-R1-200"])

        rc, _out, _err = self._run_convergence(db_a, db_b)
        assert rc == 0, f"Expected exit 0 for converged dbs, got {rc}\nstderr: {_err}"

    def test_diverged_exits_nonzero(self, tmp_path, monkeypatch):
        """check_convergence must exit non-zero when dbs have different spec_slots."""
        monkeypatch.setenv("BOB_DATABASE_PATH", str(tmp_path / "dummy.db"))
        from bob.db import init_database

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        pid_a = _create_project(db_a, "Proj A")
        pid_b = _create_project(db_b, "Proj B")
        _add_features(db_a, pid_a, ["F-R1-100", "F-R1-200"])
        _add_features(db_b, pid_b, ["F-R1-100", "F-R1-999"])  # different

        rc, _out, _err = self._run_convergence(db_a, db_b)
        assert rc != 0, f"Expected non-zero exit for diverged dbs, got {rc}"

    def test_empty_dbs_considered_converged(self, tmp_path, monkeypatch):
        """Two empty dbs (no spec_slots) should be considered converged."""
        monkeypatch.setenv("BOB_DATABASE_PATH", str(tmp_path / "dummy.db"))
        from bob.db import init_database

        db_a = tmp_path / "a.db"
        db_b = tmp_path / "b.db"
        init_database(db_path=db_a)
        init_database(db_path=db_b)

        rc, _out, _err = self._run_convergence(db_a, db_b)
        assert rc == 0, f"Expected exit 0 for both empty dbs, got {rc}\nstderr: {_err}"
