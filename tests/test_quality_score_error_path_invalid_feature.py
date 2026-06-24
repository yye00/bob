"""Tests for error paths and invalid input in compute_score.

AC: tests/test_quality_score_error_path_invalid_feature.py asserts
    compute_score(None) raises TypeError with message containing "feature"
"""

from __future__ import annotations

import pytest

from bob3.spec_quality.quality_score import (
    BelowQualityScoreError,
    QualityReport,
    ScoreComponents,
    compute_score,
    raises_below_threshold,
)


@pytest.fixture(autouse=True)
def _reset_threshold_to_default(monkeypatch):
    """Ensure the quality threshold is 0.85 for every test in this module."""
    monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "0.85")
    import bob3.spec_quality.threshold_resolver as _tr
    _tr._frozen_value = None
    _tr._frozen_initialized = False
    yield
    _tr._frozen_value = None
    _tr._frozen_initialized = False


def test_compute_score_raises_type_error_for_none_name():
    with pytest.raises(TypeError) as exc_info:
        compute_score(None, None, [])
    assert "feature" in str(exc_info.value).lower()


def test_compute_score_none_name_error_message_contains_feature():
    try:
        compute_score(None, "Some description", ["AC one"])
    except TypeError as e:
        assert "feature" in str(e).lower()
    else:
        pytest.fail("Expected TypeError was not raised")


def test_raises_below_threshold_raises_for_low_score():
    report = QualityReport(
        score=0.50,
        components=ScoreComponents(0.5, 0.5, 0.5, 0.5),
    )
    with pytest.raises(BelowQualityScoreError):
        raises_below_threshold(report)


def test_raises_below_threshold_message_contains_score():
    report = QualityReport(
        score=0.40,
        components=ScoreComponents(0.4, 0.4, 0.4, 0.4),
    )
    with pytest.raises(BelowQualityScoreError) as exc_info:
        raises_below_threshold(report)
    assert "0.40" in str(exc_info.value) or "0.4" in str(exc_info.value)


def test_raises_below_threshold_does_not_raise_for_passing_score():
    report = QualityReport(
        score=0.90,
        components=ScoreComponents(0.9, 0.9, 0.9, 0.9),
    )
    raises_below_threshold(report)


def test_raises_below_threshold_does_not_raise_at_exact_threshold():
    report = QualityReport(
        score=0.85,
        components=ScoreComponents(0.85, 0.85, 0.85, 0.85),
    )
    raises_below_threshold(report)


def test_below_quality_score_error_is_exception():
    assert issubclass(BelowQualityScoreError, Exception)


def test_raises_below_threshold_message_contains_blocked():
    report = QualityReport(
        score=0.30,
        components=ScoreComponents(0.3, 0.3, 0.3, 0.3),
    )
    with pytest.raises(BelowQualityScoreError) as exc_info:
        raises_below_threshold(report)
    assert "BLOCKED" in str(exc_info.value)
