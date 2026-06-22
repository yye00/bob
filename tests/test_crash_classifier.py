"""Tests for F-R6-300: sub-agent crash classifier.

The classifier distinguishes three sub-agent termination modes from
real on-disk evidence:

* ``spawn_failure`` — the sub-agent died before doing any work. Safe
  to retry without charging a refinement attempt.
* ``mid_work_crash`` — the sub-agent did work (tool calls, progress
  events) and then crashed. MUST charge a refinement attempt, otherwise
  the orchestrator loops forever on a buggy spec (F-R5-202 regression).
* ``clean_exit`` — exit_code == 0; counted as a real attempt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bob3.orchestrator.crash_classifier import (
    ClassificationResult,
    classify_sub_agent_exit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, events: list[dict]) -> None:
    """Write ``events`` (one JSON object per line) to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def _progress_work_event(feature_id: str = "F042") -> dict:
    """Return a canonical ``progress_updated`` event."""
    return {
        "timestamp": "2026-05-19T12:00:00+00:00",
        "event_type": "progress_updated",
        "project_id": "",
        "feature_id": feature_id,
        "attempt_number": 1,
        "payload": {"feature_name": "Test", "outcome": "in_progress"},
    }


# ---------------------------------------------------------------------------
# Acceptance criteria tests
# ---------------------------------------------------------------------------


class TestRealSpawnFailure:
    """A genuine spawn-time failure: no progress.jsonl, no tool calls,
    SDK reports zero duration and zero turns, exit_code != 0."""

    def test_no_progress_file_no_tool_calls_classified_as_spawn_failure(
        self, tmp_path: Path
    ) -> None:
        progress_path = tmp_path / "progress.jsonl"  # never created
        session_path = tmp_path / "session.log"  # never created

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(progress_path),
            session_log_path=str(session_path),
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail="Command failed with exit code 1",
        )

        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False
        assert "progress_jsonl=missing" in result["evidence"]

    def test_empty_progress_file_still_spawn_failure(
        self, tmp_path: Path
    ) -> None:
        """An empty progress.jsonl (sub-agent created the file but never
        wrote anything) is still a spawn-time failure."""
        progress_path = tmp_path / "progress.jsonl"
        progress_path.write_text("")  # zero events

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(progress_path),
            session_log_path=None,
            duration_ms=15,
            num_turns=0,
            exit_code=1,
            stderr_tail=None,
        )

        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False


class TestMidWorkCrash:
    """The bug being fixed: the sub-agent produced real work (tool
    calls or progress events) and then died with a non-zero exit
    code. Must NOT be free-retried."""

    def test_progress_jsonl_with_work_events_is_mid_work_crash(
        self, tmp_path: Path
    ) -> None:
        progress_path = tmp_path / "progress.jsonl"
        _write_jsonl(
            progress_path,
            [
                _progress_work_event(),
                _progress_work_event(),
                _progress_work_event(),
            ],
        )

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(progress_path),
            session_log_path=None,
            # The bug signature: SDK reports nothing even though the
            # sub-agent clearly ran.
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=(
                "Fatal error in message reader: "
                "Command failed with exit code 1"
            ),
        )

        assert result["kind"] == "mid_work_crash"
        assert result["should_charge_attempt"] is True
        assert "progress_jsonl.work_events=3" in result["evidence"]

    def test_session_log_tool_calls_promote_to_mid_work_crash(
        self, tmp_path: Path
    ) -> None:
        """progress.jsonl missing, but session log proves tool calls
        happened. Must still be mid_work_crash."""
        session_path = tmp_path / "session.log"
        session_path.write_text(
            'assistant: {"type":"tool_use","name":"Write","input":{}}\n'
            "tool_result: ok\n"
        )

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(tmp_path / "nope.jsonl"),
            session_log_path=str(session_path),
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail="Fatal error in message reader",
        )

        assert result["kind"] == "mid_work_crash"
        assert result["should_charge_attempt"] is True
        assert "session_log.tool_calls=yes" in result["evidence"]

    def test_real_turns_and_duration_is_mid_work_crash(
        self, tmp_path: Path
    ) -> None:
        """When the SDK DOES report turns/duration honestly, that alone
        is enough to classify as mid_work_crash."""
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=120_000,
            num_turns=12,
            exit_code=1,
            stderr_tail="Compilation error in main.py",
        )

        assert result["kind"] == "mid_work_crash"
        assert result["should_charge_attempt"] is True


