"""Tests for fbe6b19b: zero-cost telemetry loss detection.

Covers is_cost_telemetry_lost: the function that detects when
cost==0 is a stream-json telemetry miss rather than a genuinely
free run.

Key AC assertions:
- (cost=0, work_events=176217) → True (lost telemetry)
- (cost=0, work_events=0)      → False (clean spawn crash, free retry path)
- (cost=0.001, work_events=176217) → False (cost was reported, not lost)
"""

from __future__ import annotations

import os

import pytest

from bob3.orchestrator.cost_telemetry_guard import is_cost_telemetry_lost


class TestIsCostTelemetryLost:
    """Direct behavior tests for is_cost_telemetry_lost."""

    def test_zero_cost_high_work_events_is_lost(self):
        """AC: (cost=0, work_events=176217) classified as telemetry-lost (True)."""
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=176217) is True

    def test_zero_cost_zero_work_events_is_not_lost(self):
        """AC: (cost=0, work_events=0) classified as NOT telemetry-lost (clean spawn crash)."""
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=0) is False

    def test_nonzero_cost_high_work_events_is_not_lost(self):
        """AC: (cost=0.001, work_events=176217) classified as NOT telemetry-lost (cost was reported)."""
        assert is_cost_telemetry_lost(reported_cost=0.001, work_events=176217) is False

    def test_zero_cost_at_threshold_boundary_is_lost(self):
        """work_events == 101 (> default 100 threshold) → telemetry lost."""
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=101) is True

    def test_zero_cost_at_exact_threshold_is_not_lost(self):
        """work_events == 100 (== default threshold, not >) → NOT lost."""
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=100) is False

    def test_zero_cost_just_below_threshold_is_not_lost(self):
        """work_events == 99 (< default 100) → NOT lost."""
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=99) is False

    def test_positive_cost_zero_work_events_is_not_lost(self):
        """Positive cost, no work events → not lost (cost was reported)."""
        assert is_cost_telemetry_lost(reported_cost=1.23, work_events=0) is False

    def test_large_positive_cost_high_work_events_is_not_lost(self):
        """Large cost, large work_events → not lost (cost reported fine)."""
        assert is_cost_telemetry_lost(reported_cost=10.0, work_events=500000) is False

    def test_none_reported_cost_treated_as_zero(self):
        """None cost is coerced to 0.0; with high work_events → detected as lost."""
        assert is_cost_telemetry_lost(reported_cost=None, work_events=200) is True

    def test_none_reported_cost_zero_work_events_not_lost(self):
        """None cost is coerced to 0.0; with zero work_events → not lost."""
        assert is_cost_telemetry_lost(reported_cost=None, work_events=0) is False

    def test_negative_cost_treated_as_zero(self):
        """Negative cost (invalid SDK value) → coerced to 0.0, treated as zero-cost."""
        assert is_cost_telemetry_lost(reported_cost=-0.5, work_events=200) is True

    def test_very_small_positive_cost_not_lost(self):
        """Any positive cost means telemetry arrived; not lost."""
        assert is_cost_telemetry_lost(reported_cost=0.0001, work_events=200000) is False


class TestThresholdOverride:
    """BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD env var overrides the default."""

    def test_env_threshold_lower_fires_earlier(self, monkeypatch):
        """Setting threshold=10 means work_events=50 triggers detection."""
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "10")
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=50) is True

    def test_env_threshold_lower_boundary(self, monkeypatch):
        """work_events == threshold (not >) → still not lost."""
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "10")
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=10) is False

    def test_env_threshold_higher_suppresses_detection(self, monkeypatch):
        """Raising threshold to 1000 means work_events=176 does not trigger."""
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "1000")
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=176) is False

    def test_env_threshold_clamped_below_1(self, monkeypatch):
        """Threshold < 1 is clamped to 1; work_events=1 triggers (> 1 is false, = 1 is false, > 1 is true)."""
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "0")
        # clamped to 1; work_events=2 > 1 → True
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=2) is True

    def test_env_threshold_clamped_above_10000(self, monkeypatch):
        """Threshold > 10000 is clamped to 10000."""
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "99999")
        # clamped to 10000; work_events=9999 ≤ 10000 → not lost
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=9999) is False
        # work_events=10001 > 10000 → lost
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=10001) is True

    def test_env_threshold_invalid_falls_back_to_default(self, monkeypatch):
        """Non-numeric env var falls back to default 100."""
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "not_a_number")
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=101) is True
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=100) is False

    def test_env_threshold_negative_clamped_to_1(self, monkeypatch):
        """Negative threshold is clamped to 1."""
        monkeypatch.setenv("BOB3_COST_TELEMETRY_LOST_WORK_THRESHOLD", "-50")
        # clamped to 1; work_events=2 > 1 → True
        assert is_cost_telemetry_lost(reported_cost=0.0, work_events=2) is True
