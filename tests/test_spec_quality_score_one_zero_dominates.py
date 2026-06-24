"""Tests that verify geometric mean property: one zero sub-score dominates.

The key property of weighted geometric mean is that if any sub-score is 0,
the composite is driven to 0 regardless of other sub-scores.

This is a critical correctness requirement — it prevents a fatal flaw
from being averaged away by high scores in other dimensions.
"""

from __future__ import annotations

import os
import sys
import math
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from spec_quality_score import (
    compute,
    CompositeScore,
    _weighted_geometric_mean,
    _WEIGHTS,
    GATE_BLOCK,
)


class TestGeometricMeanZeroDominates:
    """Weighted geometric mean: any zero sub-score → composite = 0."""

    def test_one_zero_drives_composite_to_zero(self):
        scores = {
            "smell_density": 0.0,  # fatal flaw
            "predicate_coverage": 1.0,
            "contract_completeness": 1.0,
            "boundary_coverage": 1.0,
            "error_path_coverage": 1.0,
            "traceability": 1.0,
            "spec_executability": 1.0,
            "ac_atomicity": 1.0,
        }
        result = _weighted_geometric_mean(scores, _WEIGHTS)
        assert result == 0.0, f"Expected 0.0 with one zero score, got {result}"

    def test_zero_predicate_drives_composite_to_zero(self):
        scores = {
            "smell_density": 1.0,
            "predicate_coverage": 0.0,  # fatal flaw
            "contract_completeness": 1.0,
            "boundary_coverage": 1.0,
            "error_path_coverage": 1.0,
            "traceability": 1.0,
            "spec_executability": 1.0,
            "ac_atomicity": 1.0,
        }
        result = _weighted_geometric_mean(scores, _WEIGHTS)
        assert result == 0.0, f"Expected 0.0 with zero predicate_coverage, got {result}"

    def test_all_perfect_gives_one(self):
        scores = {k: 1.0 for k in _WEIGHTS}
        result = _weighted_geometric_mean(scores, _WEIGHTS)
        assert abs(result - 1.0) < 1e-9, f"Expected 1.0, got {result}"

    def test_all_half_gives_half(self):
        scores = {k: 0.5 for k in _WEIGHTS}
        result = _weighted_geometric_mean(scores, _WEIGHTS)
        # geometric mean of all 0.5 = 0.5 regardless of weights
        assert abs(result - 0.5) < 1e-9, f"Expected 0.5, got {result}"

    def test_two_zeros_still_zero(self):
        scores = {
            "smell_density": 0.0,
            "predicate_coverage": 0.0,
            "contract_completeness": 1.0,
            "boundary_coverage": 1.0,
            "error_path_coverage": 1.0,
            "traceability": 1.0,
            "spec_executability": 1.0,
            "ac_atomicity": 1.0,
        }
        result = _weighted_geometric_mean(scores, _WEIGHTS)
        assert result == 0.0

    def test_small_score_dominates_high_others(self):
        # A score of 0.01 in a 0.20-weight dimension should pull composite well below 0.5
        scores = {
            "smell_density": 0.01,
            "predicate_coverage": 1.0,
            "contract_completeness": 1.0,
            "boundary_coverage": 1.0,
            "error_path_coverage": 1.0,
            "traceability": 1.0,
            "spec_executability": 1.0,
            "ac_atomicity": 1.0,
        }
        result = _weighted_geometric_mean(scores, _WEIGHTS)
        # 0.01^0.20 * 1.0^0.80 = 0.01^0.20 ≈ 0.398
        expected = 0.01 ** 0.20
        assert abs(result - expected) < 1e-5, f"Expected ~{expected:.4f}, got {result:.4f}"
        assert result < 0.5


class TestComputeZeroSubScore:
    """compute() with all-bad ACs should produce zero composite due to geometric mean."""

    def test_all_bad_acs_produces_zero_or_blocked(self):
        result = compute(
            "Bad feature",
            None,
            [
                "The system should be fast and reliable",
                "Works correctly for all inputs",
                "Simple and easy to use",
            ],
        )
        # predicate_coverage = 0 (no concrete predicates) → composite = 0
        assert result.predicate_coverage == 0.0
        assert result.composite == 0.0

    def test_zero_traceability_blocks_composite(self):
        # Verify that specs with all structured ACs score well on traceability/executability
        # even when boundary/error paths are zero (those also drive composite to 0)
        result = compute(
            "Partial feature",
            None,
            [
                "File exists: src/foo.py",
                "pytest: tests/test_foo.py",
                "Score raises ValueError on empty input",  # error path
                "Score handles empty list boundary case",  # boundary
            ],
        )
        # These ACs include error + boundary coverage, so composite > 0
        assert result.spec_executability >= 0.5
        assert result.traceability >= 0.5
        assert result.error_path_coverage > 0.0
        assert result.boundary_coverage > 0.0
        assert result.composite > 0.0

    def test_no_error_path_acs_drives_to_zero(self):
        # A spec with no error ACs gets error_path_coverage=0 → composite=0
        result = compute(
            "No errors feature",
            None,
            [
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "pytest: tests/test_foo.py",
                "integration: bob.cli.run",
            ],
        )
        assert result.error_path_coverage == 0.0
        assert result.composite == 0.0, (
            f"Expected composite=0 due to zero error_path_coverage, got {result.composite}"
        )

    def test_no_boundary_acs_drives_to_zero(self):
        result = compute(
            "No boundaries feature",
            None,
            [
                "File exists: src/foo.py",
                "Function defined: foo.bar",
                "pytest: tests/test_foo.py",
            ],
        )
        assert result.boundary_coverage == 0.0
        assert result.composite == 0.0


class TestGeometricMeanVsArithmeticMean:
    """Geometric mean scores lower than arithmetic mean when scores vary."""

    def test_geometric_lower_than_arithmetic_for_uneven_scores(self):
        scores = {
            "smell_density": 0.1,
            "predicate_coverage": 1.0,
            "contract_completeness": 1.0,
            "boundary_coverage": 1.0,
            "error_path_coverage": 1.0,
            "traceability": 1.0,
            "spec_executability": 1.0,
            "ac_atomicity": 1.0,
        }
        geometric = _weighted_geometric_mean(scores, _WEIGHTS)
        # Arithmetic weighted mean
        arithmetic = sum(scores[k] * _WEIGHTS[k] for k in _WEIGHTS)
        assert geometric < arithmetic, (
            f"Geometric ({geometric:.4f}) should be < Arithmetic ({arithmetic:.4f}) "
            "for uneven scores"
        )

    def test_geometric_equals_arithmetic_for_equal_scores(self):
        # When all scores are equal, geometric = arithmetic
        scores = {k: 0.7 for k in _WEIGHTS}
        geometric = _weighted_geometric_mean(scores, _WEIGHTS)
        arithmetic = sum(scores[k] * _WEIGHTS[k] for k in _WEIGHTS)
        assert abs(geometric - arithmetic) < 1e-6
