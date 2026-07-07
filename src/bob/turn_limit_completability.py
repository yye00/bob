"""Turn-limit exhaustion is a completability signal, not a transport-transient (182cf79c).

Context
-------
A prior generation lost days to this: when a sub-agent hits its ``max_turns``
budget, the SDK returns a turn-limit result that surfaces as a nonzero exit
("Command failed with exit code 1"). The transport-transient classifier
(F-R6-300 / :mod:`bob.startup_crash_exempt`) matched the bare "exit code 1" /
"message reader" substring and mis-classified turn-limit exhaustion as a free
transport retry, so an oversized feature silently retried its full turn budget
forever and never converged (observed: a feature spun ~3.5h emitting exactly N
dispatches then a graceful exit-1 each attempt).

Policy this module enforces
---------------------------
* The transport-transient predicate matches ONLY genuine transport signatures
  (ECONNRESET, connection reset, self-signed certificate, ReadTimeout, broken
  pipe, MCP connection failed). It MUST NOT match a bare nonzero exit code or
  "message reader" alone.
* A turn-limit result (``max_turns`` reached / turn ceiling hit) is
  attempt-consuming and decomposition-eligible — it routes to the completability
  path (F-R7 stuck decomposer), never to an infinite free retry.

The two predicates are mutually exclusive by construction: a turn-limit marker
never matches the transport patterns, and a transport marker never matches the
turn-limit patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "TurnLimitOutcome",
    "is_turn_limit_result",
    "is_transport_transient",
    "classify_result",
]


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Turn-limit / max_turns-reached signatures. These identify a sub-agent that
# exhausted its turn budget — a completability signal.
_TURN_LIMIT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in [
        r"max[_\s-]?turns",
        r"turn[_\s-]?limit",
        r"num[_\s-]?turns\s+exceeded",
        r"turn\s+budget\s+(?:exhausted|exceeded)",
        r"error_max_turns",
        r"reached\s+(?:the\s+)?maximum\s+(?:number\s+of\s+)?turns",
    ]
)

# Genuine transport-transient signatures ONLY. Deliberately excludes bare
# "exit code 1" and bare "message reader" — those are the substrings that
# caused the historical misclassification.
_TRANSPORT_TRANSIENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ECONNRESET",
        r"ConnectionResetError",
        r"connection reset",
        r"self[\s-]?signed certificate",
        r"certificate verify failed",
        r"certificate chain",
        r"ReadTimeout",
        r"read timed out",
        r"connection timed out",
        r"ETIMEDOUT",
        r"ECONNREFUSED",
        r"broken pipe",
        r"socket hang up",
        r"EHOSTUNREACH",
        r"mcp.*connection.*fail",
        r"mcp.*server.*connection",
        r"mcp.*transport.*fail",
        r"streamable http error",
        r"error posting to endpoint",
    ]
)


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnLimitOutcome:
    """Result of :func:`classify_result`.

    Attributes
    ----------
    is_turn_limit:
        The signature carries a turn-limit / max_turns-reached marker.
    transport_transient:
        The signature matches a genuine transport-transient pattern.
    attempt_consuming:
        The result must charge a retry attempt. True for turn-limit and for
        unclassified results; False only for genuine transport-transients
        (which get a free retry).
    decomposition_eligible:
        The result should route to the F-R7 stuck decomposer. True only for
        turn-limit exhaustion.
    evidence:
        Human-readable explanation of the decision.
    """

    is_turn_limit: bool
    transport_transient: bool
    attempt_consuming: bool
    decomposition_eligible: bool
    evidence: str


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _coerce_to_text(result: object, *, param: str) -> str:
    """Return a searchable string for ``result``.

    Accepts:
      * ``None`` → empty string.
      * ``str`` → itself.
      * ``dict`` → its keys and values joined (so a ``{"subtype": ...}``
        result payload can be matched).

    Raises
    ------
    ValueError
        For any other type (int, float, list, etc.).
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        parts: list[str] = []
        for key, value in result.items():
            parts.append(str(key))
            parts.append(str(value))
        return " ".join(parts)
    raise ValueError(
        f"{param} must be a str, dict, or None, got {type(result).__name__!r}"
    )


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def is_turn_limit_result(result: object) -> bool:
    """Return True iff ``result`` carries a turn-limit / max_turns marker.

    A turn-limit result is a completability signal: the sub-agent exhausted its
    turn budget. It is attempt-consuming and decomposition-eligible, NOT a free
    transport retry.

    Parameters
    ----------
    result:
        A crash signature / stderr tail (``str``), a result payload (``dict``
        whose keys/values are searched), or ``None``.

    Returns
    -------
    bool
        ``True`` when a turn-limit marker is present, ``False`` otherwise
        (including for empty / ``None`` input).

    Raises
    ------
    ValueError
        When ``result`` is not a ``str``, ``dict``, or ``None``.
    """
    text = _coerce_to_text(result, param="result")
    if not text.strip():
        return False
    return any(p.search(text) for p in _TURN_LIMIT_PATTERNS)


