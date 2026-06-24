"""Tests for bob.watchdog_escalator.escalate_spec_gate_stalls.

Feature b6f360f6-a0f9-450b-ac15-5dc1b02728c1

The watchdog escalator module exposes escalate_spec_gate_stalls as the
canonical public entry-point for escalating repeated spec_gate_stall_observed
events to a needs_human_attention sentinel (HALT_ATTENTION marker file +
WARN-level chain_dead_locked log event).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.watchdog_escalator import escalate_spec_gate_stalls


class TestModuleImport:
    """The module and function must be importable."""

    def test_function_is_callable(self):
        assert callable(escalate_spec_gate_stalls)

    def test_function_is_exported(self):
        import bob.watchdog_escalator as mod
        assert "escalate_spec_gate_stalls" in mod.__all__


class TestBelowThreshold:
    """Counts below default threshold (5) must not escalate."""

    def test_count_0_not_escalated(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stalls(observation_count=0, marker_path=marker)
        assert result["escalated"] is False
        assert not marker.exists()

    def test_count_4_not_escalated(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stalls(observation_count=4, marker_path=marker)
        assert result["escalated"] is False
        assert not marker.exists()

    def test_result_has_required_keys(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stalls(observation_count=0, marker_path=marker)
        assert "escalated" in result
        assert "threshold" in result
        assert "observation_count" in result
        assert "marker_path" in result

    def test_threshold_defaults_to_5(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stalls(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5


class TestAtThreshold:
    """Counts at or above default threshold must escalate."""

    def test_count_5_escalates(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stalls(observation_count=5, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_count_10_escalates(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stalls(observation_count=10, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_marker_file_content_mentions_chain_dead_locked(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_spec_gate_stalls(observation_count=5, marker_path=marker)
        content = marker.read_text()
        assert "chain_dead_locked" in content

    def test_result_marker_path_is_absolute(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stalls(observation_count=5, marker_path=marker)
        assert Path(result["marker_path"]).is_absolute()


class TestEnvOverride:
    """BOB_STALL_ESCALATION_COUNT overrides the default threshold."""

    def test_env_threshold_3_escalates_at_3(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_spec_gate_stalls(observation_count=3, marker_path=marker)
        assert result["escalated"] is True
        assert result["threshold"] == 3

    def test_env_threshold_3_does_not_escalate_at_2(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_spec_gate_stalls(observation_count=2, marker_path=marker)
        assert result["escalated"] is False

    def test_invalid_env_falls_back_to_default(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "bad"}):
            result = escalate_spec_gate_stalls(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5


class TestErrorPaths:
    """Invalid inputs must raise ValueError."""

    def test_negative_count_raises_value_error(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with pytest.raises(ValueError):
            escalate_spec_gate_stalls(observation_count=-1, marker_path=marker)

    def test_negative_count_does_not_write_marker(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        try:
            escalate_spec_gate_stalls(observation_count=-1, marker_path=marker)
        except ValueError:
            pass
        assert not marker.exists()


class TestWarnLogging:
    """Escalation must emit a WARN-level chain_dead_locked log event."""

    def test_escalation_logs_warn(self, tmp_path, caplog):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING):
            escalate_spec_gate_stalls(observation_count=5, marker_path=marker)
        assert any("chain_dead_locked" in r.message for r in caplog.records)

    def test_no_warn_below_threshold(self, tmp_path, caplog):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING):
            escalate_spec_gate_stalls(observation_count=4, marker_path=marker)
        chain_records = [r for r in caplog.records if "chain_dead_locked" in r.message]
        assert len(chain_records) == 0
