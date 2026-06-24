"""Tests that the parser handles empty or missing subjects appropriately."""
import pytest
from bob.spec_quality.ears_parser import (
    BehaviorAC,
    EARSParseError,
    parse_behavior_ac,
    raises_on_malformed,
)


def test_parse_behavior_ac_returns_none_for_empty_string():
    result = parse_behavior_ac("")
    assert result is None


def test_parse_behavior_ac_returns_none_for_whitespace_only():
    result = parse_behavior_ac("   ")
    assert result is None


def test_raises_on_malformed_raises_for_empty_string():
    with pytest.raises(EARSParseError):
        raises_on_malformed("")


def test_raises_on_malformed_raises_for_whitespace_only():
    with pytest.raises(EARSParseError):
        raises_on_malformed("   ")


def test_raises_on_malformed_error_message_for_empty():
    with pytest.raises(EARSParseError, match="empty"):
        raises_on_malformed("")


def test_parse_behavior_ac_behavior_colon_only_returns_none():
    """'behavior:' with no content is not a valid AC."""
    result = parse_behavior_ac("behavior:")
    assert result is None


def test_raises_on_malformed_raises_for_behavior_colon_only():
    with pytest.raises(EARSParseError):
        raises_on_malformed("behavior:")
