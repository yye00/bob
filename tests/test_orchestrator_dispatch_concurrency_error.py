"""Error-path tests for orchestrator dispatch concurrency.

AC: pytest: tests/test_orchestrator_dispatch_concurrency_error.py — invalid
    input raises ValueError and the function does not silently succeed
    (error path).
"""

from __future__ import annotations

import pytest

from bob.orchestrator.run_loop import dispatch_concurrent_features


# ---------------------------------------------------------------------------
# Error path: invalid inputs must raise ValueError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_none_loop_raises_value_error():
    """Passing loop=None raises ValueError immediately without silently succeeding."""
    async def noop(f):
        return "ok"

    with pytest.raises(ValueError, match="loop"):
        await dispatch_concurrent_features(None, worker=noop)


@pytest.mark.asyncio
async def test_dispatch_non_callable_worker_raises_value_error():
    """Passing a non-callable worker raises ValueError immediately."""
    import unittest.mock as mock

    loop = mock.MagicMock()
    loop.max_concurrent_features = 3

    with pytest.raises(ValueError, match="worker"):
        await dispatch_concurrent_features(loop, worker="not_a_function")


@pytest.mark.asyncio
async def test_dispatch_none_worker_raises_value_error():
    """Passing worker=None raises ValueError immediately."""
    import unittest.mock as mock

    loop = mock.MagicMock()
    loop.max_concurrent_features = 3

    with pytest.raises(ValueError, match="worker"):
        await dispatch_concurrent_features(loop, worker=None)


@pytest.mark.asyncio
async def test_dispatch_integer_worker_raises_value_error():
    """Passing an integer as worker raises ValueError."""
    import unittest.mock as mock

    loop = mock.MagicMock()
    loop.max_concurrent_features = 3

    with pytest.raises(ValueError):
        await dispatch_concurrent_features(loop, worker=42)


@pytest.mark.asyncio
async def test_dispatch_both_none_raises_value_error():
    """Passing both loop=None and worker=None raises ValueError."""
    with pytest.raises(ValueError):
        await dispatch_concurrent_features(None, worker=None)
