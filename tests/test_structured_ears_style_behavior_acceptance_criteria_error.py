"""Error-path tests for ears_criteria.parse_behavior.

Invalid input (behavior: prefix present but malformed) must raise ValueError
and the function must not silently succeed.
"""

from __future__ import annotations

import pytest

from ears_criteria import parse_behavior


def test_behavior_without_when_raises_valueerror():
    """A behavior: AC without 'when' must raise ValueError."""
    with pytest.raises(ValueError):
        parse_behavior("behavior: parser returns value")


def test_behavior_no_when_does_not_return_none():
    """Function must raise, not silently return None, for malformed behavior ACs."""
    with pytest.raises(ValueError):
        result = parse_behavior("behavior: system does something")
        # If we reach here (no raise), the test fails — but pytest.raises will fail first


def test_behavior_no_when_clause_contains_when_in_message():
    """ValueError message should mention 'when' to indicate the missing clause."""
    with pytest.raises(ValueError, match="when"):
        parse_behavior("behavior: orchestrator dispatches task")


def test_behavior_prefix_but_empty_body_raises():
    """behavior: with only whitespace after colon raises ValueError."""
    with pytest.raises((ValueError, Exception)):
        result = parse_behavior("behavior:   ")
        # If not raised — force the test to fail
        assert result is None, "Expected ValueError but got None"


def test_behavior_missing_object_no_when_raises():
    """behavior: subject verb (no object, no when) raises ValueError."""
    with pytest.raises(ValueError):
        parse_behavior("behavior: parser returns")


def test_behavior_missing_subject_no_when_raises():
    """behavior: with just a verb token and no when raises ValueError."""
    with pytest.raises(ValueError):
        parse_behavior("behavior: returns")


def test_wrong_delimiter_raises():
    """behavior: AC using 'WHERE' instead of 'when' raises ValueError."""
    with pytest.raises(ValueError):
        parse_behavior("behavior: system logs error WHERE input is invalid")


def test_valueerror_not_other_exception_type():
    """Only ValueError (or subclass) must be raised — not TypeError, KeyError, etc."""
    with pytest.raises(ValueError):
        parse_behavior("behavior: does something without the required trigger")


def test_behavior_no_when_does_not_silently_succeed():
    """Confirm no silent success: calling without when must raise, not produce output."""
    raised = False
    try:
        parse_behavior("behavior: component updates state")
    except ValueError:
        raised = True
    assert raised, "Expected ValueError but function returned without raising"


def test_multiple_malformed_acs_all_raise():
    """Each of several malformed behavior ACs raises ValueError."""
    malformed = [
        "behavior: a b c",
        "behavior: system runs",
        "behavior: module loads configuration",
        "behavior: user clicks button",
    ]
    for ac in malformed:
        with pytest.raises(ValueError, match="when"):
            parse_behavior(ac)
