"""Tests for the zero-AC boundary case in compute_score.

AC: tests/test_quality_score_gate_zero_ac_list.py asserts
    compute_score(feature_with_zero_acs) returns 0.0 (zero-element boundary)
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.quality_score import compute_score, handle_zero_ac_list


def test_compute_score_returns_zero_for_empty_ac_list():
    report = compute_score(
        name="Empty AC feature",
        description="A feature with no acceptance criteria.",
        acceptance_criteria=[],
    )
    assert report.score == 0.0


def test_compute_score_returns_zero_for_json_empty_list():
    report = compute_score(
        name="Empty AC feature JSON",
        description=None,
        acceptance_criteria="[]",
    )
    assert report.score == 0.0


def test_compute_score_returns_zero_for_whitespace_only_string():
    report = compute_score(
        name="Whitespace AC feature",
        description=None,
        acceptance_criteria="   \n  \n  ",
    )
    assert report.score == 0.0


def test_handle_zero_ac_list_returns_zero():
    score = handle_zero_ac_list("Feature with no ACs")
    assert score == 0.0


def test_handle_zero_ac_list_score_is_float():
    score = handle_zero_ac_list("Feature with no ACs")
    assert isinstance(score, float)


def test_zero_ac_report_has_remediation_hints():
    report = compute_score(
        name="No AC feature",
        description=None,
        acceptance_criteria=[],
    )
    assert len(report.remediation_hints) > 0


def test_zero_ac_all_components_are_zero():
    report = compute_score(
        name="No AC feature",
        description=None,
        acceptance_criteria=[],
    )
    assert report.components.ambiguity_score == 0.0
    assert report.components.reachability_score == 0.0
    assert report.components.ears_score == 0.0
    assert report.components.ac_coverage_score == 0.0
