"""Tests that passes_gate(score=0.74) returns False at just-below-threshold boundary — AC-16."""

from __future__ import annotations

import pytest

from bob.verification.mutation_gate import default_threshold, passes_gate


class TestBelowThresholdRejects:
    def test_just_below_threshold_returns_false(self):
        score = 0.74
        result = passes_gate(score=score)
        assert result is False, (
            f"passes_gate(score=0.74) should return False (threshold is {default_threshold()}), "
            f"got {result!r}"
        )

    def test_threshold_is_0_75(self):
        assert default_threshold() == 0.75

    def test_0_74_is_below_0_75(self):
        assert 0.74 < default_threshold()

    def test_passes_gate_at_exactly_0_74_is_false(self):
        assert passes_gate(0.74) is False

    def test_passes_gate_at_0_75_is_true(self):
        assert passes_gate(0.75) is True

    def test_one_hundredth_below_threshold_fails(self):
        threshold = default_threshold()
        just_below = round(threshold - 0.01, 10)
        assert passes_gate(just_below) is False

    def test_epsilon_below_threshold_fails(self):
        threshold = default_threshold()
        just_below = threshold - 1e-9
        assert passes_gate(just_below) is False
