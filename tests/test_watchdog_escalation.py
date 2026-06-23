"""Tests for watchdog stall escalation via the public API.

Feature c024f7e6-5341-4b80-a49b-0a4dcb198623

Verifies escalate_stall_observation in bob3.watchdog escalates repeated
spec_gate_stall_observed events to a needs_human_attention sentinel after N
consecutive observations (default 5, configurable via BOB3_STALL_ESCALATION_COUNT).

Escalation:
 - Writes a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt by default)
 - Logs a chain_dead_locked event at WARN level
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.watchdog import escalate_spec_gate_stall, escalate_stall_observation


def test_escalate_after_n_consecutive_stalls(tmp_path):
    """After N consecutive stall observations, escalation sentinel is triggered."""
    marker = tmp_path / "STALL_ATTENTION.txt"
    for count in range(1, 5):
        result = escalate_spec_gate_stall(observation_count=count, marker_path=marker)
        assert result["escalated"] is False, f"Must not escalate before threshold, count={count}"
        assert not marker.exists()
    result = escalate_spec_gate_stall(observation_count=5, marker_path=marker)
    assert result["escalated"] is True
    assert marker.exists()
    assert len(marker.read_text()) > 0


def test_function_is_callable():
    assert callable(escalate_stall_observation)


def test_below_threshold_returns_escalated_false(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    for count in range(0, 5):
        result = escalate_stall_observation(observation_count=count, marker_path=marker)
        assert result["escalated"] is False, f"Should not escalate at count={count}"


def test_below_threshold_does_not_write_marker(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    for count in range(0, 5):
        marker.unlink(missing_ok=True)
        escalate_stall_observation(observation_count=count, marker_path=marker)
        assert not marker.exists(), f"Marker must not exist at count={count}"


def test_at_default_threshold_escalates(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    result = escalate_stall_observation(observation_count=5, marker_path=marker)
    assert result["escalated"] is True


def test_at_default_threshold_writes_marker(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    escalate_stall_observation(observation_count=5, marker_path=marker)
    assert marker.exists()


def test_above_threshold_escalates(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    for count in [6, 10, 100]:
        marker.unlink(missing_ok=True)
        result = escalate_stall_observation(observation_count=count, marker_path=marker)
        assert result["escalated"] is True, f"Should escalate at count={count}"
        assert marker.exists()


def test_marker_content_is_nonempty(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    escalate_stall_observation(observation_count=5, marker_path=marker)
    assert marker.exists()
    assert len(marker.read_text()) > 0


def test_result_has_required_keys(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    result = escalate_stall_observation(observation_count=3, marker_path=marker)
    assert "escalated" in result
    assert "threshold" in result
    assert "observation_count" in result
    assert "marker_path" in result


def test_result_observation_count_matches_input(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    result = escalate_stall_observation(observation_count=3, marker_path=marker)
    assert result["observation_count"] == 3


def test_default_threshold_is_5(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    result = escalate_stall_observation(observation_count=0, marker_path=marker)
    assert result["threshold"] == 5


def test_env_override_changes_threshold(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "3"}):
        result_below = escalate_stall_observation(observation_count=2, marker_path=marker)
        assert result_below["escalated"] is False
        marker.unlink(missing_ok=True)
        result_at = escalate_stall_observation(observation_count=3, marker_path=marker)
        assert result_at["escalated"] is True
        assert marker.exists()


def test_warn_log_emitted_on_escalation(tmp_path, caplog):
    marker = tmp_path / "STALL_ATTENTION.txt"
    with caplog.at_level(logging.WARNING):
        escalate_stall_observation(observation_count=5, marker_path=marker)
    assert any("chain_dead_locked" in r.message for r in caplog.records)


def test_no_warn_log_below_threshold(tmp_path, caplog):
    marker = tmp_path / "STALL_ATTENTION.txt"
    with caplog.at_level(logging.WARNING):
        escalate_stall_observation(observation_count=4, marker_path=marker)
    chain_dead_locked_logs = [r for r in caplog.records if "chain_dead_locked" in r.message]
    assert len(chain_dead_locked_logs) == 0


def test_marker_parent_created_when_missing(tmp_path):
    nested_marker = tmp_path / "bob4" / "tools" / "STALL_ATTENTION.txt"
    escalate_stall_observation(observation_count=5, marker_path=nested_marker)
    assert nested_marker.exists()


def test_invalid_env_threshold_falls_back_to_default(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "banana"}):
        result = escalate_stall_observation(observation_count=4, marker_path=marker)
        assert result["escalated"] is False
        marker.unlink(missing_ok=True)
        result = escalate_stall_observation(observation_count=5, marker_path=marker)
        assert result["escalated"] is True


def test_negative_count_raises_value_error(tmp_path):
    marker = tmp_path / "STALL_ATTENTION.txt"
    with pytest.raises(ValueError):
        escalate_stall_observation(observation_count=-1, marker_path=marker)


def test_default_marker_path_used_when_not_specified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = escalate_stall_observation(observation_count=5)
    assert result["escalated"] is True
    assert (tmp_path / "bob4" / "tools" / "STALL_ATTENTION.txt").exists()
