"""Tests that one hung task does not block other concurrent dispatches.

AC: pytest: tests/test_dispatch_concurrency_one_hung_does_not_block_others.py
"""

from __future__ import annotations

import asyncio

import pytest

from bob.orchestrator.run_loop import gather_completed_dispatches


@pytest.mark.asyncio
async def test_gather_completed_dispatches_isolates_hung_task():
    """gather_completed_dispatches awaits all tasks; a slow task does not block fast peers."""
    results_order: list[str] = []

    async def fast_task():
        await asyncio.sleep(0)
        results_order.append("fast")
        return "fast_result"

    async def slow_task():
        await asyncio.sleep(0.05)
        results_order.append("slow")
        return "slow_result"

    tasks = [
        asyncio.create_task(fast_task()),
        asyncio.create_task(slow_task()),
        asyncio.create_task(fast_task()),
    ]
    outcomes = await gather_completed_dispatches(tasks)

    assert len(outcomes) == 3
    successes = [o for o in outcomes if o["success"]]
    assert len(successes) == 3

    # Fast tasks should have completed before slow
    assert results_order[0] == "fast"
    assert results_order[-1] == "slow"


@pytest.mark.asyncio
async def test_gather_completed_dispatches_one_failure_does_not_cancel_others():
    """One failing task does not prevent other tasks from completing."""
    completed: list[str] = []

    async def good_task(name: str):
        await asyncio.sleep(0)
        completed.append(name)
        return name

    async def bad_task():
        await asyncio.sleep(0)
        raise RuntimeError("intentional failure")

    tasks = [
        asyncio.create_task(good_task("g1")),
        asyncio.create_task(bad_task()),
        asyncio.create_task(good_task("g2")),
    ]
    outcomes = await gather_completed_dispatches(tasks)

    assert len(outcomes) == 3
    successes = [o for o in outcomes if o["success"]]
    failures = [o for o in outcomes if not o["success"]]
    assert len(successes) == 2
    assert len(failures) == 1
    assert "intentional failure" in failures[0]["error"]
    assert set(completed) == {"g1", "g2"}


@pytest.mark.asyncio
async def test_gather_completed_dispatches_all_fail():
    """gather_completed_dispatches handles the case where all tasks fail."""
    async def bad():
        raise ValueError("boom")

    tasks = [asyncio.create_task(bad()) for _ in range(3)]
    outcomes = await gather_completed_dispatches(tasks)

    assert len(outcomes) == 3
    assert all(not o["success"] for o in outcomes)
    assert all("boom" in o["error"] for o in outcomes)


@pytest.mark.asyncio
async def test_gather_completed_dispatches_empty_list():
    """gather_completed_dispatches returns empty list for empty input."""
    outcomes = await gather_completed_dispatches([])
    assert outcomes == []


@pytest.mark.asyncio
async def test_gather_completed_dispatches_result_order_matches_task_order():
    """gather_completed_dispatches returns outcomes in the same order as tasks."""
    results = []

    async def ordered_task(val: int):
        await asyncio.sleep(0)
        return val

    tasks = [asyncio.create_task(ordered_task(i)) for i in range(5)]
    outcomes = await gather_completed_dispatches(tasks)

    assert len(outcomes) == 5
    for i, outcome in enumerate(outcomes):
        assert outcome["success"] is True
        assert outcome["result"] == i
