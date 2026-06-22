"""Tests for score_gate_threshold_from_env.

Verifies env-based threshold reading, clamping, and defaults.
"""
from __future__ import annotations

import pytest

from bob3.spec_synthesizer import score_gate_threshold_from_env


class TestScoreGateThresholdFromEnv:
    """score_gate_threshold_from_env reads and clamps threshold from env."""

    def test_default_threshold_is_0_85(self, monkeypatch):
        """Default threshold is 0.85 when env var is not set."""
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD", raising=False)
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(0.85)

    def test_reads_from_env(self, monkeypatch):
        """Returns the float value from BOB3_SPEC_QUALITY_THRESHOLD."""
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "0.70")
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(0.70)

    def test_clamps_to_maximum_1_0(self, monkeypatch):
        """Clamps to 1.0 when env value exceeds 1.0."""
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "1.5")
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(1.0)

    def test_clamps_to_minimum_0_0(self, monkeypatch):
        """Clamps to 0.0 when env value is below 0.0."""
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "-0.5")
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(0.0)

    def test_returns_default_on_invalid_value(self, monkeypatch):
        """Returns default 0.85 when env var is not a valid float."""
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "not_a_float")
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(0.85)

    def test_returns_exact_boundary_1_0(self, monkeypatch):
        """Returns exactly 1.0 when env is set to '1.0'."""
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "1.0")
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(1.0)

    def test_returns_exact_boundary_0_0(self, monkeypatch):
        """Returns exactly 0.0 when env is set to '0.0'."""
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "0.0")
        threshold = score_gate_threshold_from_env()
        assert threshold == pytest.approx(0.0)