class TestCleanExit:
    def test_exit_code_zero_is_clean_exit(self, tmp_path: Path) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=45_000,
            num_turns=8,
            exit_code=0,
            stderr_tail=None,
        )

        assert result["kind"] == "clean_exit"
        assert result["should_charge_attempt"] is True

    def test_clean_exit_with_progress_events_still_clean(
        self, tmp_path: Path
    ) -> None:
        progress_path = tmp_path / "progress.jsonl"
        _write_jsonl(progress_path, [_progress_work_event()])

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(progress_path),
            session_log_path=None,
            duration_ms=30_000,
            num_turns=5,
            exit_code=0,
            stderr_tail="",
        )

        assert result["kind"] == "clean_exit"
        assert result["should_charge_attempt"] is True


class TestMissingFilesAreHandledGracefully:
    """The classifier must NEVER raise on missing / unreadable inputs.
    A sub-agent that died before flushing its log is exactly the case
    we need to handle."""

    def test_none_paths_do_not_raise(self) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=None,
        )
        assert result["kind"] == "spawn_failure"

    def test_nonexistent_paths_do_not_raise(self, tmp_path: Path) -> None:
        result = classify_sub_agent_exit(
            progress_jsonl_path=str(tmp_path / "ghost.jsonl"),
            session_log_path=str(tmp_path / "ghost.log"),
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=None,
        )
        assert result["kind"] == "spawn_failure"

    def test_malformed_jsonl_lines_are_skipped(self, tmp_path: Path) -> None:
        """Truncated last line (sub-agent crashed mid-write) must not
        crash the classifier; complete lines should still count."""
        progress_path = tmp_path / "progress.jsonl"
        complete = json.dumps(_progress_work_event())
        progress_path.write_text(
            complete
            + "\n"
            + "not-json-at-all\n"
            + '{"event_type": "progress_updat'  # truncated
        )

        result = classify_sub_agent_exit(
            progress_jsonl_path=str(progress_path),
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=1,
            stderr_tail=None,
        )
        # The one complete work event is enough to flip the verdict.
        assert result["kind"] == "mid_work_crash"
        assert result["should_charge_attempt"] is True

    def test_none_exit_code_treated_as_error(self, tmp_path: Path) -> None:
        """``exit_code=None`` (killed by signal, no status captured)
        must not be misread as a clean exit."""
        result = classify_sub_agent_exit(
            progress_jsonl_path=None,
            session_log_path=None,
            duration_ms=0,
            num_turns=0,
            exit_code=None,
            stderr_tail=None,
        )
        assert result["kind"] == "spawn_failure"
        assert result["should_charge_attempt"] is False


# ---------------------------------------------------------------------------
# Result shape contract
# ---------------------------------------------------------------------------


def test_result_shape_matches_typed_dict() -> None:
    """The function's return type must include all three required keys
    with values of the documented types."""
    result: ClassificationResult = classify_sub_agent_exit(
        progress_jsonl_path=None,
        session_log_path=None,
        duration_ms=0,
        num_turns=0,
        exit_code=1,
        stderr_tail=None,
    )

    assert set(result.keys()) == {"kind", "evidence", "should_charge_attempt"}
    assert result["kind"] in {"spawn_failure", "mid_work_crash", "clean_exit"}
    assert isinstance(result["evidence"], str)
    assert isinstance(result["should_charge_attempt"], bool)


@pytest.mark.parametrize(
    ("exit_code", "expected_charge"),
    [
        (0, True),  # clean_exit
        (1, False),  # spawn_failure (no evidence)
    ],
)
def test_should_charge_attempt_matches_kind(
    exit_code: int, expected_charge: bool
) -> None:
    result = classify_sub_agent_exit(
        progress_jsonl_path=None,
        session_log_path=None,
        duration_ms=0,
        num_turns=0,
        exit_code=exit_code,
        stderr_tail=None,
    )
    assert result["should_charge_attempt"] is expected_charge
