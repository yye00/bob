"""Tests for bob.turn_limit_completability (182cf79c).

Turn-limit exhaustion (max_turns reached, surfaced by the SDK as a bare
nonzero exit) must be classified as a completability signal — attempt-consuming
and decomposition-eligible — NOT as a free transport-transient retry.
"""
from __future__ import annotations

import pytest

from bob import turn_limit_completability as tlc


# ---------------------------------------------------------------------------
# is_turn_limit_result
# ---------------------------------------------------------------------------


class TestIsTurnLimitResult:
    def test_max_turns_marker_matches(self):
        assert tlc.is_turn_limit_result("max_turns reached") is True

    def test_turn_limit_phrase_matches(self):
        assert tlc.is_turn_limit_result("Agent hit the turn limit") is True

    def test_num_turns_exceeded_matches(self):
        assert tlc.is_turn_limit_result("num_turns exceeded budget") is True

    def test_bare_exit_code_1_is_not_a_positive_turn_limit_signature(self):
        # A bare exit code with no turn marker is NOT classifiable as
        # turn-limit purely from the string; it returns False here (the
        # caller supplies the result-type marker separately).
        assert tlc.is_turn_limit_result("Command failed with exit code 1") is False

    def test_transport_signature_is_not_turn_limit(self):
        assert tlc.is_turn_limit_result("ECONNRESET connection reset") is False

    def test_case_insensitive(self):
        assert tlc.is_turn_limit_result("MAX_TURNS REACHED") is True

    def test_result_type_field_marker(self):
        assert tlc.is_turn_limit_result("result subtype=error_max_turns") is True

    def test_dict_with_turn_limit_marker(self):
        assert tlc.is_turn_limit_result({"subtype": "error_max_turns"}) is True

    def test_dict_without_turn_limit_marker(self):
        assert tlc.is_turn_limit_result({"subtype": "success"}) is False


# ---------------------------------------------------------------------------
# is_transport_transient
# ---------------------------------------------------------------------------


class TestIsTransportTransient:
    def test_econnreset_matches(self):
        assert tlc.is_transport_transient("ECONNRESET") is True

    def test_connection_reset_matches(self):
        assert tlc.is_transport_transient("connection reset by peer") is True

    def test_self_signed_cert_matches(self):
        assert tlc.is_transport_transient("self-signed certificate in chain") is True

    def test_read_timeout_matches(self):
        assert tlc.is_transport_transient("ReadTimeout waiting for response") is True

    def test_broken_pipe_matches(self):
        assert tlc.is_transport_transient("broken pipe") is True

    def test_mcp_connection_failed_matches(self):
        assert tlc.is_transport_transient("MCP connection failed") is True

    def test_bare_exit_code_1_does_NOT_match(self):
        # This is the core regression: bare exit-1 must NOT be transport.
        assert tlc.is_transport_transient("Command failed with exit code 1") is False

    def test_message_reader_alone_does_NOT_match(self):
        assert tlc.is_transport_transient("message reader") is False

    def test_turn_limit_signature_does_NOT_match_transport(self):
        assert tlc.is_transport_transient("max_turns reached") is False

    def test_case_insensitive(self):
        assert tlc.is_transport_transient("econnreset") is True


# ---------------------------------------------------------------------------
# Mutual exclusivity — the whole point of the feature
# ---------------------------------------------------------------------------


class TestMutualExclusivity:
    def test_turn_limit_is_not_transport(self):
        sig = "Command failed with exit code 1 — max_turns reached"
        assert tlc.is_turn_limit_result(sig) is True
        assert tlc.is_transport_transient(sig) is False

    def test_transport_is_not_turn_limit(self):
        sig = "Command failed with exit code 1 — ECONNRESET"
        assert tlc.is_transport_transient(sig) is True
        assert tlc.is_turn_limit_result(sig) is False


# ---------------------------------------------------------------------------
# classify_result — the completability routing decision
# ---------------------------------------------------------------------------


class TestClassifyResult:
    def test_turn_limit_is_attempt_consuming(self):
        outcome = tlc.classify_result("max_turns reached")
        assert outcome.is_turn_limit is True
        assert outcome.attempt_consuming is True
        assert outcome.decomposition_eligible is True
        assert outcome.transport_transient is False

    def test_transport_is_free_retry(self):
        outcome = tlc.classify_result("ECONNRESET")
        assert outcome.transport_transient is True
        assert outcome.attempt_consuming is False
        assert outcome.decomposition_eligible is False

    def test_bare_exit_1_is_attempt_consuming_not_transport(self):
        outcome = tlc.classify_result("Command failed with exit code 1")
        assert outcome.transport_transient is False
        assert outcome.attempt_consuming is True
