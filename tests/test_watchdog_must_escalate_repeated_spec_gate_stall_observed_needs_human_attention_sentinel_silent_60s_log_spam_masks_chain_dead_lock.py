"""Tests for watchdog escalation of repeated spec_gate_stall_observed events.

Feature 1c71893f-b668-47f0-8f62-8e4d05b5f1b9

The watchdog must escalate spec_gate_stall_observed to a
needs_human_attention sentinel after N consecutive observations
(default 5, configurable via BOB3_STALL_ESCALATION_COUNT).

Escalation:
 - Writes a HALT_ATTENTION marker file (bob4/tools/STALL_ATTENTION.txt)
 - Logs a chain_dead_locked event at WARN level

AC:
 - Function defined: bob3.watchdog_must_escalate_...watchdog_must_escalate_...
 - pytest: tests/test_watchdog_must_escalate_...::test_watchdog_must_escalate_...
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_MOD = "bob3.watchdog_must_escalate_repeated_spec_gate_stall_observed_needs_human_attention_sentinel_silent_60s_log_spam_masks_chain_dead_lock"
_FUNC = "watchdog_must_escalate_repeated_spec_gate_stall_observed_needs_human_attention_sentinel_silent_60s_log_spam_masks_chain_dead_lock"


def _import_func():
    import importlib
    mod = importlib.import_module(_MOD)
    return getattr(mod, _FUNC)


# ---------------------------------------------------------------------------
# AC smoke test — the one AC-named test that must pass
# ---------------------------------------------------------------------------


def test_watchdog_must_escalate_repeated_spec_gate_stall_observed_needs_human_attention_sentinel_silent_60s_log_spam_masks_chain_dead_lock():
    """Main AC test: function is importable and callable; escalates after threshold."""
    fn = _import_func()
    assert callable(fn)

    with tempfile.TemporaryDirectory() as tmpdir:
        marker_file = Path(tmpdir) / "STALL_ATTENTION.txt"

        # 4 observations below threshold (default 5) — no escalation
        for i in range(1, 5):
            result = fn(
                observation_count=i,
                marker_path=marker_file,
            )
            assert result["escalated"] is False, f"Should not escalate at count={i}"
            assert not marker_file.exists(), f"Marker must not exist at count={i}"

        # 5th observation — must escalate
        result = fn(
            observation_count=5,
            marker_path=marker_file,
        )
        assert result["escalated"] is True
        assert marker_file.exists(), "Marker file must be written on escalation"
        content = marker_file.read_text()
        assert "chain_dead_locked" in content or "STALL" in content or len(content) > 0


# ---------------------------------------------------------------------------
# Additional behavioral tests
# ---------------------------------------------------------------------------


def test_import_is_possible():
    fn = _import_func()
    assert fn is not None


def test_no_escalation_below_threshold():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        for count in range(1, 5):
            result = fn(observation_count=count, marker_path=marker)
            assert result["escalated"] is False
            assert not marker.exists()


def test_escalation_at_default_threshold():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        result = fn(observation_count=5, marker_path=marker)
        assert result["escalated"] is True
        assert marker.exists()


def test_escalation_above_threshold():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        for count in [5, 6, 10, 100]:
            marker.unlink(missing_ok=True)
            result = fn(observation_count=count, marker_path=marker)
            assert result["escalated"] is True
            assert marker.exists()


def test_escalation_count_env_override():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"

        with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "3"}):
            # count=2 below env threshold of 3 — no escalation
            result = fn(observation_count=2, marker_path=marker)
            assert result["escalated"] is False

            # count=3 at env threshold — escalate
            marker.unlink(missing_ok=True)
            result = fn(observation_count=3, marker_path=marker)
            assert result["escalated"] is True
            assert marker.exists()


def test_marker_file_content_is_nonempty():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        fn(observation_count=5, marker_path=marker)
        assert marker.exists()
        assert len(marker.read_text()) > 0


def test_result_contains_threshold_key():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        result = fn(observation_count=1, marker_path=marker)
        assert "threshold" in result


def test_result_contains_observation_count():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        result = fn(observation_count=3, marker_path=marker)
        assert result.get("observation_count") == 3


def test_warn_log_emitted_on_escalation(caplog):
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING):
            fn(observation_count=5, marker_path=marker)
        assert any("chain_dead_locked" in r.message for r in caplog.records), (
            "Expected a WARN log containing 'chain_dead_locked'"
        )


def test_no_warn_log_below_threshold(caplog):
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        with caplog.at_level(logging.WARNING):
            fn(observation_count=4, marker_path=marker)
        chain_dead_locked_logs = [
            r for r in caplog.records if "chain_dead_locked" in r.message
        ]
        assert len(chain_dead_locked_logs) == 0


def test_marker_parent_created_if_missing():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        nested_marker = Path(tmpdir) / "bob4" / "tools" / "STALL_ATTENTION.txt"
        fn(observation_count=5, marker_path=nested_marker)
        assert nested_marker.exists()


def test_env_threshold_invalid_value_uses_default():
    fn = _import_func()
    with tempfile.TemporaryDirectory() as tmpdir:
        marker = Path(tmpdir) / "STALL_ATTENTION.txt"
        with patch.dict(os.environ, {"BOB3_STALL_ESCALATION_COUNT": "not_a_number"}):
            # Default is 5; count=4 should not escalate
            result = fn(observation_count=4, marker_path=marker)
            assert result["escalated"] is False

            marker.unlink(missing_ok=True)
            result = fn(observation_count=5, marker_path=marker)
            assert result["escalated"] is True
