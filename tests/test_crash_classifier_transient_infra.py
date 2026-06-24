"""Tests for F-R6-315: AMD gateway deprecated-key advisory treated as transient.

The AMD Vertex gateway returns HTTP 400 with an informational advisory
about shared/deprecated API keys. claude-code surfaces this as a fatal
exit (exit_code=1, duration_ms=0, num_turns=0), but the gateway continues
serving traffic, so it must be classified as a free-retry ``spawn_failure``
instead of a ``mid_work_crash``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob.orchestrator.crash_classifier import (
    _has_transient_infra_signature,
    classify_sub_agent_exit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def _work_event() -> dict:
    return {
        "timestamp": "2026-05-20T12:00:00+00:00",
        "event_type": "progress_updated",
        "project_id": "",
        "feature_id": "1cb15253",
        "attempt_number": 1,
        "payload": {"feature_name": "Test", "outcome": "in_progress"},
    }


_DEPRECATED_KEY_FULL = (
    "Application 'Claude Code' (Production Restricted) is a shared API key "
    "and is being deprecated; subsequent requests will continue to work in "
    "the meantime. Please request an individual API key."
)

_DEPRECATED_KEY_TRUNCATED_FIRST_MARKER = (
    "shared API key and is being deprecated; subsequent requests will continue"
)

_DEPRECATED_KEY_TRUNCATED_SECOND_MARKER = (
    "Application 'Claude Code' (Production Restricted) is a shared API key"
)


# ---------------------------------------------------------------------------
# _has_transient_infra_signature unit tests
# ---------------------------------------------------------------------------


class TestHasTransientInfraSignature:
    def test_full_gateway_message_matches(self) -> None:
        assert _has_transient_infra_signature(_DEPRECATED_KEY_FULL) is True

    def test_first_marker_partial_match(self) -> None:
        assert _has_transient_infra_signature(_DEPRECATED_KEY_TRUNCATED_FIRST_MARKER) is True

    def test_second_marker_partial_match(self) -> None:
        assert _has_transient_infra_signature(_DEPRECATED_KEY_TRUNCATED_SECOND_MARKER) is True

    def test_unrelated_error_does_not_match(self) -> None:
        assert _has_transient_infra_signature("Command failed with exit code 1") is False

    def test_none_stderr_does_not_raise(self) -> None:
        assert _has_transient_infra_signature(None) is False

    def test_empty_stderr_does_not_raise(self) -> None:
        assert _has_transient_infra_signature("") is False

    def test_whitespace_only_stderr_does_not_match(self) -> None:
        assert _has_transient_infra_signature("   \n\t  ") is False


# ---------------------------------------------------------------------------
# classify_sub_agent_exit integration: positive match overrides mid_work_crash
# ---------------------------------------------------------------------------


class TestTransientInfraOverridesMidWorkCrash:
    """When the transient marker is present, classify as spawn_failure
    regardless of any work_events / turns / duration that would normally
    trigger mid_work_crash."""

    def test_work_events_present_but_transient_marker_overrides(
        self, tmp_path: Path
    ) -> None:
        """The bob9/1cb15253 failure mode: ~44k progress events written,
        then the deprecated-key 400 at the end. Must NOT charge attempt."""
        progress_path = tmp_path / "progress.jsonl"
        _write_jsonl(progress_path, [_work_event(), _work_event(), _work_event()])

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(progress_path),
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=_DEPRECATED_KEY_FULL,
        )

        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False
        assert "transient_infra_error=" in result["evidence"]

    def test_nonzero_turns_overridden_by_transient_marker(
        self, tmp_path: Path
    ) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=5000,
            num_turns=3,
            exit_code=1,
            stderr_tail=_DEPRECATED_KEY_FULL,
        )

        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False
        assert "transient_infra_error=" in result["evidence"]

    def test_evidence_contains_transient_infra_error_prefix(
        self, tmp_path: Path
    ) -> None:
        """Operator must be able to grep for 'transient_infra_error=' in logs."""
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=_DEPRECATED_KEY_TRUNCATED_FIRST_MARKER,
        )

        assert result["evidence"].startswith("transient_infra_error=")

    def test_truncated_first_marker_also_overrides(self, tmp_path: Path) -> None:
        """Partial truncation of gateway message must still be caught."""
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=_DEPRECATED_KEY_TRUNCATED_FIRST_MARKER,
        )

        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False

    def test_truncated_second_marker_also_overrides(self, tmp_path: Path) -> None:
        """Alternate partial truncation is also caught."""
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=_DEPRECATED_KEY_TRUNCATED_SECOND_MARKER,
        )

        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False


# ---------------------------------------------------------------------------
# Negative match: existing paths are still triggered without transient marker
# ---------------------------------------------------------------------------


class TestNegativeMatchPreservesMidWorkCrash:
    """Without the transient marker, mid_work_crash and spawn_failure paths
    behave exactly as before (no regression)."""

    def test_work_events_without_marker_is_still_mid_work_crash(
        self, tmp_path: Path
    ) -> None:
        progress_path = tmp_path / "progress.jsonl"
        _write_jsonl(progress_path, [_work_event()])

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(progress_path),
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail="Fatal error in message reader",
        )

        assert result["kind"] == "mid_work_crash"
        assert result["should_charge_attempt"] is True

    def test_turns_without_marker_is_mid_work_crash(self) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=30_000,
            num_turns=5,
            exit_code=1,
            stderr_tail="some unrelated error",
        )

        assert result["kind"] == "mid_work_crash"
        assert result["should_charge_attempt"] is True

    def test_no_work_no_marker_is_spawn_failure(self) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail="Command not found",
        )

        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False


# ---------------------------------------------------------------------------
# clean_exit is not affected by transient marker
# ---------------------------------------------------------------------------


class TestCleanExitNotAffected:
    """exit_code=0 always yields clean_exit regardless of stderr content."""

    def test_clean_exit_with_transient_marker_in_stderr(self) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=30_000,
            num_turns=5,
            exit_code=0,
            stderr_tail=_DEPRECATED_KEY_FULL,
        )

        assert result["kind"] == "clean_exit"
        assert result["should_charge_attempt"] is True

    def test_clean_exit_with_no_stderr(self) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=10_000,
            num_turns=2,
            exit_code=0,
            stderr_tail=None,
        )

        assert result["kind"] == "clean_exit"
        assert result["should_charge_attempt"] is True
