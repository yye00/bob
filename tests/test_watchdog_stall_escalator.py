"""Tests for watchdog_stall_escalator.escalate_spec_gate_stall.

Verifies the AC-required function bob3.watchdog_stall_escalator.escalate_spec_gate_stall
correctly escalates repeated spec_gate_stall_observed events to a needs_human_attention
sentinel (HALT_ATTENTION marker + chain_dead_locked WARN log).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.watchdog_stall_escalator import escalate_spec_gate_stall


class TestEscalateSpecGateStallBasic:
    """Core behaviour: function exists, returns a dict with required keys."""

    def test_returns_dict(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert isinstance(result, dict)

    def test_result_has_required_keys(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert "escalated" in result
        assert "threshold" in result
        assert "observation_count" in result
        assert "marker_path" in result

    def test_observation_count_reflected_in_result(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=3, marker_path=marker)
        assert result["observation_count"] == 3

    def test_default_threshold_is_5(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5


class TestEscalateSpecGateStallBelowThreshold:
    """Below-threshold: escalated=False, no marker written."""

    def test_count_4_not_escalated(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=4, marker_path=marker)
        assert result["escalated"] is False

    def test_count_4_no_marker_written(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_spec_gate_stall(observation_count=4, marker_path=marker)
        assert not marker.exists()

    def test_count_0_not_escalated(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert result["escalated"] is False


class TestEscalateSpecGateStallAtThreshold:
    """At/above threshold: escalated=True, marker written, WARN logged."""

    def test_count_5_escalated(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=5, marker_path=marker)
        assert result["escalated"] is True

    def test_count_5_writes_marker(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_spec_gate_stall(observation_count=5, marker_path=marker)
        assert marker.exists()

    def test_marker_content_mentions_chain_dead_locked(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_spec_gate_stall(observation_count=5, marker_path=marker)
        content = marker.read_text()
        assert "chain_dead_locked" in content

    def test_count_10_escalated(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_spec_gate_stall(observation_count=10, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_warn_log_emitted_on_escalation(self, tmp_path, caplog):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING):
            escalate_spec_gate_stall(observation_count=5, marker_path=marker)
        assert any("chain_dead_locked" in r.message for r in caplog.records)


class TestEscalateSpecGateStallEnvOverride:
    """BOB3_STALL_ESCALATION_COUNT env var overrides default threshold."""

    def test_custom_threshold_3_escalates_at_3(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_spec_gate_stall(observation_count=3, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_custom_threshold_3_does_not_escalate_at_2(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_spec_gate_stall(observation_count=2, marker_path=marker)
        assert result["escalated"] is False

    def test_custom_threshold_reflected_in_result(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "7"}):
            result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert result["threshold"] == 7

    def test_invalid_env_falls_back_to_default(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "notanumber"}):
            result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5


class TestEscalateSpecGateStallErrorPath:
    """Negative observation_count must raise ValueError."""

    def test_negative_raises_value_error(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with pytest.raises(ValueError):
            escalate_spec_gate_stall(observation_count=-1, marker_path=marker)

    def test_negative_does_not_write_marker(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        try:
            escalate_spec_gate_stall(observation_count=-1, marker_path=marker)
        except ValueError:
            pass
        assert not marker.exists()


class TestEscalateSpecGateStallDefaultMarker:
    """Default marker path is used when marker_path is not provided."""

    def test_default_path_no_raise_below_threshold(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = escalate_spec_gate_stall(observation_count=1)
        assert result["escalated"] is False

    def test_default_path_creates_marker_at_threshold(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = escalate_spec_gate_stall(observation_count=5)
        assert result["escalated"] is True
        assert (tmp_path / "bob4" / "tools" / "STALL_ATTENTION.txt").exists()
