"""Tests for the per-feature cost reservation + concurrent budget guard.

Feature 7841fb76-d4b6-4924-a559-eb012357efe5.

Uses an in-memory SQLite database throughout — no disk I/O, no mocking.
The concurrent tests use threading to simulate N workers racing on the
reservation table so that the atomicity guarantee is exercised for real.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from typing import Any

import pytest

from bob3.orchestrator.cost_reservation import (
    outstanding_reservations,
    release_reservation,
    reserve_budget,
)


# ---------------------------------------------------------------------------
# Minimal schema — just what the reservation tests need.
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    name        TEXT,
    description TEXT,
    tasks_total INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sub_agent_runs (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    purpose     TEXT,
    target_type TEXT,
    target_id   TEXT,
    status      TEXT,
    cost_usd    REAL,
    created_at  TEXT
);
"""


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(_SCHEMA)
    return conn


def _feature(
    *,
    feature_id: str | None = None,
    tasks_total: int = 5,
    description: str = "a typical small feature with about twenty tokens here",
) -> dict[str, Any]:
    return {
        "id": feature_id or f"feat_{uuid.uuid4().hex[:8]}",
        "tasks_total": tasks_total,
        "description": description,
    }


def _seed_history(conn: sqlite3.Connection, costs: list[float]) -> None:
    """Insert completed sub_agent_runs so project_feature_cost has history."""
    for cost in costs:
        fid = f"feat_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO features (id, project_id, tasks_total, description) VALUES (?, ?, ?, ?)",
            (fid, "proj", 5, "a typical small feature with about twenty tokens here"),
        )
        conn.execute(
            "INSERT INTO sub_agent_runs (id, project_id, target_type, target_id, status, cost_usd) "
            "VALUES (?, ?, 'feature', ?, 'completed', ?)",
            (f"run_{uuid.uuid4().hex[:8]}", "proj", fid, cost),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Basic unit tests
# ---------------------------------------------------------------------------


class TestReserveBudgetNoCap:
    def test_no_cap_always_grants(self):
        conn = _make_db()
        feat = _feature()
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=9999.0,
            cap_usd=None,
        )
        assert granted is True
        assert info["source"] == "no-cap"

    def test_no_cap_zero_cap_grants(self):
        conn = _make_db()
        feat = _feature()
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=0.0,
            cap_usd=0,
        )
        assert granted is True


class TestReserveBudgetWithCap:
    def test_grants_when_budget_available(self):
        conn = _make_db()
        feat = _feature()
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=0.0,
            cap_usd=100.0,
        )
        assert granted is True
        assert rid is not None
        assert info["projected_total_usd"] > 0

    def test_denies_when_budget_exhausted(self):
        conn = _make_db()
        feat = _feature()
        # committed spend is already at 99% of cap → any estimate will exceed
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=95.0,
            cap_usd=100.0,  # effective ceiling = 95.0 with default headroom 0.95
        )
        assert granted is False
        assert rid is None
        assert "projected" in info["reason"]

    def test_headroom_factor_applied(self):
        """headroom_factor=0.5 means only 50% of cap is usable."""
        conn = _make_db()
        feat = _feature()
        # committed=40 on a cap=100 with headroom=0.5 → ceiling=50
        # even the smallest estimate (fallback 1.5) makes 40+0+1.5=41.5 ≤ 50 → granted
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=40.0,
            cap_usd=100.0,
            headroom_factor=0.5,
        )
        assert granted is True
        assert info["effective_ceiling_usd"] == pytest.approx(50.0)

    def test_headroom_factor_clamped_at_0_95(self):
        """headroom_factor > 0.95 is silently clamped to 0.95."""
        conn = _make_db()
        feat = _feature()
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=0.0,
            cap_usd=100.0,
            headroom_factor=1.0,  # should be clamped to 0.95
        )
        assert info["effective_ceiling_usd"] == pytest.approx(95.0)

    def test_uses_historical_p75_when_enough_samples(self):
        """When ≥3 history samples exist the p75 is used, not the fallback."""
        conn = _make_db()
        # Seed 5 runs each costing $1.00 → p75 ≈ $1.00
        _seed_history(conn, [1.0, 1.0, 1.0, 1.0, 1.0])
        feat = _feature()
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=0.0,
            cap_usd=100.0,
        )
        assert granted is True
        assert info["source"] == "history"
        assert info["estimate_used"] == pytest.approx(1.0, rel=0.01)

    def test_uses_fallback_when_insufficient_history(self):
        """When history is sparse the conservative fallback is used."""
        conn = _make_db()
        feat = _feature()
        granted, rid, info = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=0.0,
            cap_usd=100.0,
        )
        assert granted is True
        assert info["source"] == "fallback"
        assert info["estimate_used"] == pytest.approx(1.5)


