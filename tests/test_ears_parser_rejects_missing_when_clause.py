"""Tests that raises_on_malformed raises EARSParseError when 'when' clause is missing."""
import pytest
from bob.spec_quality.ears_parser import EARSParseError, raises_on_malformed


def test_raises_when_no_when_clause():
    with pytest.raises(EARSParseError):
        raises_on_malformed("behavior: subject verb object")


def test_raises_when_only_behavior_prefix():
    with pytest.raises(EARSParseError):
        raises_on_malformed("behavior: something happens")


def test_raises_message_mentions_when():
    with pytest.raises(EARSParseError, match="when"):
        raises_on_malformed("behavior: parser returns result")


def test_does_not_raise_when_when_clause_present():
    result = raises_on_malformed("behavior: parser returns BehaviorAC when AC matches grammar")
    assert result is not None
    assert result.condition == "AC matches grammar"


def test_raises_on_partial_when_keyword_in_subject():
    """'whenever' in subject should not satisfy the when clause requirement."""
    with pytest.raises(EARSParseError):
        raises_on_malformed("behavior: system whenever triggered")
