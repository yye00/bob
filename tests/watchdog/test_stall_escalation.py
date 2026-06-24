"""Tests for bob.watchdog.stall_escalation.escalate_spec_gate_stall."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.watchdog.stall_escalation import escalate_spec_gate_stall, escalate_stall_observation


class TestEscalateSpecGateStallBasic:
    """Basic behaviour of escalate_spec_gate_stall."""

    def test_callable(self):
        assert callable(escalate_spec_gate_stall)

    def test_returns_dict(self, tmp_path):
        result = escalate_spec_gate_stall(observation_count=0, marker_path=tmp_path / "m.txt")
        assert isinstance(result, dict)

    def test_required_keys_present(self, tmp_path):
        result = escalate_spec_gate_stall(observation_count=0, marker_path=tmp_path / "m.txt")
        assert {"escalated", "threshold", "observation_count", "marker_path"} <= result.keys()

    def test_no_escalation_below_threshold(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        for count in range(0, 5):
            result = escalate_spec_gate_stall(observation_count=count, marker_path=marker)
            assert result["escalated"] is False
            assert not marker.exists()

    def test_escalation_at_default_threshold(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        result = escalate_spec_gate_stall(observation_count=5, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()

    def test_escalation_above_threshold(self, tmp_path):
        for count in [5, 6, 10, 100]:
            marker = tmp_path / f"STALL_{count}.txt"
            result = escalate_spec_gate_stall(observation_count=count, marker_path=marker)
            assert result["escalated"] is True
            assert marker.exists()

    def test_marker_content_non_empty(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        escalate_spec_gate_stall(observation_count=5, marker_path=marker)
        assert len(marker.read_text()) > 0

    def test_observation_count_reflected(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        result = escalate_spec_gate_stall(observation_count=3, marker_path=marker)
        assert result["observation_count"] == 3

    def test_threshold_default_is_5(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5

    def test_threshold_env_override(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "3"}):
            result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert result["threshold"] == 3

    def test_custom_threshold_triggers_at_n(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "2"}):
            result = escalate_spec_gate_stall(observation_count=2, marker_path=marker)
        assert result["escalated"] is True

    def test_invalid_env_falls_back_to_default(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        with patch.dict(os.environ, {"BOB_STALL_ESCALATION_COUNT": "bad"}):
            result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert result["threshold"] == 5

    def test_negative_observation_count_raises(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        with pytest.raises(ValueError):
            escalate_spec_gate_stall(observation_count=-1, marker_path=marker)

    def test_creates_parent_directories(self, tmp_path):
        marker = tmp_path / "nested" / "deep" / "STALL.txt"
        escalate_spec_gate_stall(observation_count=5, marker_path=marker)
        assert marker.exists()

    def test_marker_path_returned_absolute(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        result = escalate_spec_gate_stall(observation_count=0, marker_path=marker)
        assert Path(result["marker_path"]).is_absolute()

    def test_alias_escalate_stall_observation_identical(self, tmp_path):
        marker = tmp_path / "STALL.txt"
        r1 = escalate_spec_gate_stall(observation_count=3, marker_path=marker)
        marker2 = tmp_path / "STALL2.txt"
        r2 = escalate_stall_observation(observation_count=3, marker_path=marker2)
        assert r1["escalated"] == r2["escalated"]
        assert r1["threshold"] == r2["threshold"]
        assert r1["observation_count"] == r2["observation_count"]


class TestDefaultMarkerPath:
    """Default marker path when none is provided."""

    def test_default_path_no_exception_below_threshold(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = escalate_spec_gate_stall(observation_count=1)
        assert result["escalated"] is False

    def test_default_path_creates_file_on_escalation(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        escalate_spec_gate_stall(observation_count=5)
        assert (tmp_path / "bob4" / "tools" / "STALL_ATTENTION.txt").exists()
