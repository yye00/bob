"""Boundary tests for watchdog stall escalation.

AC: empty, zero, or minimum input returns a well-defined result rather than
raising (boundary case).

Tests the escalate_stall_observation function at boundary values:
  - observation_count=0 (zero/empty boundary)
  - observation_count=1 (minimum non-zero)
  - observation_count at exactly threshold (boundary trigger)
  - observation_count at threshold-1 (just below trigger)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.watchdog import escalate_stall_observation


class TestBoundaryZeroObservations:
    """Zero observation_count must return a well-defined result, not raise."""

    def test_zero_count_does_not_raise(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert isinstance(result, dict)

    def test_zero_count_returns_escalated_false(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert result["escalated"] is False

    def test_zero_count_does_not_write_marker(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_stall_observation(observation_count=0, marker_path=marker)
        assert not marker.exists()

    def test_zero_count_result_has_required_keys(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert "escalated" in result
        assert "threshold" in result
        assert "observation_count" in result
        assert "marker_path" in result


class TestBoundaryMinimumInput:
    """Minimum positive observation_count (1) must return a well-defined result."""

    def test_count_1_does_not_raise(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=1, marker_path=marker)
        assert isinstance(result, dict)

    def test_count_1_returns_escalated_false_with_default_threshold(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=1, marker_path=marker)
        assert result["escalated"] is False

    def test_count_1_observation_count_reflected_in_result(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=1, marker_path=marker)
        assert result["observation_count"] == 1


class TestBoundaryAtThreshold:
    """Exact threshold boundary: count == threshold triggers escalation."""

    def test_count_equals_default_threshold_escalates(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=5, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_count_one_below_threshold_does_not_escalate(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=4, marker_path=marker)
        assert result["escalated"] is False
        assert not marker.exists()

    def test_custom_threshold_boundary_at_exactly_n(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_stall_observation(observation_count=3, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_custom_threshold_boundary_at_n_minus_1(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_stall_observation(observation_count=2, marker_path=marker)
        assert result["escalated"] is False
        assert not marker.exists()


class TestBoundaryDefaultMarkerPath:
    """Calling without marker_path uses the default path (no exception)."""

    def test_no_marker_path_does_not_raise_below_threshold(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = escalate_stall_observation(observation_count=1)
        assert isinstance(result, dict)
        assert result["escalated"] is False

    def test_no_marker_path_escalates_and_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = escalate_stall_observation(observation_count=5)
        assert result["escalated"] is True
        assert (tmp_path / "bob4" / "tools" / "STALL_ATTENTION.txt").exists()


class TestBoundaryThresholdReflected:
    """Returned threshold must match the effective configuration."""

    def test_threshold_equals_default_5(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5

    def test_threshold_reflects_env_override(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "7"}):
            result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert result["threshold"] == 7
