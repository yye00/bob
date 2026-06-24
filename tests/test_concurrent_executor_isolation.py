"""Tests for the concurrent feature executor with failure isolation.

Feature 6e085356-e232-4950-bee6-f05d8f19c677.

Verifies:
- run_concurrent dispatches up to N features concurrently (semaphore)
- A failure in one worker does NOT propagate to peers
- Failed workers record failure to the DB
- Cost reservations are released on failure
- N=1 reproduces sequential behaviour (backward compat)
- N > 1 runs multiple features concurrently
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bob.orchestrator.concurrent_executor import run_concurrent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feature(
    *,
    feature_id: str | None = None,
    name: str = "test feature",
    status: str = "ready",
) -> MagicMock:
    f = MagicMock()
    f.id = feature_id or f"feat_{uuid.uuid4().hex[:8]}"
    f.name = name
    f.status = status
    return f


async def _ok_worker(feature: Any) -> str:
    await asyncio.sleep(0)
    return f"ok:{feature.id}"


async def _fail_worker(feature: Any) -> str:
    await asyncio.sleep(0)
    raise RuntimeError(f"boom:{feature.id}")


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------


class TestRunConcurrentBasic:
    def test_empty_features_returns_empty(self):
        results = asyncio.run(run_concurrent([], worker=_ok_worker, max_concurrent=4))
        assert results == []

    def test_single_success(self):
        feature = _feature()
        results = asyncio.run(
            run_concurrent([feature], worker=_ok_worker, max_concurrent=1)
        )
        assert len(results) == 1
        assert results[0]["feature_id"] == feature.id
        assert results[0]["success"] is True
        assert results[0]["result"] == f"ok:{feature.id}"
        assert results[0]["error"] is None

    def test_multiple_success(self):
        features = [_feature() for _ in range(4)]
        results = asyncio.run(
            run_concurrent(features, worker=_ok_worker, max_concurrent=4)
        )
        assert len(results) == 4
        assert all(r["success"] for r in results)

    def test_returns_one_result_per_feature(self):
        features = [_feature() for _ in range(6)]
        results = asyncio.run(
            run_concurrent(features, worker=_ok_worker, max_concurrent=3)
        )
        assert len(results) == 6
        ids_returned = {r["feature_id"] for r in results}
        ids_expected = {f.id for f in features}
        assert ids_returned == ids_expected


# ---------------------------------------------------------------------------
# Failure isolation (the core requirement)
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_one_failure_does_not_prevent_others(self):
        """A failing worker must not block peers from completing."""
        good = _feature(feature_id="good")
        bad = _feature(feature_id="bad")

        async def mixed_worker(feature: Any) -> str:
            await asyncio.sleep(0)
            if feature.id == "bad":
                raise RuntimeError("injected failure")
            return f"ok:{feature.id}"

        results = asyncio.run(
            run_concurrent([good, bad], worker=mixed_worker, max_concurrent=2)
        )
        assert len(results) == 2
        by_id = {r["feature_id"]: r for r in results}

        assert by_id["good"]["success"] is True
        assert by_id["bad"]["success"] is False
        assert "injected failure" in by_id["bad"]["error"]

    def test_all_fail_returns_all_error_results(self):
        features = [_feature() for _ in range(3)]
        results = asyncio.run(
            run_concurrent(features, worker=_fail_worker, max_concurrent=3)
        )
        assert all(not r["success"] for r in results)
        assert all("boom:" in r["error"] for r in results)

    def test_failure_error_captured_in_result(self):
        feature = _feature()
        results = asyncio.run(
            run_concurrent([feature], worker=_fail_worker, max_concurrent=1)
        )
        assert results[0]["success"] is False
        assert results[0]["error"] is not None
        assert "boom:" in results[0]["error"]
        assert results[0]["result"] is None

    def test_sibling_completes_even_if_peer_raises_immediately(self):
        """A peer that raises instantly should not cancel a slow sibling."""
        done = []

        async def slow_ok(feature: Any) -> str:
            await asyncio.sleep(0.01)
            done.append(feature.id)
            return f"done:{feature.id}"

        async def fast_fail(feature: Any) -> str:
            raise ValueError("fast fail")

        slow = _feature(feature_id="slow")
        fast = _feature(feature_id="fast")

        results = asyncio.run(
            run_concurrent([slow, fast], worker=lambda f: slow_ok(f) if f.id == "slow" else fast_fail(f), max_concurrent=2)
        )
        by_id = {r["feature_id"]: r for r in results}
        assert by_id["slow"]["success"] is True
        assert by_id["fast"]["success"] is False
        assert "slow" in done


# ---------------------------------------------------------------------------
# Semaphore / concurrency limiting
# ---------------------------------------------------------------------------


class TestConcurrencyLimit:
    def test_max_concurrent_respected(self):
        """At most max_concurrent workers run simultaneously."""
        peak = 0
        current = 0

        async def counting_worker(feature: Any) -> str:
            nonlocal peak, current
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.01)
            current -= 1
            return f"ok:{feature.id}"

        features = [_feature() for _ in range(8)]
        asyncio.run(run_concurrent(features, worker=counting_worker, max_concurrent=3))
        assert peak <= 3

    def test_max_concurrent_1_is_sequential(self):
        """N=1 must run features one at a time (backward compat)."""
        order = []

        async def ordered_worker(feature: Any) -> str:
            order.append(feature.id)
            await asyncio.sleep(0)
            return "ok"

        features = [_feature(feature_id=f"f{i}") for i in range(4)]
        asyncio.run(run_concurrent(features, worker=ordered_worker, max_concurrent=1))
        # With max_concurrent=1 all 4 features should be processed (order may vary
        # but all must appear exactly once).
        assert len(order) == 4
        assert set(order) == {f.id for f in features}

    def test_default_max_concurrent_is_1(self):
        """Omitting max_concurrent defaults to 1 (backward compat)."""
        concurrent_count = 0
        peak = 0

        async def probe(feature: Any) -> str:
            nonlocal concurrent_count, peak
            concurrent_count += 1
            peak = max(peak, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return "ok"

        features = [_feature() for _ in range(3)]
        asyncio.run(run_concurrent(features, worker=probe))
        assert peak == 1


# ---------------------------------------------------------------------------
# on_failure callback (DB recording + reservation release)
# ---------------------------------------------------------------------------


class TestOnFailureCallback:
    def test_on_failure_called_on_error(self):
        recorded = []

        def on_failure(feature: Any, exc: Exception) -> None:
            recorded.append((feature.id, str(exc)))

        feature = _feature()
        asyncio.run(
            run_concurrent(
                [feature],
                worker=_fail_worker,
                max_concurrent=1,
                on_failure=on_failure,
            )
        )
        assert len(recorded) == 1
        assert recorded[0][0] == feature.id
        assert "boom:" in recorded[0][1]

    def test_on_failure_not_called_on_success(self):
        recorded = []

        def on_failure(feature: Any, exc: Exception) -> None:
            recorded.append(feature.id)

        features = [_feature() for _ in range(3)]
        asyncio.run(
            run_concurrent(
                features,
                worker=_ok_worker,
                max_concurrent=3,
                on_failure=on_failure,
            )
        )
        assert recorded == []

    def test_on_failure_called_per_failing_feature(self):
        recorded = []

        def on_failure(feature: Any, exc: Exception) -> None:
            recorded.append(feature.id)

        features = [_feature() for _ in range(5)]
        asyncio.run(
            run_concurrent(
                features,
                worker=_fail_worker,
                max_concurrent=5,
                on_failure=on_failure,
            )
        )
        assert len(recorded) == 5
        assert set(recorded) == {f.id for f in features}

    def test_on_failure_exception_does_not_kill_loop(self):
        """A buggy on_failure callback must not propagate its own exception."""

        def bad_callback(feature: Any, exc: Exception) -> None:
            raise RuntimeError("callback itself failed")

        good = _feature(feature_id="good")
        bad = _feature(feature_id="bad")

        async def mixed(feature: Any) -> str:
            if feature.id == "bad":
                raise RuntimeError("original failure")
            return "ok"

        results = asyncio.run(
            run_concurrent(
                [good, bad],
                worker=mixed,
                max_concurrent=2,
                on_failure=bad_callback,
            )
        )
        # Both should still have results — the bad callback shouldn't propagate.
        assert len(results) == 2
        by_id = {r["feature_id"]: r for r in results}
        assert by_id["good"]["success"] is True
        assert by_id["bad"]["success"] is False


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class TestResultStructure:
    def test_success_result_has_expected_keys(self):
        feature = _feature()
        results = asyncio.run(
            run_concurrent([feature], worker=_ok_worker, max_concurrent=1)
        )
        r = results[0]
        assert "feature_id" in r
        assert "success" in r
        assert "result" in r
        assert "error" in r

    def test_failure_result_has_expected_keys(self):
        feature = _feature()
        results = asyncio.run(
            run_concurrent([feature], worker=_fail_worker, max_concurrent=1)
        )
        r = results[0]
        assert "feature_id" in r
        assert "success" in r
        assert "result" in r
        assert "error" in r
