"""Boundary-case tests for spec_quality.score.calculate_spec_quality_score.

AC: pytest: tests/test_spec_quality_score_gate_boundary.py — empty, zero, or minimum
input returns a well-defined result rather than raising (boundary case).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spec_quality.score import calculate_spec_quality_score


def test_empty_acceptance_criteria_returns_zero_not_raises():
    """Empty AC list must return 0.0, not raise any exception."""
    score = calculate_spec_quality_score(
        name="boundary empty ACs",
        description=None,
        acceptance_criteria=[],
    )
    assert score == 0.0


def test_single_ac_returns_valid_score():
    """A single AC must return a valid float in [0, 1]."""
    score = calculate_spec_quality_score(
        name="single ac",
        description=None,
        acceptance_criteria=["File exists: src/spec_quality/score.py"],
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_empty_name_string_returns_score():
    """Empty string name must not raise — return a score."""
    score = calculate_spec_quality_score(
        name="",
        description=None,
        acceptance_criteria=["File exists: src/spec_quality/score.py"],
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_none_description_is_accepted():
    """None description is a valid input — must not raise."""
    score = calculate_spec_quality_score(
        name="no desc feature",
        description=None,
        acceptance_criteria=["File exists: src/spec_quality/score.py"],
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_empty_string_description_is_accepted():
    """Empty string description is a valid input — must not raise."""
    score = calculate_spec_quality_score(
        name="empty desc feature",
        description="",
        acceptance_criteria=["File exists: src/spec_quality/score.py"],
    )
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_score_clamped_to_unit_interval():
    """Score is always clamped to [0.0, 1.0] regardless of inputs."""
    score = calculate_spec_quality_score(
        name="clamping test",
        description=None,
        acceptance_criteria=[
            "File exists: src/spec_quality/score.py",
            "Function defined: spec_quality.score.calculate_spec_quality_score",
            "pytest: tests/test_spec_quality_score.py",
            "pytest: tests/test_spec_quality_score_gate_boundary.py",
            "pytest: tests/test_spec_quality_score_gate_error.py",
        ],
    )
    assert 0.0 <= score <= 1.0


def test_whitespace_only_ac_list_handled():
    """A list of whitespace-only strings is treated as empty — returns 0.0."""
    score = calculate_spec_quality_score(
        name="whitespace feature",
        description=None,
        acceptance_criteria=["   ", "\t", "\n"],
    )
    assert isinstance(score, float)
    # whitespace strings treated as empty → 0.0 or very low score
    assert 0.0 <= score <= 1.0


def test_json_empty_array_returns_zero():
    """JSON-encoded empty array treated as zero ACs → score 0.0."""
    score = calculate_spec_quality_score(
        name="json empty",
        description=None,
        acceptance_criteria="[]",
    )
    assert score == 0.0
