"""Tests that parse_behavior_ac raises/rejects empty and invalid inputs."""
import pytest
from bob.spec_quality.ears_parser import EARSParseError, parse_behavior_ac, raises_on_malformed


def test_parse_behavior_ac_rejects_empty_string():
    """parse_behavior_ac must return None for empty input."""
    result = parse_behavior_ac("")
    assert result is None


def test_raises_on_malformed_raises_for_empty_string():
    """raises_on_malformed must raise an error for empty input."""
    with pytest.raises(EARSParseError):
        raises_on_malformed("")


def test_raises_on_malformed_raises_for_invalid_input():
    """raises_on_malformed must raise for any non-behavior AC string."""
    with pytest.raises(EARSParseError):
        raises_on_malformed("not a behavior ac at all")


def test_parse_behavior_ac_returns_none_not_raises_for_empty():
    """parse_behavior_ac should NOT raise for empty — returns None."""
    result = parse_behavior_ac("")
    assert result is None  # None, not EARSParseError


def test_raises_on_malformed_error_is_ears_parse_error():
    with pytest.raises(EARSParseError) as exc_info:
        raises_on_malformed("")
    assert isinstance(exc_info.value, EARSParseError)


def test_raises_on_malformed_error_is_value_error_subclass():
    """EARSParseError is a ValueError subclass."""
    with pytest.raises(ValueError):
        raises_on_malformed("")
