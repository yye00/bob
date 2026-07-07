"""Tests for the in-process SDK transport-transient retry wrapper (4def8bdc)."""

from __future__ import annotations

import asyncio

import pytest

from bob.sdk_transport_retry import (
    DEFAULT_MAX_RETRIES,
    is_transport_transient,
    query_with_transport_retry,
)


# --------------------------------------------------------------------------
# is_transport_transient
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sig",
    [
        "Fatal error in message reader: connection reset by peer",
        "ECONNRESET during MCP request",
        "broken pipe writing to transport",
        "self-signed certificate in certificate chain",
        "read timeout after 30s",
        "socket hang up",
        "streamable http error posting to endpoint",
        "network is unreachable",
        "transport closed unexpectedly",
    ],
)
def test_transport_signatures_are_transient(sig):
    assert is_transport_transient(sig) is True


@pytest.mark.parametrize(
    "sig",
    [
        "Command failed with exit code 1",  # bare exit-1: max_turns / real error
        "message reader",  # not a network marker on its own
        "AssertionError: expected 3 got 4",
        "ValueError: bad input",
        "verification failed: 2 acs unmet",
        "",  # empty -> not transient
        "   ",  # whitespace -> not transient
    ],
)
def test_non_transport_signatures_are_not_transient(sig):
    assert is_transport_transient(sig) is False


def test_none_is_not_transient():
    assert is_transport_transient(None) is False


def test_case_insensitive():
    assert is_transport_transient("CONNECTION RESET BY PEER") is True


# --------------------------------------------------------------------------
# query_with_transport_retry: success / retry / resume semantics
# --------------------------------------------------------------------------


async def _collect(factory, **kw):
    out = []
    async for m in query_with_transport_retry(factory, **kw):
        out.append(m)
    return out


def test_clean_stream_yields_all_messages():
    async def factory():
        for m in ["a", "b", "c"]:
            yield m

    result = asyncio.run(_collect(factory))
    assert result == ["a", "b", "c"]


def test_transport_crash_is_retried_in_process_and_completes():
    """A build that crashes twice with transport errors still finishes."""
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        yield f"chunk-{calls['n']}"
        if calls["n"] < 3:
            raise RuntimeError("connection reset by peer")
        # third attempt completes cleanly

    result = asyncio.run(
        _collect(factory, sleep=_noop_sleep, backoff_base=0.0)
    )
    # Each attempt re-issues the request (workspace WIP carries progress),
    # so we see one chunk per attempt and the run completes.
    assert result == ["chunk-1", "chunk-2", "chunk-3"]
    assert calls["n"] == 3


def test_non_transport_error_is_not_retried():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        yield "partial"
        raise ValueError("real implementation bug")

    with pytest.raises(ValueError, match="real implementation bug"):
        asyncio.run(_collect(factory, sleep=_noop_sleep))
    assert calls["n"] == 1  # not retried


def test_retries_exhausted_bubbles_up():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        yield "x"
        raise RuntimeError("ECONNRESET")

    with pytest.raises(RuntimeError, match="ECONNRESET"):
        asyncio.run(
            _collect(factory, max_retries=2, sleep=_noop_sleep, backoff_base=0.0)
        )
    # initial + 2 retries = 3 attempts
    assert calls["n"] == 3


def test_crash_count_logged_does_not_reset_agent(caplog):
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        yield "y"
        if calls["n"] < 2:
            raise RuntimeError("broken pipe")

    import logging

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(_collect(factory, sleep=_noop_sleep, backoff_base=0.0))
    assert result == ["y", "y"]
    assert any("transport-transient" in r.message for r in caplog.records)


def test_cancelled_error_is_not_retried():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        raise asyncio.CancelledError()
        yield  # pragma: no cover

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_collect(factory, sleep=_noop_sleep))
    assert calls["n"] == 1


def test_backoff_delays_grow_and_cap():
    delays: list[float] = []

    async def _record_sleep(d):
        delays.append(d)

    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        yield "z"
        raise RuntimeError("connection reset")

    with pytest.raises(RuntimeError):
        asyncio.run(
            _collect(
                factory,
                max_retries=5,
                sleep=_record_sleep,
                backoff_base=2.0,
                backoff_cap=15.0,
            )
        )
    assert delays == [2.0, 4.0, 8.0, 15.0, 15.0]


def test_default_max_retries_is_positive():
    assert isinstance(DEFAULT_MAX_RETRIES, int)
    assert DEFAULT_MAX_RETRIES > 0


async def _noop_sleep(_d):
    return None
