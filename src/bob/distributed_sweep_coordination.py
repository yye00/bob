"""Distributed sweep coordination via Redis-backed work queue.

Extends the sweep orchestrator to distribute runs across a compute cluster
(initially multiple machines sharing an NFS-mounted workspace). The coordinator
pushes SweepRun items onto a Redis list; worker nodes pop items, execute them,
and write per-node progress events to a shared JSONL file on NFS.

Usage pattern (coordinator + worker on same node, or split across nodes):

    redis_client = redis.Redis(host="redis-host")
    plan = load_sweep_plan("sweep_plan.yaml")

    result = distribute_sweep(
        plan=plan,
        redis_client=redis_client,
        run_one=my_run_function,
        node_id=socket.gethostname(),
        events_path=Path("/nfs/shared/sweep_events.jsonl"),
    )
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from bob.sweep_orchestrator import SweepPlan, SweepResult, SweepRun


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class WorkItem(BaseModel):
    """A single unit of work pushed onto the Redis queue."""

    run: SweepRun

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "WorkItem":
        return cls.model_validate_json(data.decode("utf-8"))


class NodeProgressEvent(BaseModel):
    """A progress event emitted by a worker node."""

    node_id: str
    run_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default="")

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "NodeProgressEvent":
        return cls.model_validate_json(raw)


# ---------------------------------------------------------------------------
# Redis work queue
# ---------------------------------------------------------------------------


class RedisWorkQueue:
    """Reliable Redis-backed work queue using the reliable-queue pattern.

    Items move from a pending list to a processing list on dequeue, and are
    removed from the processing list on ack (success) or returned to the
    pending list on nack (failure/retry).
    """

    def __init__(self, client: Any, queue_name: str = "bob_sweep") -> None:
        self._client = client
        self._pending_key = f"{queue_name}:pending"
        self._processing_key = f"{queue_name}:processing"

    def enqueue(self, item: WorkItem) -> None:
        """Push a work item onto the pending list."""
        self._client.lpush(self._pending_key, item.to_bytes())

    def dequeue(self, timeout_s: int = 5) -> WorkItem | None:
        """Pop an item from pending, atomically moving it to processing.

        Returns None if no item is available within timeout_s seconds.
        """
        raw = self._client.rpoplpush(self._pending_key, self._processing_key)
        if raw is None:
            return None
        return WorkItem.from_bytes(raw)

    def ack(self, item: WorkItem) -> None:
        """Remove a successfully processed item from the processing list."""
        self._client.lrem(self._processing_key, 1, item.to_bytes())

    def nack(self, item: WorkItem) -> None:
        """Return a failed item from processing back to the pending queue."""
        self._client.lrem(self._processing_key, 1, item.to_bytes())
        self._client.lpush(self._pending_key, item.to_bytes())

    def pending_count(self) -> int:
        return self._client.llen(self._pending_key)

    def processing_count(self) -> int:
        return self._client.llen(self._processing_key)


# ---------------------------------------------------------------------------
# Event writer
# ---------------------------------------------------------------------------


class _EventWriter:
    """Thread-safe append writer for per-node progress events."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: NodeProgressEvent) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_json() + "\n")


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


RunOneCallback = Callable[[SweepRun], float]


