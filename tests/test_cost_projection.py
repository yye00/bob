"""Tests for F-R6-307: pre-spawn cost projection gate.

Uses an in-memory sqlite database. No mocked queries — the gate must
work against a real schema (the same one bob3 ships) so a regression
in either the projection or the orchestrator integration would surface
here.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

import pytest

from bob3.orchestrator.cost_projection import (
    DEFAULT_FALLBACK_ESTIMATE_USD,
    MAX_HEADROOM_FACTOR,
    allow_spawn,
    project_feature_cost,
)


# A minimal slice of the bob3 schema that's enough to exercise the
# projection. Keeping it inline avoids dragging in the full db.init
# (which writes to disk and pulls in a forest of helpers).
_SCHEMA = """
CREATE TABLE features (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT,
    description TEXT,
    tasks_total INTEGER DEFAULT 0
);

CREATE TABLE sub_agent_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    purpose TEXT,
    target_type TEXT,
    target_id TEXT,
    status TEXT,
    cost_usd REAL,
    created_at TEXT
);
"""


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    return conn


def _insert_feature(
    conn: sqlite3.Connection,
    *,
    feature_id: str | None = None,
    tasks_total: int = 5,
    description: str = "a typical small feature description with maybe twenty tokens or so to land in the short bucket",
) -> str:
    fid = feature_id or f"feat_{uuid.uuid4().hex[:8]}"
    conn.execute(
        "INSERT INTO features (id, project_id, name, description, tasks_total) "
        "VALUES (?, ?, ?, ?, ?)",
        (fid, "proj_test", "F", description, tasks_total),
    )
    return fid


def _insert_run(
    conn: sqlite3.Connection,
    *,
    target_id: str,
    cost_usd: float | None,
    status: str = "completed",
    target_type: str = "feature",
) -> str:
    rid = f"run_{uuid.uuid4().hex[:8]}"
    conn.execute(
        "INSERT INTO sub_agent_runs (id, project_id, purpose, target_type, target_id, status, cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rid, "proj_test", "implementation", target_type, target_id, status, cost_usd),
    )
    return rid


def _feature_dict(
    *,
    tasks_total: int = 5,
    description: str = "a typical small feature description with maybe twenty tokens or so to land in the short bucket",
) -> dict[str, Any]:
    return {
        "id": f"feat_{uuid.uuid4().hex[:8]}",
        "tasks_total": tasks_total,
        "description": description,
    }


# ---------------------------------------------------------------------------
# project_feature_cost
# ---------------------------------------------------------------------------


def test_empty_history_uses_fallback_default():
    conn = _make_db()
    feature = _feature_dict()

    proj = project_feature_cost(conn, feature)

    assert proj["n_samples"] == 0
    assert proj["source"] == "fallback"
    assert proj["estimate_used"] == DEFAULT_FALLBACK_ESTIMATE_USD
    # Percentiles on an empty list are 0.0 — they're informational only.
    assert proj["p50_usd"] == 0.0
    assert proj["p75_usd"] == 0.0
    assert proj["p95_usd"] == 0.0


def test_five_historical_runs_p75_computed():
    """With 5 same-bucket completed runs, p75 should be the estimate."""

    conn = _make_db()
    feature = _feature_dict(tasks_total=5)

    # Five historical features in the SAME bucket (tasks_total=5 -> "small",
    # description -> "short"). Each gets one completed run.
    sample_costs = [0.10, 0.30, 0.50, 0.70, 0.90]
    for cost in sample_costs:
        fid = _insert_feature(
            conn,
            tasks_total=5,
            description=feature["description"],
        )
        _insert_run(conn, target_id=fid, cost_usd=cost)

    proj = project_feature_cost(conn, feature)

    assert proj["n_samples"] == 5
    assert proj["source"] == "history"
    # Linear-interp p75 over [0.1, 0.3, 0.5, 0.7, 0.9]: idx = 0.75*4 = 3.0
    # -> exactly index 3 -> 0.70.
    assert proj["p75_usd"] == pytest.approx(0.70)
    assert proj["estimate_used"] == pytest.approx(0.70)
    assert proj["p50_usd"] == pytest.approx(0.50)
    # p95 = idx 3.8 -> 0.7 + 0.8*(0.9-0.7) = 0.86
    assert proj["p95_usd"] == pytest.approx(0.86)


def test_history_outside_bucket_is_ignored():
    """Runs against features in a *different* bucket should not contribute."""

    conn = _make_db()
    feature = _feature_dict(tasks_total=5)  # "small" bucket

    # Insert runs against LARGE features — should be ignored.
    for cost in [10.0, 12.0, 15.0, 20.0]:
        fid = _insert_feature(
            conn,
            tasks_total=100,
            description="x " * 300,  # long
        )
        _insert_run(conn, target_id=fid, cost_usd=cost)

    proj = project_feature_cost(conn, feature)
    assert proj["n_samples"] == 0
    assert proj["source"] == "fallback"


def test_failed_and_inflight_runs_excluded_from_history():
    conn = _make_db()
    feature = _feature_dict()

    fid = _insert_feature(
        conn, tasks_total=5, description=feature["description"]
    )
    # Failed + in-flight rows should NOT feed the percentile.
    _insert_run(conn, target_id=fid, cost_usd=99.0, status="failed")
    _insert_run(conn, target_id=fid, cost_usd=99.0, status="running")
    _insert_run(conn, target_id=fid, cost_usd=99.0, status="executing")
    # Only this one counts.
    _insert_run(conn, target_id=fid, cost_usd=0.50, status="completed")

    proj = project_feature_cost(conn, feature)
    assert proj["n_samples"] == 1
    # 1 sample is below MIN_SAMPLES_FOR_BUCKET_ESTIMATE -> fallback.
    assert proj["source"] == "fallback"
    assert proj["estimate_used"] == DEFAULT_FALLBACK_ESTIMATE_USD


# ---------------------------------------------------------------------------
# allow_spawn
# ---------------------------------------------------------------------------


def test_allow_spawn_well_under_cap():
    conn = _make_db()
    feature = _feature_dict()

    allowed, info = allow_spawn(
        conn,
        feature,
        committed_spend_usd=1.0,
        cap_usd=100.0,
        headroom_factor=0.95,
    )

    assert allowed is True
    assert info["projected_total_usd"] < info["effective_ceiling_usd"]
    assert info["estimate_used"] == DEFAULT_FALLBACK_ESTIMATE_USD
    assert "reason" in info
    assert info["headroom_factor"] == pytest.approx(0.95)


def test_allow_spawn_blocks_when_projection_exceeds_cap():
    conn = _make_db()
    feature = _feature_dict()

    # Already spent $9.50 of a $10 cap; headroom 0.95 -> ceiling $9.50;
    # fallback estimate $1.50 puts projected total at $11.00 -> blocked.
    allowed, info = allow_spawn(
        conn,
        feature,
        committed_spend_usd=9.50,
        cap_usd=10.0,
        headroom_factor=0.95,
    )

    assert allowed is False
    assert "cost-cap projection" in info["reason"]
    assert "projected" in info["reason"]
    assert "remaining" in info["reason"]
    assert info["projected_total_usd"] > info["effective_ceiling_usd"]


def test_allow_spawn_counts_outstanding_reservations():
    """In-flight sub-agent runs should be subtracted from headroom."""

    conn = _make_db()
    feature = _feature_dict()

    # Spent $5 of $10; ceiling = 0.95*10 = $9.50; fallback estimate $1.50.
    # Without reservations: projected = 5 + 0 + 1.5 = $6.50 -> allowed.
    allowed_no_resv, info_no_resv = allow_spawn(
        conn, feature, committed_spend_usd=5.0, cap_usd=10.0
    )
    assert allowed_no_resv is True
    assert info_no_resv["outstanding_reservations_count"] == 0

    # Add three in-flight runs (cost_usd=NULL so each gets charged the
    # fallback $1.50). Total reserved = $4.50.
    fid = _insert_feature(conn)
    for status in ("running", "executing", "running"):
        _insert_run(conn, target_id=fid, cost_usd=None, status=status)

    # Now projected = 5 + 4.5 + 1.5 = $11.00 > $9.50 -> blocked.
    allowed_with_resv, info_with_resv = allow_spawn(
        conn, feature, committed_spend_usd=5.0, cap_usd=10.0
    )

    assert info_with_resv["outstanding_reservations_count"] == 3
    assert info_with_resv["outstanding_reservations_usd"] == pytest.approx(4.5)
    assert allowed_with_resv is False


def test_allow_spawn_uses_partial_cost_for_reservations():
    """In-flight rows with a recorded cost_usd should use that value."""

    conn = _make_db()
    feature = _feature_dict()
    fid = _insert_feature(conn)
    _insert_run(conn, target_id=fid, cost_usd=2.50, status="running")
    _insert_run(conn, target_id=fid, cost_usd=None, status="executing")

    _, info = allow_spawn(
        conn, feature, committed_spend_usd=0.0, cap_usd=100.0
    )
    # 2.50 (recorded) + 1.50 (fallback for NULL) = 4.00.
    assert info["outstanding_reservations_usd"] == pytest.approx(4.0)
    assert info["outstanding_reservations_count"] == 2


def test_allow_spawn_headroom_clamped_to_ceiling():
    """A caller passing 1.0 (or higher) must NOT disable the gate."""

    conn = _make_db()
    feature = _feature_dict()

    _, info = allow_spawn(
        conn,
        feature,
        committed_spend_usd=0.0,
        cap_usd=100.0,
        headroom_factor=1.5,  # naughty
    )
    assert info["headroom_factor"] == pytest.approx(MAX_HEADROOM_FACTOR)
    assert info["effective_ceiling_usd"] == pytest.approx(MAX_HEADROOM_FACTOR * 100.0)


def test_allow_spawn_no_cap_always_allows():
    conn = _make_db()
    feature = _feature_dict()

    allowed, info = allow_spawn(
        conn, feature, committed_spend_usd=999999.0, cap_usd=None
    )
    assert allowed is True
    assert info["source"] == "no-cap"


def test_allow_spawn_accepts_object_feature():
    """Should accept Feature-like objects, not just dicts."""

    conn = _make_db()

    class _FakeFeature:
        id = "feat_obj"
        tasks_total = 5
        description = "a description"

    allowed, info = allow_spawn(
        conn, _FakeFeature(), committed_spend_usd=0.0, cap_usd=100.0
    )
    assert allowed is True
    assert info["estimate_used"] == DEFAULT_FALLBACK_ESTIMATE_USD


def test_allow_spawn_handles_missing_table_gracefully():
    """If sub_agent_runs is absent the gate must NOT crash — it should
    silently treat history/reservations as zero."""

    conn = sqlite3.connect(":memory:")
    # Only features table; no sub_agent_runs.
    conn.executescript(
        "CREATE TABLE features ("
        "id TEXT PRIMARY KEY, project_id TEXT, name TEXT, description TEXT, "
        "tasks_total INTEGER);"
    )

    proj = project_feature_cost(conn, _feature_dict())
    assert proj["n_samples"] == 0
    assert proj["source"] == "fallback"

    allowed, info = allow_spawn(
        conn, _feature_dict(), committed_spend_usd=0.0, cap_usd=100.0
    )
    assert allowed is True
    assert info["outstanding_reservations_usd"] == 0.0


# ---------------------------------------------------------------------------
# Integration with the orchestrator: a spawn attempt under a tight cap
# should mark the feature needs_human WITHOUT actually spawning.
# ---------------------------------------------------------------------------


def test_run_loop_integration_blocks_spawn_and_marks_needs_human(
    monkeypatch, tmp_path
):
    """Walk one execute_feature call with a budget too tight to spawn.

    Verifies:
      * cost-projection gate refuses the spawn,
      * the feature transitions to ``needs_human``,
      * the spawn helper (claude_executor.spawn_sub_agent) is NOT called.
    """

    import asyncio

    from bob3 import db
    from bob3.orchestrator import run_loop as rl

    # Isolate the test database.
    db_path = tmp_path / "bob3_test.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_path))
    # conftest defaults the gate OFF for the rest of the suite; this test
    # exercises the gate so flip it on.
    monkeypatch.setenv("BOB3_COST_PROJECTION_GATE", "1")
    db.init_database(db_path=db_path)

    # Create a project at its cost cap already.
    project = db.create_project(
        name="cap-test",
        workspace_path=str(tmp_path),
        max_cost_usd=10.0,
        total_cost_usd=9.80,
    )

    # Create a small feature, mark it ready.
    feature = db.create_feature(
        project_id=project.id,
        name="small thing",
        description="implement a small thing",
        priority=10,
    )
    # tasks_total isn't accepted by create_feature; write directly.
    with db.connect() as conn:
        conn.execute(
            "UPDATE features SET tasks_total = ?, status = ? WHERE id = ?",
            (5, "ready", feature.id),
        )

    # Construct a loop targeting that feature with the same tight cap.
    loop = rl.OrchestrationLoop(
        project_id=project.id,
        max_cost=10.0,
        workspace=str(tmp_path),
        target_feature_id=feature.id,
    )

    # Sentinel: if execute_feature actually reaches spawn_sub_agent, fail.
    spawn_calls: list[Any] = []

    async def _explode(*args, **kwargs):
        spawn_calls.append((args, kwargs))
        raise AssertionError(
            "spawn_sub_agent must not be called when the projection gate fires"
        )

    monkeypatch.setattr(rl, "spawn_sub_agent", _explode)

    # Run a single execute_feature.
    feature_fresh = db.get_feature(feature.id)
    asyncio.run(loop.execute_feature(feature_fresh))

    # Spawn was never attempted.
    assert spawn_calls == []

    # Feature ended up needs_human with a cost-projection reason logged
    # somewhere (the loop logs it; we assert the status transition here).
    final = db.get_feature(feature.id)
    assert final.status == "needs_human", (
        f"expected needs_human, got {final.status!r}"
    )
