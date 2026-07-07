"""Tests for bob.turn_limit_completability (182cf79c / 25082b08).

Turn-limit exhaustion is a completability signal, not a transport-transient.
The transport-transient predicate must match ONLY genuine transport signatures
and MUST NOT match a bare nonzero exit code or "message reader" alone.
"""
from __future__ import annotations

import pytest

from bob import turn_limit_completability as tlc


# ---------------------------------------------------------------------------
# is_turn_limit_result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sig",
    [
        "max_turns reached",
        "max-turns exceeded",
        "the turn limit was hit",
        "num_turns exceeded budget",
        "turn budget exhausted",
        "error_max_turns",
        "Reached the maximum number of turns",
        "MAX_TURNS",
    ],
)
def test_turn_limit_markers_detected(sig):
    assert tlc.is_turn_limit_result(sig) is True


@pytest.mark.parametrize(
    "sig",
    [
        "Command failed with exit code 1",
        "exit code 1",
        "message reader",
        "ECONNRESET",
        "connection reset by peer",
        "",
    ],
)
def test_non_turn_limit_signatures_not_detected(sig):
    assert tlc.is_turn_limit_result(sig) is False


def test_turn_limit_from_dict_payload():
    assert tlc.is_turn_limit_result({"subtype": "error_max_turns"}) is True


# ---------------------------------------------------------------------------
# is_transport_transient
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sig",
    [
        "ECONNRESET",
        "ConnectionResetError: connection reset by peer",
        "self-signed certificate in chain",
        "certificate verify failed",
        "ReadTimeout: read timed out",
        "connection timed out",
        "broken pipe",
        "socket hang up",
        "mcp server connection failed",
    ],
)
def test_genuine_transport_signatures_matched(sig):
    assert tlc.is_transport_transient(sig) is True


@pytest.mark.parametrize(
    "sig",
    [
        "Command failed with exit code 1",
        "exit code 1",
        "message reader",
        "max_turns reached",
        "turn limit hit",
        "some unknown failure",
        "",
    ],
)
def test_bare_exit_and_turn_limit_not_transport(sig):
    # The historical bug: bare "exit code 1" / "message reader" and turn-limit
    # markers were mis-classified as transport-transient free retries.
    assert tlc.is_transport_transient(sig) is False


# ---------------------------------------------------------------------------
# classify_result / classify_turn_limit_result
# ---------------------------------------------------------------------------


def test_turn_limit_routes_to_completability():
    outcome = tlc.classify_result("max_turns reached")
    assert outcome.is_turn_limit is True
    assert outcome.transport_transient is False
    assert outcome.attempt_consuming is True
    assert outcome.decomposition_eligible is True


def test_transport_transient_grants_free_retry():
    outcome = tlc.classify_result("ECONNRESET")
    assert outcome.transport_transient is True
    assert outcome.is_turn_limit is False
    assert outcome.attempt_consuming is False
    assert outcome.decomposition_eligible is False


def test_bare_exit_code_is_attempt_consuming_not_free_retry():
    outcome = tlc.classify_result("Command failed with exit code 1")
    assert outcome.is_turn_limit is False
    assert outcome.transport_transient is False
    # The core fix: bare exit code charges the attempt, never a free retry.
    assert outcome.attempt_consuming is True
    assert outcome.decomposition_eligible is False


def test_turn_limit_precedence_over_transport():
    # If both markers appear, turn-limit must win (never a free retry).
    outcome = tlc.classify_result("max_turns reached; ECONNRESET")
    assert outcome.is_turn_limit is True
    assert outcome.transport_transient is False
    assert outcome.decomposition_eligible is True


def test_classify_turn_limit_result_alias_matches():
    a = tlc.classify_turn_limit_result("max_turns reached")
    b = tlc.classify_result("max_turns reached")
    assert a == b


def test_predicates_mutually_exclusive_for_turn_limit():
    sig = "error_max_turns"
    assert tlc.is_turn_limit_result(sig) is True
    assert tlc.is_transport_transient(sig) is False


def test_integration_startup_crash_exempt_excludes_bare_exit():
    # F-R6-300 classifier must not treat bare exit-1 as transport-transient.
    from bob import startup_crash_exempt as sce

    assert sce.exit_signature_matches_transport_transient(
        "Command failed with exit code 1"
    ) is False
    assert sce.exit_signature_matches_transport_transient("ECONNRESET") is True


# ---------------------------------------------------------------------------
# error path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [123, 3.14, [1, 2], (1,)])
def test_invalid_types_raise(bad):
    with pytest.raises(ValueError):
        tlc.classify_result(bad)