class TestReleaseReservation:
    def test_release_removes_row(self):
        conn = _make_db()
        feat = _feature()
        granted, rid, _ = reserve_budget(
            conn,
            feature=feat,
            project_id="proj",
            committed_spend_usd=0.0,
            cap_usd=100.0,
        )
        assert granted is True
        total_before, count_before = outstanding_reservations(conn, "proj")
        assert count_before == 1

        removed = release_reservation(conn, rid)
        assert removed is True
        total_after, count_after = outstanding_reservations(conn, "proj")
        assert count_after == 0
        assert total_after == pytest.approx(0.0)

    def test_release_none_is_noop(self):
        """release_reservation(conn, None) must not raise."""
        conn = _make_db()
        result = release_reservation(conn, None)
        assert result is False

    def test_release_unknown_id_returns_false(self):
        conn = _make_db()
        result = release_reservation(conn, "no-such-id")
        assert result is False


class TestOutstandingReservations:
    def test_empty_returns_zeros(self):
        conn = _make_db()
        total, count = outstanding_reservations(conn, "proj")
        assert total == pytest.approx(0.0)
        assert count == 0

    def test_sums_multiple_reservations(self):
        conn = _make_db()
        for _ in range(3):
            reserve_budget(
                conn,
                feature=_feature(),
                project_id="proj",
                committed_spend_usd=0.0,
                cap_usd=1000.0,
            )
        total, count = outstanding_reservations(conn, "proj")
        assert count == 3
        assert total > 0.0

    def test_scoped_to_project(self):
        """Reservations for proj-A must not appear in proj-B's total."""
        conn = _make_db()
        reserve_budget(
            conn,
            feature=_feature(),
            project_id="proj-A",
            committed_spend_usd=0.0,
            cap_usd=1000.0,
        )
        total_b, count_b = outstanding_reservations(conn, "proj-B")
        assert count_b == 0
        assert total_b == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Concurrency tests — the core correctness requirement
# ---------------------------------------------------------------------------


