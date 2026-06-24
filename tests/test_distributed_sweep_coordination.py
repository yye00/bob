"""Tests for src/bob/distributed_sweep_coordination.py

Covers:
- RedisWorkQueue: enqueue, dequeue, ack, nack
- DistributedSweepCoordinator: distribute_plan, run_as_worker, progress events
- Per-node progress events emitted to NFS-mounted JSONL
- Coordinator collects results and returns SweepResult
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bob.distributed_sweep_coordination import (
    DistributedSweepCoordinator,
    NodeProgressEvent,
    RedisWorkQueue,
    WorkItem,
    distribute_sweep,
)
from bob.sweep_orchestrator import SweepPlan, SweepRun, SweepResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_run(variant: str = "V0", spec: str = "spec_a", seed: int = 1) -> SweepRun:
    return SweepRun(variant=variant, spec=spec, seed=seed)


def make_plan(n: int = 3) -> SweepPlan:
    return SweepPlan(runs=[make_run(seed=i) for i in range(n)])


def fake_redis_client() -> MagicMock:
    """A lightweight in-memory Redis mock using a dict + list."""
    store: dict[str, Any] = {}
    lists: dict[str, list[bytes]] = {}

    client = MagicMock()

    def lpush(key: str, value: bytes) -> int:
        lists.setdefault(key, []).insert(0, value)
        return len(lists[key])

    def rpoplpush(src: str, dst: str) -> bytes | None:
        if lists.get(src):
            item = lists[src].pop()
            lists.setdefault(dst, []).insert(0, item)
            return item
        return None

    def lrem(key: str, count: int, value: bytes) -> int:
        lst = lists.get(key, [])
        removed = 0
        new_lst = []
        for item in lst:
            if item == value and removed < abs(count):
                removed += 1
            else:
                new_lst.append(item)
        lists[key] = new_lst
        return removed

    def llen(key: str) -> int:
        return len(lists.get(key, []))

    def lrange(key: str, start: int, end: int) -> list[bytes]:
        lst = lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start : end + 1]

    def rpush(key: str, value: bytes) -> int:
        lists.setdefault(key, []).append(value)
        return len(lists[key])

    def get(key: str) -> bytes | None:
        return store.get(key)

    def set_(key: str, value: bytes, **kwargs: Any) -> bool:
        store[key] = value
        return True

    def delete(*keys: str) -> int:
        count = 0
        for key in keys:
            if key in store:
                del store[key]
                count += 1
            if key in lists:
                del lists[key]
                count += 1
        return count

    def pipeline() -> MagicMock:
        pipe = MagicMock()
        ops: list[tuple] = []

        def pipe_lpush(key: str, value: bytes) -> MagicMock:
            ops.append(("lpush", key, value))
            return pipe

        def pipe_execute() -> list[Any]:
            results = []
            for op in ops:
                if op[0] == "lpush":
                    results.append(lpush(op[1], op[2]))
            return results

        pipe.lpush = pipe_lpush
        pipe.execute = pipe_execute
        return pipe

    client.lpush = lpush
    client.rpoplpush = rpoplpush
    client.lrem = lrem
    client.llen = llen
    client.lrange = lrange
    client.rpush = rpush
    client.get = get
    client.set = set_
    client.delete = delete
    client.pipeline = pipeline
    return client


# ---------------------------------------------------------------------------
# WorkItem
# ---------------------------------------------------------------------------


class TestWorkItem:
    def test_serialise_roundtrip(self):
        run = make_run()
        item = WorkItem(run=run)
        raw = item.to_bytes()
        restored = WorkItem.from_bytes(raw)
        assert restored.run.run_id == run.run_id
        assert restored.run.variant == run.variant
        assert restored.run.spec == run.spec
        assert restored.run.seed == run.seed

    def test_work_item_has_run_id(self):
        run = make_run()
        item = WorkItem(run=run)
        assert item.run.run_id == run.run_id

    def test_different_runs_different_bytes(self):
        item1 = WorkItem(run=make_run(seed=1))
        item2 = WorkItem(run=make_run(seed=2))
        assert item1.to_bytes() != item2.to_bytes()


# ---------------------------------------------------------------------------
# RedisWorkQueue
# ---------------------------------------------------------------------------


class TestRedisWorkQueue:
    def test_enqueue_and_dequeue(self):
        client = fake_redis_client()
        queue = RedisWorkQueue(client=client, queue_name="test_q")
        run = make_run()
        queue.enqueue(WorkItem(run=run))
        item = queue.dequeue(timeout_s=0)
        assert item is not None
        assert item.run.run_id == run.run_id

    def test_dequeue_empty_returns_none(self):
        client = fake_redis_client()
        queue = RedisWorkQueue(client=client, queue_name="test_q")
        item = queue.dequeue(timeout_s=0)
        assert item is None

    def test_enqueue_multiple(self):
        client = fake_redis_client()
        queue = RedisWorkQueue(client=client, queue_name="test_q")
        runs = [make_run(seed=i) for i in range(3)]
        for r in runs:
            queue.enqueue(WorkItem(run=r))
        dequeued_ids = []
        for _ in range(3):
            item = queue.dequeue(timeout_s=0)
            assert item is not None
            dequeued_ids.append(item.run.run_id)
        # all enqueued runs are dequeued exactly once
        assert sorted(dequeued_ids) == sorted(r.run_id for r in runs)

    def test_ack_removes_from_processing(self):
        client = fake_redis_client()
        queue = RedisWorkQueue(client=client, queue_name="test_q")
        run = make_run()
        item = WorkItem(run=run)
        queue.enqueue(item)
        dequeued = queue.dequeue(timeout_s=0)
        assert dequeued is not None
        queue.ack(dequeued)
        # After ack, the processing list should be empty
        assert queue.processing_count() == 0

    def test_nack_returns_item_to_queue(self):
        client = fake_redis_client()
        queue = RedisWorkQueue(client=client, queue_name="test_q")
        run = make_run()
        item = WorkItem(run=run)
        queue.enqueue(item)
        dequeued = queue.dequeue(timeout_s=0)
        assert dequeued is not None
        queue.nack(dequeued)
        # After nack, item is back and can be dequeued again
        requeued = queue.dequeue(timeout_s=0)
        assert requeued is not None
        assert requeued.run.run_id == run.run_id

    def test_queue_size(self):
        client = fake_redis_client()
        queue = RedisWorkQueue(client=client, queue_name="test_q")
        assert queue.pending_count() == 0
        for i in range(5):
            queue.enqueue(WorkItem(run=make_run(seed=i)))
        assert queue.pending_count() == 5

    def test_processing_count_increases_after_dequeue(self):
        client = fake_redis_client()
        queue = RedisWorkQueue(client=client, queue_name="test_q")
        queue.enqueue(WorkItem(run=make_run()))
        queue.dequeue(timeout_s=0)
        assert queue.processing_count() == 1


# ---------------------------------------------------------------------------
# NodeProgressEvent
# ---------------------------------------------------------------------------


class TestNodeProgressEvent:
    def test_event_has_required_fields(self):
        evt = NodeProgressEvent(
            node_id="node-1",
            run_id="abc123",
            event_type="run_started",
            payload={},
        )
        assert evt.node_id == "node-1"
        assert evt.run_id == "abc123"
        assert evt.event_type == "run_started"

    def test_event_serialises_to_json(self):
        evt = NodeProgressEvent(
            node_id="node-1",
            run_id="abc123",
            event_type="run_completed",
            payload={"cost_usd": 0.05},
        )
        raw = evt.to_json()
        data = json.loads(raw)
        assert data["node_id"] == "node-1"
        assert data["run_id"] == "abc123"
        assert data["event_type"] == "run_completed"
        assert data["payload"]["cost_usd"] == pytest.approx(0.05)

    def test_event_has_timestamp(self):
        evt = NodeProgressEvent(
            node_id="node-1",
            run_id="abc",
            event_type="run_started",
            payload={},
        )
        raw = evt.to_json()
        data = json.loads(raw)
        assert "timestamp" in data

    def test_from_json_roundtrip(self):
        evt = NodeProgressEvent(
            node_id="n2",
            run_id="xyz",
            event_type="run_failed",
            payload={"error": "timeout"},
        )
        restored = NodeProgressEvent.from_json(evt.to_json())
        assert restored.node_id == evt.node_id
        assert restored.run_id == evt.run_id
        assert restored.event_type == evt.event_type
        assert restored.payload == evt.payload


# ---------------------------------------------------------------------------
# DistributedSweepCoordinator
# ---------------------------------------------------------------------------


class TestDistributedSweepCoordinator:
    def _make_coordinator(self, tmp_path: Path) -> DistributedSweepCoordinator:
        client = fake_redis_client()
        return DistributedSweepCoordinator(
            redis_client=client,
            events_path=tmp_path / "events.jsonl",
            queue_name="sweep_test",
        )

    def test_coordinator_populates_queue(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(3)
        coord.distribute_plan(plan)
        assert coord.queue.pending_count() == 3

    def test_coordinator_returns_empty_result_for_empty_plan(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = SweepPlan(runs=[])
        coord.distribute_plan(plan)
        result = coord.collect_results(timeout_s=1)
        assert result.completed == []
        assert result.failed == []
        assert result.skipped == []

    def test_run_as_worker_processes_items(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(2)
        coord.distribute_plan(plan)

        executed = []

        def run_one(run: SweepRun) -> float:
            executed.append(run.run_id)
            return 0.01

        coord.run_as_worker(
            node_id="worker-1",
            run_one=run_one,
            stop_when_queue_empty=True,
        )

        assert len(executed) == 2

    def test_worker_emits_progress_events(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(1)
        coord.distribute_plan(plan)

        def run_one(run: SweepRun) -> float:
            return 0.01

        coord.run_as_worker(
            node_id="node-42",
            run_one=run_one,
            stop_when_queue_empty=True,
        )

        events_path = tmp_path / "events.jsonl"
        assert events_path.exists()
        lines = events_path.read_text().strip().split("\n")
        events = [json.loads(line) for line in lines if line]
        event_types = [e["event_type"] for e in events]
        assert "run_started" in event_types
        assert "run_completed" in event_types

    def test_worker_emits_node_id_in_events(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(1)
        coord.distribute_plan(plan)

        def run_one(run: SweepRun) -> float:
            return 0.0

        coord.run_as_worker(
            node_id="my-node",
            run_one=run_one,
            stop_when_queue_empty=True,
        )

        events_path = tmp_path / "events.jsonl"
        lines = events_path.read_text().strip().split("\n")
        events = [json.loads(line) for line in lines if line]
        assert all(e["node_id"] == "my-node" for e in events)

    def test_worker_emits_run_failed_on_exception(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(1)
        coord.distribute_plan(plan)

        def run_one(run: SweepRun) -> float:
            raise RuntimeError("kaboom")

        coord.run_as_worker(
            node_id="worker-err",
            run_one=run_one,
            stop_when_queue_empty=True,
        )

        events_path = tmp_path / "events.jsonl"
        lines = events_path.read_text().strip().split("\n")
        events = [json.loads(line) for line in lines if line]
        event_types = [e["event_type"] for e in events]
        assert "run_failed" in event_types

    def test_collect_results_reads_events_file(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(2)
        coord.distribute_plan(plan)

        def run_one(run: SweepRun) -> float:
            return 0.05

        coord.run_as_worker(
            node_id="solo-worker",
            run_one=run_one,
            stop_when_queue_empty=True,
        )

        result = coord.collect_results(timeout_s=1)
        assert len(result.completed) == 2
        assert len(result.failed) == 0

    def test_collect_results_aggregates_total_cost(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(3)
        coord.distribute_plan(plan)

        def run_one(run: SweepRun) -> float:
            return 0.10

        coord.run_as_worker(
            node_id="worker",
            run_one=run_one,
            stop_when_queue_empty=True,
        )

        result = coord.collect_results(timeout_s=1)
        assert result.total_cost_usd == pytest.approx(0.30, abs=0.001)

    def test_failed_runs_in_result(self, tmp_path: Path):
        coord = self._make_coordinator(tmp_path)
        plan = make_plan(2)
        coord.distribute_plan(plan)
        run_ids = [r.run_id for r in plan.runs]

        call_count = 0

        def run_one(run: SweepRun) -> float:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first fails")
            return 0.0

        coord.run_as_worker(
            node_id="worker",
            run_one=run_one,
            stop_when_queue_empty=True,
        )

        result = coord.collect_results(timeout_s=1)
        assert len(result.failed) == 1
        assert len(result.completed) == 1


# ---------------------------------------------------------------------------
# distribute_sweep convenience function
# ---------------------------------------------------------------------------


class TestDistributeSweep:
    def test_distribute_sweep_end_to_end(self, tmp_path: Path):
        client = fake_redis_client()
        plan = make_plan(3)

        def run_one(run: SweepRun) -> float:
            return 0.01

        result = distribute_sweep(
            plan=plan,
            redis_client=client,
            run_one=run_one,
            node_id="single-node",
            events_path=tmp_path / "events.jsonl",
        )

        assert len(result.completed) == 3
        assert len(result.failed) == 0
        assert result.total_cost_usd == pytest.approx(0.03, abs=0.001)

    def test_distribute_sweep_creates_events_file(self, tmp_path: Path):
        client = fake_redis_client()
        plan = make_plan(1)

        def run_one(run: SweepRun) -> float:
            return 0.0

        distribute_sweep(
            plan=plan,
            redis_client=client,
            run_one=run_one,
            node_id="node-1",
            events_path=tmp_path / "events.jsonl",
        )

        assert (tmp_path / "events.jsonl").exists()

    def test_distribute_sweep_with_failures(self, tmp_path: Path):
        client = fake_redis_client()
        plan = make_plan(2)

        def run_one(run: SweepRun) -> float:
            raise RuntimeError("all fail")

        result = distribute_sweep(
            plan=plan,
            redis_client=client,
            run_one=run_one,
            node_id="node-fail",
            events_path=tmp_path / "events.jsonl",
        )

        assert len(result.failed) == 2
        assert len(result.completed) == 0
