"""Tests for bob3.stall_escalation.

AC: File exists: src/bob3/stall_escalation.py
    Function defined: bob3.stall_escalation.escalate_stall_observation
    Function defined: bob3.stall_escalation.write_stall_attention_marker
    integration: bob3.weekend_watchdog
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bob3.stall_escalation import escalate_stall_observation, write_stall_attention_marker


class TestModuleInterface:
    """Verify that the public API matches the AC function definitions."""

    def test_escalate_stall_observation_is_callable(self):
        assert callable(escalate_stall_observation)

    def test_write_stall_attention_marker_is_callable(self):
        assert callable(write_stall_attention_marker)

    def test_module_has_all_exports(self):
        import bob3.stall_escalation as mod
        assert "escalate_stall_observation" in mod.__all__
        assert "write_stall_attention_marker" in mod.__all__


class TestEscalateStallObservation:
    """Core behavior of escalate_stall_observation."""

    def test_below_threshold_returns_escalated_false(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=4, marker_path=marker)
        assert result["escalated"] is False

    def test_at_threshold_returns_escalated_true(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=5, marker_path=marker)
        assert result["escalated"] is True

    def test_above_threshold_returns_escalated_true(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=10, marker_path=marker)
        assert result["escalated"] is True

    def test_escalation_writes_marker_file(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_stall_observation(observation_count=5, marker_path=marker)
        assert marker.exists()

    def test_no_escalation_does_not_write_marker_file(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_stall_observation(observation_count=4, marker_path=marker)
        assert not marker.exists()

    def test_marker_file_content_contains_chain_dead_locked(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        escalate_stall_observation(observation_count=5, marker_path=marker)
        content = marker.read_text()
        assert "chain_dead_locked" in content

    def test_result_contains_required_keys(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert "escalated" in result
        assert "threshold" in result
        assert "observation_count" in result
        assert "marker_path" in result

    def test_result_observation_count_matches_input(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=3, marker_path=marker)
        assert result["observation_count"] == 3

    def test_default_threshold_is_5(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5

    def test_env_override_threshold(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_stall_observation(observation_count=3, marker_path=marker)
        assert result["escalated"] is True
        assert result["threshold"] == 3

    def test_negative_count_raises_value_error(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with pytest.raises(ValueError):
            escalate_stall_observation(observation_count=-1, marker_path=marker)

    def test_marker_path_created_with_parent_dirs(self, tmp_path):
        marker = tmp_path / "nested" / "deep" / "STALL_ATTENTION.txt"
        escalate_stall_observation(observation_count=5, marker_path=marker)
        assert marker.exists()

    def test_result_marker_path_is_absolute(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = escalate_stall_observation(observation_count=0, marker_path=marker)
        assert Path(result["marker_path"]).is_absolute()

    def test_escalation_logs_warn(self, tmp_path, caplog):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING, logger="bob3.stall_escalation"):
            escalate_stall_observation(observation_count=5, marker_path=marker)
        assert any("chain_dead_locked" in r.message for r in caplog.records)


class TestWriteStallAttentionMarker:
    """Core behavior of write_stall_attention_marker."""

    def test_creates_marker_file(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        write_stall_attention_marker(marker, observation_count=5)
        assert marker.exists()

    def test_marker_content_contains_chain_dead_locked(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        write_stall_attention_marker(marker, observation_count=5)
        content = marker.read_text()
        assert "chain_dead_locked" in content

    def test_marker_content_includes_observation_count(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        write_stall_attention_marker(marker, observation_count=7)
        content = marker.read_text()
        assert "7" in content

    def test_creates_parent_directories(self, tmp_path):
        marker = tmp_path / "subdir" / "STALL_ATTENTION.txt"
        write_stall_attention_marker(marker, observation_count=5)
        assert marker.exists()

    def test_custom_threshold_reflected_in_content(self, tmp_path):
        marker = tmp_path / "STALL_ATTENTION.txt"
        write_stall_attention_marker(marker, observation_count=5, threshold=3)
        content = marker.read_text()
        assert "threshold=3" in content

    def test_logs_warn_event(self, tmp_path, caplog):
        marker = tmp_path / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING, logger="bob3.stall_escalation"):
            write_stall_attention_marker(marker, observation_count=5)
        assert any("chain_dead_locked" in r.message for r in caplog.records)


class TestWeekendWatchdogIntegration:
    """Verify bob3.weekend_watchdog re-exports the stall escalation functions."""

    def test_weekend_watchdog_exports_escalate_stall_observation(self):
        from bob3.weekend_watchdog import escalate_stall_observation as fn
        assert callable(fn)

    def test_weekend_watchdog_exports_write_stall_attention_marker(self):
        from bob3.weekend_watchdog import write_stall_attention_marker as fn
        assert callable(fn)

    def test_weekend_watchdog_escalate_stall_observation_works(self, tmp_path):
        from bob3.weekend_watchdog import escalate_stall_observation as fn
        marker = tmp_path / "STALL_ATTENTION.txt"
        result = fn(observation_count=5, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_weekend_watchdog_write_marker_works(self, tmp_path):
        from bob3.weekend_watchdog import write_stall_attention_marker as fn
        marker = tmp_path / "STALL_ATTENTION.txt"
        fn(marker, observation_count=5)
        assert marker.exists()