def is_transport_transient(signature: object) -> bool:
    """Return True iff ``signature`` matches a genuine transport-transient pattern.

    Matches ONLY real transport signatures (connection reset, self-signed
    certificate, read timeout, broken pipe, MCP connection failure). Explicitly
    does NOT match a bare nonzero exit code ("exit code 1") or "message reader"
    alone — that was the historical misclassification that turned turn-limit
    exhaustion into an infinite free retry.

    Parameters
    ----------
    signature:
        A crash signature / stderr tail (``str``), a result payload (``dict``),
        or ``None``.

    Returns
    -------
    bool
        ``True`` when a transport-transient pattern matches, ``False``
        otherwise (including for empty / ``None`` input).

    Raises
    ------
    ValueError
        When ``signature`` is not a ``str``, ``dict``, or ``None``.
    """
    text = _coerce_to_text(signature, param="signature")
    if not text.strip():
        return False
    return any(p.search(text) for p in _TRANSPORT_TRANSIENT_PATTERNS)


def classify_result(result: object) -> TurnLimitOutcome:
    """Classify a sub-agent result into a completability routing decision.

    Precedence: a turn-limit marker wins over everything (a turn-limit result
    is never treated as a free transport retry). Then transport-transient. An
    unclassified result (bare exit code, unknown error) is attempt-consuming
    but not decomposition-eligible.

    Parameters
    ----------
    result:
        A crash signature / stderr tail (``str``), a result payload (``dict``),
        or ``None``.

    Returns
    -------
    TurnLimitOutcome
        Structured decision.

    Raises
    ------
    ValueError
        When ``result`` is not a ``str``, ``dict``, or ``None``.
    """
    turn_limit = is_turn_limit_result(result)

    if turn_limit:
        return TurnLimitOutcome(
            is_turn_limit=True,
            transport_transient=False,
            attempt_consuming=True,
            decomposition_eligible=True,
            evidence=(
                "turn_limit_exhaustion: max_turns marker present; "
                "attempt-consuming and decomposition-eligible (route to F-R7 "
                "stuck decomposer), NOT a transport-transient free retry"
            ),
        )

    if is_transport_transient(result):
        return TurnLimitOutcome(
            is_turn_limit=False,
            transport_transient=True,
            attempt_consuming=False,
            decomposition_eligible=False,
            evidence=(
                "transport_transient: genuine transport signature matched; "
                "free retry granted"
            ),
        )

    return TurnLimitOutcome(
        is_turn_limit=False,
        transport_transient=False,
        attempt_consuming=True,
        decomposition_eligible=False,
        evidence=(
            "unclassified: no turn-limit marker and no transport signature "
            "(e.g. bare exit code); charge the attempt, do not grant a free retry"
        ),
    )
