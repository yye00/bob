"""Error-path tests for watchdog stall escalation.

AC: invalid input raises ValueError and the function does not silently succeed
(error path).

Tests that escalate_stall_observation raises ValueError for clearly invalid
inputs like negative observation counts, and that it does NOT silently succeed
on such inputs.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.watchdog import escalate_stall_observation


class TestErrorNegativeObservationCount:
    """Negative observation_count must raise ValueError, not silently return."""

    def test_negative_count_raises_value_error(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with pytest.raises(ValueError):
            escalate_stall_observation(observation_count=-1, marker_path=marker)

    def test_large_negative_count_raises_value_error(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with pytest.raises(ValueError):
            escalate_stall_observation(observation_count=-100, marker_path=marker)

    def test_negative_count_does_not_write_marker(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        try:
            escalate_stall_observation(observation_count=-1, marker_path=marker)
        except ValueError:
            pass
        assert not marker.exists(), "Marker must not be written on invalid input"

    def test_minus_one_does_not_silently_succeed(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        raised = False
        try:
            escalate_stall_observation(observation_count=-1, marker_path=marker)
        except ValueError:
            raised = True
        assert raised, "Expected ValueError for observation_count=-1 but none raised"


class TestErrorInvalidEnvThreshold:
    """Invalid BOB_STALL_ESCALATION_COUNT env values must not silently corrupt results."""

    def test_non_numeric_env_falls_back_to_default_threshold(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "not_a_number"}):
            result = escalate_stall_observation(observation_count=4, marker_path=marker)
        assert result["escalated"] is False
        assert result["threshold"] == 5

    def test_zero_env_falls_back_to_default_threshold(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "0"}):
            result = escalate_stall_observation(observation_count=4, marker_path=marker)
        assert result["threshold"] == 5

    def test_negative_env_falls_back_to_default_threshold(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "-3"}):
            result = escalate_stall_observation(observation_count=4, marker_path=marker)
        assert result["threshold"] == 5

    def test_empty_string_env_falls_back_to_default(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": ""}):
            result = escalate_stall_observation(observation_count=4, marker_path=marker)
        assert result["threshold"] == 5


class TestErrorMarkerFileWrittenOnlyOnEscalation:
    """Marker file must NOT be written on invalid/below-threshold inputs."""

    def test_below_threshold_never_writes_marker(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        for count in range(0, 5):
            marker.unlink(missing_ok=True)
            result = escalate_stall_observation(observation_count=count, marker_path=marker)
            assert not marker.exists(), f"Marker written at count={count} (below threshold)"
            assert result["escalated"] is False

    def test_negative_input_never_writes_marker(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        for count in [-1, -5, -10]:
            marker.unlink(missing_ok=True)
            try:
                escalate_stall_observation(observation_count=count, marker_path=marker)
            except ValueError:
                pass
            assert not marker.exists(), f"Marker incorrectly written for count={count}"