class DistributedSweepCoordinator:
    """Orchestrates distributed sweep execution over Redis.

    The coordinator pushes work onto the queue; workers call ``run_as_worker``
    to consume and execute items. Both can run on the same machine or different
    machines sharing an NFS workspace.
    """

    def __init__(
        self,
        redis_client: Any,
        events_path: Path,
        queue_name: str = "bob_sweep",
    ) -> None:
        self.queue = RedisWorkQueue(client=redis_client, queue_name=queue_name)
        self._writer = _EventWriter(events_path)
        self._events_path = events_path

    def distribute_plan(self, plan: SweepPlan) -> None:
        """Push all runs from a SweepPlan onto the Redis work queue."""
        for run in plan.runs:
            self.queue.enqueue(WorkItem(run=run))

    def run_as_worker(
        self,
        node_id: str,
        run_one: RunOneCallback,
        stop_when_queue_empty: bool = True,
    ) -> None:
        """Consume and execute work items from the queue.

        Emits ``run_started``, ``run_completed``, and ``run_failed`` events to
        the shared NFS events file.

        Args:
            node_id: Unique identifier for this compute node.
            run_one: Synchronous callable that executes a SweepRun and returns
                the USD cost incurred.
            stop_when_queue_empty: When True (default), returns once the queue
                is drained. When False, polls indefinitely (long-running worker).
        """
        while True:
            item = self.queue.dequeue(timeout_s=0)
            if item is None:
                if stop_when_queue_empty:
                    break
                continue

            run = item.run

            self._writer.write(
                NodeProgressEvent(
                    node_id=node_id,
                    run_id=run.run_id,
                    event_type="run_started",
                    payload={"variant": run.variant, "spec": run.spec, "seed": run.seed},
                )
            )

            try:
                cost = run_one(run)
            except Exception as exc:
                self.queue.ack(item)  # don't leave it in processing
                self._writer.write(
                    NodeProgressEvent(
                        node_id=node_id,
                        run_id=run.run_id,
                        event_type="run_failed",
                        payload={"error": str(exc)},
                    )
                )
                continue

            self.queue.ack(item)
            self._writer.write(
                NodeProgressEvent(
                    node_id=node_id,
                    run_id=run.run_id,
                    event_type="run_completed",
                    payload={"cost_usd": cost},
                )
            )

    def collect_results(self, timeout_s: float = 30.0) -> SweepResult:
        """Read the shared events file and aggregate into a SweepResult.

        Parses the JSONL events written by all workers and returns a
        SweepResult with completed, failed run IDs and total cost.
        """
        if not self._events_path.exists():
            return SweepResult(completed=[], failed=[], skipped=[])

        completed: list[str] = []
        failed: list[str] = []
        total_cost: float = 0.0
        seen_completed: set[str] = set()
        seen_failed: set[str] = set()

        for line in self._events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                evt = NodeProgressEvent.from_json(line)
            except Exception:
                continue

            if evt.event_type == "run_completed":
                if evt.run_id not in seen_completed:
                    seen_completed.add(evt.run_id)
                    completed.append(evt.run_id)
                    total_cost += evt.payload.get("cost_usd", 0.0)
            elif evt.event_type == "run_failed":
                if evt.run_id not in seen_failed and evt.run_id not in seen_completed:
                    seen_failed.add(evt.run_id)
                    failed.append(evt.run_id)

        return SweepResult(
            completed=completed,
            failed=failed,
            skipped=[],
            total_cost_usd=total_cost,
        )


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


def distribute_sweep(
    plan: SweepPlan,
    redis_client: Any,
    run_one: RunOneCallback,
    node_id: str,
    events_path: Path,
    queue_name: str = "bob_sweep",
) -> SweepResult:
    """Distribute and execute a sweep plan on a single node end-to-end.

    Pushes all runs onto the Redis queue, executes them as a worker, and
    returns the aggregated SweepResult.  For multi-node deployments call
    ``DistributedSweepCoordinator.distribute_plan`` once and
    ``run_as_worker`` on each node separately.

    Args:
        plan: SweepPlan describing the runs to execute.
        redis_client: Connected Redis client instance.
        run_one: Synchronous callable that executes a SweepRun and returns
            the USD cost incurred.
        node_id: Unique identifier for this compute node.
        events_path: Path to the shared NFS JSONL events file.
        queue_name: Redis key prefix for the work queue.

    Returns:
        SweepResult aggregated from the events file.
    """
    coord = DistributedSweepCoordinator(
        redis_client=redis_client,
        events_path=events_path,
        queue_name=queue_name,
    )
    coord.distribute_plan(plan)
    coord.run_as_worker(
        node_id=node_id,
        run_one=run_one,
        stop_when_queue_empty=True,
    )
    return coord.collect_results()
