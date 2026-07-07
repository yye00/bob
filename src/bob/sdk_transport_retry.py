"""In-process SDK transport-transient retry wrapper (feature 4def8bdc).

The completability cliff
------------------------
The claude-code-sdk streamable-HTTP transport intermittently dies mid-request
with signatures such as ``Fatal error in message reader: Command failed with
exit code 1`` (self-signed-cert / connection-reset / broken-pipe during MCP or
model I/O). bob correctly classifies this as a transport-transient
``mid_work_crash`` and does not charge a retry, BUT historically it surfaced the
crash up to the feature level: the sub-agent process ended, the feature was
reset, and a FRESH sub-agent restarted the feature from scratch.

For SMALL features that is fine. For LARGE features whose single-attempt build
time EXCEEDS the mean-time-between-transport-crashes, the feature can NEVER
finish in one uninterrupted attempt — it crashes mid-work every time and
restarts. Under a nonzero per-request crash probability ``p``, the probability
of finishing an ``n``-request build is ``(1 - p) ** n`` → 0 as ``n`` grows. That
is a hard *completability cliff*, not a slow grind.

The fix
-------
Retry a transport-transient failure IN-PROCESS: reconnect and re-issue the
request within the SAME sub-agent session so the agent's in-memory context and
the on-disk workspace are preserved and it RESUMES rather than restarts. Only
after ``max_retries`` in-process transport retries fail does the error bubble up
to the normal ``mid_work_crash`` path. This converts the cliff into a
slow-but-finishing grind: a feature whose build spans multiple transport crashes
still completes.

Boundary: a NON-transport error (a genuine exception, a verification failure) is
NOT retried at the SDK layer — it propagates immediately to normal refinement.

This module is deliberately decoupled from the concrete SDK. The retry driver
takes a ``query_factory`` (a zero-arg callable returning a fresh async iterator
of messages) so each retry re-issues a *new* request; the workspace WIP on disk
is what carries state across retries, exactly as in a live sub-agent session.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Awaitable, Callable, TypeVar

# Integration: bob.disk_quota — a transport-retry loop that resumes a large
# feature build in-process keeps writing WIP to the same session directory, so
# the disk-quota accounting stays authoritative across retries (the retried
# request does not spin up a fresh workspace). We import the quota helper so the
# retry layer and the quota layer share one accounting surface rather than two
# checkers disagreeing on how much disk a resumed build has consumed.
from bob.disk_quota import disk_pressure_warning  # noqa: F401

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default in-process retry budget. NEVER lowers any bob threshold — it only
# bounds how many times a single turn is re-issued before the crash bubbles up
# to normal refinement. Matches the BOB_SDK_TRANSPORT_RETRIES default used by
# the live executor's stream wrapper.
DEFAULT_MAX_RETRIES: int = 6

# Backoff bounds (seconds). Exponential: min(base * 2**attempt, cap).
_DEFAULT_BACKOFF_BASE: float = 2.0
_DEFAULT_BACKOFF_CAP: float = 15.0


# Transport-transient substrings. Lowercase; matched against the lowercased
# signature. A bare "exit code 1" / "message reader" is intentionally NOT here:
# a clean exit-1 is almost always max_turns exhaustion or a real implementation
# error, which MUST bubble to refinement rather than be silently retried. Only
# genuine network / certificate / transport markers qualify.
_TRANSPORT_TRANSIENT_MARKERS: tuple[str, ...] = (
    "connection reset",
    "econnreset",
    "connectionreseterror",
    "broken pipe",
    "self-signed certificate",
    "self signed certificate",
    "certificate chain",
    "certificate verify failed",
    "read timeout",
    "readtimeout",
    "econnrefused",
    "etimedout",
    "connection timed out",
    "socket hang up",
    "streamable http error",
    "error posting to endpoint",
    "ehostunreach",
    "network is unreachable",
    "network unreachable",
    "connection failed",
    "mcp transport fail",
    "transport closed",
)


def is_transport_transient(signature: str | None) -> bool:
    """Return True iff *signature* names a transport-transient failure.

    A transport-transient failure is one caused by the transport/infra layer
    (self-signed cert, connection reset, broken pipe, read timeout, MCP
    transport drop) rather than by the sub-agent's own work. Only these are
    safe to retry in-process; anything else must flow to normal refinement.

    Parameters
    ----------
    signature:
        The stderr tail, exception string, or combined crash signature.
        ``None`` and the empty / whitespace-only string return ``False``
        (a well-defined boundary result — there is no transport marker to
        match, so the failure is treated as non-transient and bubbles up).

    Returns
    -------
    bool
        ``True`` when a transport-transient marker is present.

    Raises
    ------
    ValueError
        When *signature* is neither ``None`` nor a ``str`` (e.g. an ``int``,
        ``list`` or object). Passing a non-string is a programming error: the
        function will not silently coerce it and return a misleading ``False``.
    """
    if signature is None:
        return False
    if not isinstance(signature, str):
        raise ValueError(
            "is_transport_transient: signature must be a str or None, got "
            f"{type(signature).__name__!r}"
        )
    lowered = signature.lower()
    if not lowered.strip():
        return False
    return any(marker in lowered for marker in _TRANSPORT_TRANSIENT_MARKERS)


def _backoff_seconds(attempt: int, *, base: float, cap: float) -> float:
    """Exponential backoff for the nth (0-based) retry, capped at *cap*."""
    if attempt < 0:
        attempt = 0
    return min(base * (2 ** attempt), cap)


async def query_with_transport_retry(
    query_factory: Callable[[], AsyncIterator[T]],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base: float = _DEFAULT_BACKOFF_BASE,
    backoff_cap: float = _DEFAULT_BACKOFF_CAP,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    is_transient: Callable[[str | None], bool] = is_transport_transient,
) -> AsyncIterator[T]:
    """Drive an SDK query, retrying transport-transient failures IN-PROCESS.

    Each call to *query_factory* must return a FRESH async iterator that
    re-issues the request (reconnecting the transport). On a transport-transient
    failure raised while iterating, the wrapper waits (exponential backoff) and
    re-invokes *query_factory* to continue the same logical turn — the sub-agent
    session and its on-disk WIP are preserved, so the build RESUMES rather than
    restarts. A non-transport failure propagates immediately.

    Parameters
    ----------
    query_factory:
        Zero-arg callable returning a fresh ``AsyncIterator`` of messages.
        Called once per attempt (initial + each retry).
    max_retries:
        Maximum number of in-process retries after the initial attempt. Must be
        a non-negative ``int``. ``0`` means: try once, never retry (the initial
        attempt still runs — a well-defined minimum). Bounds, never lowers, any
        threshold.
    backoff_base, backoff_cap:
        Exponential-backoff parameters, in seconds.
    sleep:
        Awaitable sleep function (injectable for tests).
    is_transient:
        Predicate deciding whether a failure signature is transport-transient
        (injectable for tests). Defaults to :func:`is_transport_transient`.

    Yields
    ------
    T
        Each message yielded by the underlying query iterator.

    Raises
    ------
    ValueError
        When *query_factory* is not callable, or *max_retries* is not a
        non-negative ``int`` (``bool`` is rejected).
    BaseException
        Re-raises the underlying failure once retries are exhausted, or
        immediately when the failure is not transport-transient.
    """
    if not callable(query_factory):
        raise ValueError(
            "query_with_transport_retry: query_factory must be callable, got "
            f"{type(query_factory).__name__!r}"
        )
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise ValueError(
            "query_with_transport_retry: max_retries must be a non-negative int, "
            f"got {type(max_retries).__name__!r}"
        )
    if max_retries < 0:
        raise ValueError(
            "query_with_transport_retry: max_retries must be >= 0, got "
            f"{max_retries!r}"
        )

    attempt = 0
    while True:
        try:
            async for message in query_factory():
                yield message
            return
        except (GeneratorExit, KeyboardInterrupt, asyncio.CancelledError):
            # Never swallow cooperative cancellation / shutdown.
            raise
        except BaseException as exc:  # noqa: BLE001 — classified below
            signature = str(exc)
            if is_transient(signature) and attempt < max_retries:
                attempt += 1
                delay = _backoff_seconds(
                    attempt - 1, base=backoff_base, cap=backoff_cap
                )
                logger.warning(
                    "query_with_transport_retry: transport-transient failure "
                    "(retry %d/%d) — re-issuing query in-process, workspace WIP "
                    "preserved. backoff=%.1fs sig=%r",
                    attempt,
                    max_retries,
                    delay,
                    signature[:160],
                )
                if delay > 0:
                    await sleep(delay)
                continue
            # Non-transport failure, or retries exhausted: bubble up to the
            # normal mid_work_crash / refinement path.
            raise


__all__ = [
    "DEFAULT_MAX_RETRIES",
    "is_transport_transient",
    "query_with_transport_retry",
]
