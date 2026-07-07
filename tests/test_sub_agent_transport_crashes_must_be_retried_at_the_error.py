"""Error-path tests (4def8bdc): invalid input raises ValueError and the
function does not silently succeed."""

from __future__ import annotations

import asyncio

import pytest

from bob.sdk_transport_retry import (
    is_transport_transient,
    query_with_transport_retry,
)


@pytest.mark.parametrize("bad", [123, 1.5, ["x"], {"a": 1}, object(), True])
def test_is_transport_transient_rejects_non_string(bad):
    with pytest.raises(ValueError):
        is_transport_transient(bad)


def test_query_factory_must_be_callable():
    async def run():
        async for _ in query_with_transport_retry(object()):  # type: ignore[arg-type]
            pass

    with pytest.raises(ValueError, match="callable"):
        asyncio.run(run())


@pytest.mark.parametrize("bad", [-1, "3", 2.0, None, True, False])
def test_max_retries_must_be_non_negative_int(bad):
    async def factory():
        yield "x"

    async def run():
        async for _ in query_with_transport_retry(factory, max_retries=bad):
            pass

    with pytest.raises(ValueError):
        asyncio.run(run())


def test_error_path_does_not_silently_succeed():
    """A non-transport error must propagate, not be swallowed into success."""
    async def factory():
        yield "partial"
        raise KeyError("genuine bug")

    async def run():
        out = []
        async for m in query_with_transport_retry(factory, sleep=_noop):
            out.append(m)
        return out

    with pytest.raises(KeyError):
        asyncio.run(run())


async def _noop(_d):
    return None
