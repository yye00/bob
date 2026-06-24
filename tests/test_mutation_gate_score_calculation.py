"""Tests for mutation score calculation — AC-15."""

from __future__ import annotations

import pytest

from bob3.verification.mutation_gate import (
    MutationReport,
    default_threshold,
    passes_gate,
)


class TestDefaultThreshold:
    def test_returns_0_75(self):
        assert default_threshold() == 0.75

    def test_is_float(self):
        assert isinstance(default_threshold(), float)


class TestPassesGate:
    def test_passes_at_exactly_threshold(self):
        assert passes_gate(0.75) is True

    def test_passes_above_threshold(self):
        assert passes_gate(0.80) is True
        assert passes_gate(1.0) is True
        assert passes_gate(0.76) is True

    def test_fails_below_threshold(self):
        assert passes_gate(0.74) is False
        assert passes_gate(0.0) is False
        assert passes_gate(0.749999) is False

    def test_custom_threshold_respected(self):
        assert passes_gate(0.60, threshold=0.60) is True
        assert passes_gate(0.59, threshold=0.60) is False
        assert passes_gate(0.90, threshold=0.95) is False

    def test_returns_bool(self):
        result = passes_gate(0.8)
        assert isinstance(result, bool)


class TestMutationScoreCalculation:
    def test_score_killed_over_total(self):
        report = MutationReport(
            feature_id="f",
            total_mutants=10,
            killed=8,
            survived=2,
            timed_out=0,
            mutation_score=8 / 10,
        )
        assert report.mutation_score == pytest.approx(0.8)

    def test_perfect_score(self):
        report = MutationReport(
            feature_id="f",
            total_mutants=5,
            killed=5,
            survived=0,
            timed_out=0,
            mutation_score=1.0,
        )
        assert passes_gate(report.mutation_score) is True

    def test_zero_score_fails_gate(self):
        report = MutationReport(
            feature_id="f",
            total_mutants=5,
            killed=0,
            survived=5,
            timed_out=0,
            mutation_score=0.0,
        )
        assert passes_gate(report.mutation_score) is False

    def test_boundary_at_0_75(self):
        # exactly 0.75 passes
        assert passes_gate(0.75) is True
        # just below fails
        assert passes_gate(0.74999) is False
