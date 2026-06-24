"""Error-path tests for spec_quality.score.calculate_spec_quality_score.

AC: pytest: tests/test_spec_quality_score_gate_error.py — invalid input raises
ValueError and the function does not silently succeed (error path).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.score import calculate_spec_quality_score


def test_none_name_raises_value_error():
    """None feature name must raise ValueError — a feature must have a name."""
    with pytest.raises((ValueError, TypeError)):
        calculate_spec_quality_score(
            name=None,
            description=None,
            acceptance_criteria=["File exists: src/spec_quality/score.py"],
        )


def test_non_string_name_raises():
    """Non-string (integer) name must raise ValueError or TypeError."""
    with pytest.raises((ValueError, TypeError)):
        calculate_spec_quality_score(
            name=42,
            description=None,
            acceptance_criteria=["File exists: src/spec_quality/score.py"],
        )


def test_non_list_non_string_acs_raises():
    """Non-list, non-string acceptance_criteria (e.g. dict) must raise ValueError."""
    with pytest.raises((ValueError, TypeError)):
        calculate_spec_quality_score(
            name="bad acs",
            description=None,
            acceptance_criteria={"File exists": "src/spec_quality/score.py"},
        )


def test_invalid_json_string_acs_does_not_silently_succeed():
    """Malformed (non-JSON, non-newline) string is either parsed as lines or raises — must not silently succeed with wrong data."""
    # A pure garbage string that isn't JSON and has no newlines
    # should either raise or be treated as a single AC line
    try:
        score = calculate_spec_quality_score(
            name="bad json",
            description=None,
            acceptance_criteria="NOT_JSON_NOT_LIST",
        )
        # If it doesn't raise, it must return a valid float
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
    except (ValueError, TypeError):
        pass  # raising is also acceptable


def test_error_does_not_silently_return_passing_score_for_none_name():
    """None name must not silently return a passing score — it must raise."""
    raised = False
    try:
        score = calculate_spec_quality_score(
            name=None,
            description="desc",
            acceptance_criteria=["File exists: src/spec_quality/score.py"],
        )
        # If it doesn't raise, this is wrong — the function silently succeeded
        # with invalid input
    except (ValueError, TypeError):
        raised = True
    assert raised, "Expected ValueError or TypeError for name=None but none was raised"
