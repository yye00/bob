"""Boundary tests for bob.turn_limit_completability (182cf79c).

Empty, zero, or minimum input must return a well-defined result rather than raising.
"""
from __future__ import annotations

from bob import turn_limit_completability as tlc


def test_empty_string_is_turn_limit_returns_false():
    assert tlc.is_turn_limit_result("") is False


def test_empty_string_is_transport_returns_false():
    assert tlc.is_transport_transient("") is False


def test_none_is_turn_limit_returns_false():
    assert tlc.is_turn_limit_result(None) is False


def test_none_is_transport_returns_false():
    assert tlc.is_transport_transient(None) is False


def test_empty_dict_is_turn_limit_returns_false():
    assert tlc.is_turn_limit_result({}) is False


def test_whitespace_only_returns_false():
    assert tlc.is_turn_limit_result("   ") is False
    assert tlc.is_transport_transient("   ") is False


def test_classify_empty_string_returns_well_defined_outcome():
    outcome = tlc.classify_result("")
    assert outcome.is_turn_limit is False
    assert outcome.transport_transient is False
    # Unclassified: not a free retry, charge the attempt.
    assert outcome.attempt_consuming is True


def test_classify_none_returns_well_defined_outcome():
    outcome = tlc.classify_result(None)
    assert outcome.is_turn_limit is False
    assert outcome.transport_transient is False