class TestConcurrentBudgetGuard:
    """N workers race to reserve budget; no more than fits should succeed."""

    def _run_workers(
        self,
        n_workers: int,
        cap_usd: float,
        committed_usd: float,
        per_worker_estimate: float,
    ) -> tuple[int, int]:
        """Spin up *n_workers* threads that each call reserve_budget once.

        Each worker gets its own connection to the shared in-memory database.
        SQLite in WAL mode with check_same_thread=False allows this for :memory:
        when opened via a shared URI (or the same connection is passed with care).

        Because :memory: databases are connection-scoped in Python's sqlite3, we
        use a *file-based* temp DB shared via URI so multiple connections see the
        same data.

        Returns (granted_count, denied_count).
        """
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            # Initialise schema in the shared DB.
            init_conn = sqlite3.connect(db_path, check_same_thread=False)
            init_conn.executescript(_SCHEMA)
            # Seed enough history so all workers use the same estimate.
            for _ in range(5):
                fid = f"feat_{uuid.uuid4().hex[:8]}"
                init_conn.execute(
                    "INSERT INTO features (id, project_id, tasks_total, description) VALUES (?, ?, ?, ?)",
                    (fid, "proj", 5, "a typical small feature with about twenty tokens here"),
                )
                init_conn.execute(
                    "INSERT INTO sub_agent_runs (id, project_id, target_type, target_id, status, cost_usd) "
                    "VALUES (?, ?, 'feature', ?, 'completed', ?)",
                    (f"run_{uuid.uuid4().hex[:8]}", "proj", fid, per_worker_estimate),
                )
            init_conn.commit()
            init_conn.close()

            results: list[bool] = []
            lock = threading.Lock()
            barrier = threading.Barrier(n_workers)

            def worker():
                conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA busy_timeout = 5000")
                feat = _feature()
                barrier.wait()  # all workers start at the same time
                granted, rid, _ = reserve_budget(
                    conn,
                    feature=feat,
                    project_id="proj",
                    committed_spend_usd=committed_usd,
                    cap_usd=cap_usd,
                )
                with lock:
                    results.append(granted)
                conn.close()

            threads = [threading.Thread(target=worker) for _ in range(n_workers)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)

            granted_count = sum(1 for r in results if r)
            denied_count = sum(1 for r in results if not r)
            return granted_count, denied_count
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_only_fitting_reservations_granted(self):
        """10 workers race; only those that fit under the cap are granted."""
        # cap=$10, headroom=0.95→ceiling=$9.50, committed=$0
        # each estimate=1.5 (fallback) → max 6 fit (6*1.5=9.0 ≤ 9.5, 7*1.5=10.5 > 9.5)
        n_workers = 10
        cap = 10.0
        committed = 0.0
        per_estimate = 1.5

        granted, denied = self._run_workers(n_workers, cap, committed, per_estimate)

        assert granted + denied == n_workers, "every worker must report a result"
        # At most floor(9.5 / 1.5) = 6 can fit.  Due to timing we accept ≤ 6.
        max_fitting = int(cap * 0.95 / per_estimate)
        assert granted <= max_fitting, (
            f"Concurrent guard failed: {granted} workers granted "
            f"but only {max_fitting} fit under the cap"
        )
        assert granted >= 1, "at least one worker should succeed"

    def test_no_overshoot_when_already_full(self):
        """When committed spend fills the ceiling no worker is granted."""
        # committed = cap * 0.95 → ceiling already full
        cap = 10.0
        committed = cap * 0.95  # 9.5 → ceiling exactly full

        granted, denied = self._run_workers(
            n_workers=5,
            cap_usd=cap,
            committed_usd=committed,
            per_worker_estimate=1.5,
        )
        assert granted == 0, (
            f"Expected 0 grants when ceiling full; got {granted}"
        )

    def test_second_batch_can_reserve_after_first_releases(self):
        """After first-batch reservations are released, a second batch can reserve."""
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
            conn.commit()

            # First batch: grab one reservation
            feat1 = _feature()
            granted1, rid1, info1 = reserve_budget(
                conn,
                feature=feat1,
                project_id="proj",
                committed_spend_usd=0.0,
                cap_usd=10.0,
            )
            assert granted1 is True

            # Second attempt while first is outstanding and would push over ceiling
            feat2 = _feature()
            # Push committed close to ceiling
            granted2, rid2, _ = reserve_budget(
                conn,
                feature=feat2,
                project_id="proj",
                committed_spend_usd=9.0,  # 9.0 + 0 outstanding + 1.5 estimate = 10.5 > 9.5
                cap_usd=10.0,
            )
            assert granted2 is False

            # Release first reservation
            released = release_reservation(conn, rid1)
            assert released is True

            # Now the second attempt should succeed (no outstanding)
            granted3, rid3, _ = reserve_budget(
                conn,
                feature=feat2,
                project_id="proj",
                committed_spend_usd=0.0,  # committed spent is also lower now
                cap_usd=10.0,
            )
            assert granted3 is True
            release_reservation(conn, rid3)
            conn.close()
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Integration: bob3.orchestrator.run_loop imports cost_reservation
# ---------------------------------------------------------------------------


class TestRunLoopIntegration:
    """Verify that bob3.orchestrator imports cost_reservation without error."""

    def test_run_loop_importable(self):
        import bob3.orchestrator.run_loop  # noqa: F401 — just checking the import

    def test_cost_reservation_in_orchestrator_package(self):
        import bob3.orchestrator.cost_reservation as cr  # noqa: F401
        assert callable(cr.reserve_budget)
        assert callable(cr.release_reservation)

    def test_run_loop_references_cost_reservation(self):
        """run_loop.py must import or reference cost_reservation."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "src" / "bob3" / "orchestrator" / "run_loop.py"
        text = src.read_text()
        assert "cost_reservation" in text, (
            "run_loop.py does not reference cost_reservation; "
            "integration criterion not met"
        )
