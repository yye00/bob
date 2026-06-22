"""Tests for atomic feature claim (1cb15253-ada9-46f2-9341-84950d8135ef).

Verifies that claim_next_ready_feature atomically transitions a feature
from 'ready' to 'executing' and that concurrent workers cannot double-claim
the same row.
"""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

from bob3 import db as bob3_db
from bob3.orchestrator.feature_claim import claim_next_ready_feature


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Create an isolated SQLite database for each test."""
    db_file = tmp_path / "test_claim.db"
    monkeypatch.setenv("BOB3_DATABASE_PATH", str(db_file))
    # Re-initialize tables in the fresh DB.
    from bob3.db import init_database
    init_database(db_path=db_file)
    return db_file


@pytest.fixture()
def project_id(tmp_db):
    """Create a project and return its ID."""
    project = bob3_db.create_project(
        name="Test Project",
        workspace_path="/tmp/test-workspace",
    )
    return project.id


def _make_ready_feature(project_id: str, name: str, priority: int = 100) -> str:
    """Create a ready feature with high readiness scores and return its ID."""
    feature = bob3_db.create_feature(
        project_id=project_id,
        name=name,
        status="ready",
        priority=priority,
    )
    bob3_db.update_feature(
        feature.id,
        readiness_score=0.9,
        conf_spec_understanding=0.9,
        conf_impl_correctness=0.9,
        conf_test_adequacy=0.9,
        risk_category="low",
    )
    return feature.id


# ---------------------------------------------------------------------------
# Basic correctness tests
# ---------------------------------------------------------------------------


def test_claim_returns_none_when_no_ready_features(tmp_db, project_id):
    """claim_next_ready_feature returns None when no features are ready."""
    result = claim_next_ready_feature(project_id=project_id, worker_id="worker-1")
    assert result is None


def test_claim_transitions_feature_to_executing(tmp_db, project_id):
    """Claimed feature is atomically transitioned to 'executing'."""
    fid = _make_ready_feature(project_id, "Feature A")

    feature = claim_next_ready_feature(project_id=project_id, worker_id="worker-1")

    assert feature is not None
    assert feature.id == fid
    assert feature.status == "executing"

    # Verify DB reflects the 'executing' status.
    refreshed = bob3_db.get_feature(fid)
    assert refreshed is not None
    assert refreshed.status == "executing"


def test_claim_picks_highest_priority_first(tmp_db, project_id):
    """When multiple features are ready, the lowest priority value is claimed first."""
    low_id = _make_ready_feature(project_id, "High Priority", priority=10)
    _make_ready_feature(project_id, "Low Priority", priority=200)

    feature = claim_next_ready_feature(project_id=project_id, worker_id="w1")

    assert feature is not None
    assert feature.id == low_id


def test_claim_second_worker_gets_second_feature(tmp_db, project_id):
    """After first claim, second worker claims the next available feature."""
    id_a = _make_ready_feature(project_id, "Feature A", priority=10)
    id_b = _make_ready_feature(project_id, "Feature B", priority=20)

    first = claim_next_ready_feature(project_id=project_id, worker_id="w1")
    second = claim_next_ready_feature(project_id=project_id, worker_id="w2")

    assert first is not None
    assert second is not None
    assert first.id != second.id
    assert {first.id, second.id} == {id_a, id_b}


def test_claim_returns_none_after_all_claimed(tmp_db, project_id):
    """Returns None once all features have been claimed."""
    _make_ready_feature(project_id, "Feature A")

    first = claim_next_ready_feature(project_id=project_id, worker_id="w1")
    second = claim_next_ready_feature(project_id=project_id, worker_id="w2")

    assert first is not None
    assert second is None


def test_claim_skips_pending_features(tmp_db, project_id):
    """Features in 'pending' status are not claimed."""
    # Create a pending feature (the default).
    pending = bob3_db.create_feature(
        project_id=project_id,
        name="Pending Feature",
        status="pending",
    )

    result = claim_next_ready_feature(project_id=project_id, worker_id="w1")
    assert result is None


def test_claim_skips_executing_features(tmp_db, project_id):
    """Features already in 'executing' are not double-claimed."""
    fid = _make_ready_feature(project_id, "Feature A")
    bob3_db.update_feature(fid, status="executing")

    result = claim_next_ready_feature(project_id=project_id, worker_id="w2")
    assert result is None


def test_claim_skips_below_readiness_threshold(tmp_db, project_id):
    """Features below the readiness threshold for their risk category are skipped."""
    feature = bob3_db.create_feature(
        project_id=project_id,
        name="Low Readiness",
        status="ready",
        risk_category="high",  # threshold = 0.90
    )
    bob3_db.update_feature(feature.id, readiness_score=0.5)

    result = claim_next_ready_feature(project_id=project_id, worker_id="w1")
    assert result is None


# ---------------------------------------------------------------------------
# Atomicity / concurrency tests
# ---------------------------------------------------------------------------


def test_concurrent_workers_claim_distinct_features(tmp_db, project_id):
    """Under genuine thread concurrency each feature is claimed at most once."""
    n_features = 5
    feature_ids = set()
    for i in range(n_features):
        fid = _make_ready_feature(project_id, f"Feature {i}", priority=i + 1)
        feature_ids.add(fid)

    n_workers = 10
    results: list = [None] * n_workers
    barrier = threading.Barrier(n_workers)

    def worker(idx: int) -> None:
        barrier.wait()  # all start simultaneously
        results[idx] = claim_next_ready_feature(
            project_id=project_id,
            worker_id=f"worker-{idx}",
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    claimed = [r for r in results if r is not None]
    claimed_ids = [r.id for r in claimed]

    # No feature should be claimed more than once.
    assert len(claimed_ids) == len(set(claimed_ids)), (
        f"Duplicate claims detected: {claimed_ids}"
    )
    # Exactly n_features claims should succeed (workers > features).
    assert len(claimed_ids) == n_features, (
        f"Expected {n_features} claims, got {len(claimed_ids)}"
    )
    # Every claimed id is from the feature set.
    assert set(claimed_ids) == feature_ids


def test_claim_is_atomic_no_double_claim_single_feature(tmp_db, project_id):
    """Only one worker can claim a single feature even under race conditions."""
    fid = _make_ready_feature(project_id, "Contested Feature")

    n_workers = 20
    results: list = [None] * n_workers
    barrier = threading.Barrier(n_workers)

    def worker(idx: int) -> None:
        barrier.wait()
        results[idx] = claim_next_ready_feature(
            project_id=project_id,
            worker_id=f"w-{idx}",
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1, (
        f"Expected exactly 1 claim, got {len(claimed)}: {[r.id for r in claimed]}"
    )
    assert claimed[0].id == fid
    assert claimed[0].status == "executing"
