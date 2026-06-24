"""Boundary tests for spec_quality_score gate threshold honor BOB_SPEC_QUALITY_THRESHOLD.

Verifies that empty, zero, or minimum inputs return a well-defined result
rather than raising. Boundary cases include:
- Empty acceptance criteria list (score=0.0, gate blocked, no exception)
- Zero threshold (all features pass)
- Threshold at exactly 0.0 and 1.0 boundary values
- Feature name as empty string (well-defined, not an error at this level)
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

import bob.spec_quality.threshold_resolver as _tr
from bob.spec_quality.quality_score import (
    _resolve_threshold,
    score_threshold,
    gate_for_ready,
    compute_score,
    QualityReport,
    ScoreComponents,
)


def _reset_frozen():
    _tr._frozen_initialized = False
    _tr._frozen_value = None


def _make_report(score: float) -> QualityReport:
    return QualityReport(
        score=score,
        components=ScoreComponents(
            ambiguity_score=score,
            reachability_score=score,
            ears_score=score,
            ac_coverage_score=score,
        ),
    )


class TestBoundaryEmptyAC:
    """Empty acceptance criteria returns 0.0 score without raising."""

    def test_empty_list_returns_zero_score(self):
        report = compute_score(
            name="boundary-feature",
            description=None,
            acceptance_criteria=[],
        )
        assert report.score == pytest.approx(0.0)

    def test_empty_list_gate_fails_not_raises(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        _reset_frozen()

        report = compute_score(
            name="boundary-feature",
            description=None,
            acceptance_criteria=[],
        )
        # gate_for_ready must return a tuple, not raise
        result = gate_for_ready(report)
        assert isinstance(result, tuple)
        passed, msg = result
        assert passed is False
        assert msg is not None

    def test_empty_string_ac_returns_zero(self):
        report = compute_score(
            name="boundary-feature",
            description=None,
            acceptance_criteria="",
        )
        assert report.score == pytest.approx(0.0)

    def test_whitespace_only_ac_returns_zero(self):
        report = compute_score(
            name="boundary-feature",
            description=None,
            acceptance_criteria="   \n   ",
        )
        assert report.score == pytest.approx(0.0)


class TestBoundaryZeroThreshold:
    """Zero threshold allows all features through the gate."""

    def test_zero_threshold_all_pass(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        _reset_frozen()

        threshold = _resolve_threshold()
        assert threshold == pytest.approx(0.0)

    def test_score_threshold_zero(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        _reset_frozen()

        assert score_threshold() == pytest.approx(0.0)

    def test_gate_passes_any_score_at_zero_threshold(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")

        # Even score=0.0 should pass when threshold=0.0
        for score in [0.0, 0.01, 0.5, 1.0]:
            report = _make_report(score)
            passed, msg = gate_for_ready(report)
            assert passed is True, f"score={score} should pass gate at threshold=0.0"
            assert msg is None


class TestBoundaryExactThreshold:
    """Score exactly at threshold boundary passes the gate."""

    def test_score_equals_threshold_passes(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")

        report = _make_report(0.55)
        passed, msg = gate_for_ready(report)
        assert passed is True, "Score exactly at threshold should pass"
        assert msg is None

    def test_score_just_below_threshold_blocks(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")

        report = _make_report(0.5499)
        passed, msg = gate_for_ready(report)
        assert passed is False, "Score just below threshold should block"
        assert msg is not None

    def test_threshold_1_0_only_perfect_score_passes(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "1.0")

        # Score 1.0 should pass
        passed, _ = gate_for_ready(_make_report(1.0))
        assert passed is True

        # Score 0.999 should block
        passed, _ = gate_for_ready(_make_report(0.999))
        assert passed is False


class TestBoundaryMinimumInput:
    """Minimum/edge inputs produce well-defined results without exceptions."""

    def test_single_ac_does_not_raise(self):
        report = compute_score(
            name="x",
            description=None,
            acceptance_criteria=["File exists: src/foo.py"],
        )
        assert isinstance(report.score, float)
        assert 0.0 <= report.score <= 1.0

    def test_description_none_does_not_raise(self):
        report = compute_score(
            name="feature",
            description=None,
            acceptance_criteria=["File exists: src/foo.py"],
        )
        assert isinstance(report.score, float)

    def test_very_low_env_threshold_returns_valid_float(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.000001")

        threshold = _resolve_threshold()
        assert isinstance(threshold, float)
        assert threshold >= 0.0
        assert threshold <= 1.0

    def test_zero_score_report_does_not_raise_on_gate(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)

        report = _make_report(0.0)
        # Must not raise, must return a tuple
        result = gate_for_ready(report)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_resolve_threshold_called_multiple_times_consistent(self, monkeypatch):
        """Multiple calls with same env var should return same value."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.65")

        v1 = _resolve_threshold()
        v2 = _resolve_threshold()
        assert v1 == v2 == pytest.approx(0.65)
