"""Boundary tests (4def8bdc): empty / zero / minimum input returns a
well-defined result rather than raising."""

from __future__ import annotations

import asyncio

from bob.sdk_transport_retry import (
    is_transport_transient,
    query_with_transport_retry,
)


def test_none_signature_returns_false():
    assert is_transport_transient(None) is False


def test_empty_signature_returns_false():
    assert is_transport_transient("") is False


def test_whitespace_signature_returns_false():
    assert is_transport_transient("   \n\t ") is False


def test_max_retries_zero_runs_once_and_never_retries():
    """max_retries=0 is the minimum: the initial attempt still runs."""
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        yield "only"

    async def run():
        out = []
        async for m in query_with_transport_retry(
            factory, max_retries=0, sleep=_noop
        ):
            out.append(m)
        return out

    assert asyncio.run(run()) == ["only"]
    assert calls["n"] == 1


def test_empty_stream_yields_nothing():
    async def factory():
        return
        yield  # pragma: no cover

    async def run():
        out = []
        async for m in query_with_transport_retry(factory, sleep=_noop):
            out.append(m)
        return out

    assert asyncio.run(run()) == []


def test_max_retries_zero_with_transport_crash_bubbles_immediately():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        yield "x"
        raise RuntimeError("connection reset")

    async def run():
        async for _ in query_with_transport_retry(
            factory, max_retries=0, sleep=_noop
        ):
            pass

    # With no retry budget, a transport crash is not silently swallowed —
    # it bubbles up (well-defined) after the single attempt.
    try:
        asyncio.run(run())
        raised = False
    except RuntimeError:
        raised = True
    assert raised is True
    assert calls["n"] == 1


async def _noop(_d):
    return None
