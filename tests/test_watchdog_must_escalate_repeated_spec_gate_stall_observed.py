"""Tests for watchdog escalation of repeated spec_gate_stall_observed events.

Feature 21e7c6f5-0435-4bc2-862a-1724f4e19232

The watchdog must escalate spec_gate_stall_observed to a
needs_human_attention sentinel after N consecutive observations
(default 5, configurable via BOB_STALL_ESCALATION_COUNT).

Escalation:
 - Writes a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt)
 - Logs a chain_dead_locked event at WARN level
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.watchdog_must_escalate_repeated_spec_gate_stall_observed import (
    watchdog_must_escalate_repeated_spec_gate_stall_observed,
)


def test_watchdog_must_escalate_repeated_spec_gate_stall_observed():
    """AC smoke test: function is callable; escalates after threshold."""
    assert callable(watchdog_must_escalate_repeated_spec_gate_stall_observed)

    with tempfile.TemporaryDirectory() as tmpdir:
        marker_file = Path(tmpdir) / "STALL_ATTENTION.txt"

        # 4 observations below threshold (default 5) — no escalation
        for i in range(1, 5):
            result = watchdog_must_escalate_repeated_spec_gate_stall_observed(
                observation_count=i,
                marker_path=marker_file,
            )
            assert result["escalated"] is False, f"Should not escalate at count={i}"
            assert not marker_file.exists(), f"Marker must not exist at count={i}"

        # 5th observation — must escalate
        result = watchdog_must_escalate_repeated_spec_gate_stall_observed(
            observation_count=5,
            marker_path=marker_file,
        )
        assert result["escalated"] is True
        assert marker_file.exists(), "Marker file must be written on escalation"
        content = marker_file.read_text()
        assert len(content) > 0


def test_no_escalation_below_threshold():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        for count in range(1, 5):
            result = fn(observation_count=count, marker_path=marker)
            assert result["escalated"] is False
            assert not marker.exists()


def test_escalation_at_default_threshold():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        result = fn(observation_count=5, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()


def test_escalation_above_threshold():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        for count in [5, 6, 10, 100]:
            marker.unlink(missing_ok=True)
            result = fn(observation_count=count, marker_path=marker)
            assert result["escalated"] is True
            assert marker.exists()


def test_escalation_count_env_override():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"

        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "3"}):
            result = fn(observation_count=2, marker_path=marker)
            assert result["escalated"] is False

            marker.unlink(missing_ok=True)
            result = fn(observation_count=3, marker_path=marker)
            assert result["escalated"] is True
            assert marker.exists()


def test_marker_file_content_is_nonempty():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        fn(observation_count=5, marker_path=marker)
        assert marker.exists()
        assert len(marker.read_text()) > 0


def test_result_contains_threshold_key():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        result = fn(observation_count=1, marker_path=marker)
        assert "threshold" in result


def test_result_contains_observation_count():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        result = fn(observation_count=3, marker_path=marker)
        assert result.get("observation_count") == 3


def test_warn_log_emitted_on_escalation(caplog):
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING):
            fn(observation_count=5, marker_path=marker)
        assert any("chain_dead_locked" in r.message for r in caplog.records)


def test_no_warn_log_below_threshold(caplog):
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING):
            fn(observation_count=4, marker_path=marker)
        chain_dead_locked_logs = [
            r for r in caplog.records if "chain_dead_locked" in r.message
        ]
        assert len(chain_dead_locked_logs) == 0


def test_marker_parent_created_if_missing():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        nested_marker = Path(tmpdir) / "bob4" / "tools" / "STALL_ATTENTION.txt"
        fn(observation_count=5, marker_path=nested_marker)
        assert nested_marker.exists()


def test_env_threshold_invalid_value_uses_default():
    fn = watchdog_must_escalate_repeated_spec_gate_stall_observed
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "not_a_number"}):
            result = fn(observation_count=4, marker_path=marker)
            assert result["escalated"] is False

            marker.unlink(missing_ok=True)
            result = fn(observation_count=5, marker_path=marker)
            assert result["escalated"] is True
