"""Tests for BF-8 Part A — context_budget PreToolUse hook.

Covers:
  - check_context_usage: token counting from JSONL transcripts
  - emit_telemetry: CTX_BUDGET_KILL events to .bob3/events.jsonl
  - main(): full hook entry point with stdin/stdout protocol
  - _estimate_tokens_from_transcript: char-based fallback
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

# Load the hook module directly from .claude/hooks/context_budget.py
_HOOK_PATH = Path(__file__).parents[1] / ".claude" / "hooks" / "context_budget.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("context_budget", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cb = _load_hook()


# ---------------------------------------------------------------------------
# check_context_usage — basic functionality
# ---------------------------------------------------------------------------


def test_check_context_usage_with_usage_metadata(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        json.dumps({"usage": {"input_tokens": 50_000, "output_tokens": 10_000}}) + "\n"
    )
    result = cb.check_context_usage(str(p))
    assert result["tokens_used"] == 60_000
    assert result["limit"] == 200_000
    assert result["fraction"] == pytest.approx(60_000 / 200_000, rel=1e-6)
    assert result["over_budget"] is False


def test_check_context_usage_over_budget(tmp_path):
    p = tmp_path / "transcript.jsonl"
    # 130k tokens → 65% of 200k window → over budget
    p.write_text(
        json.dumps({"usage": {"input_tokens": 120_000, "output_tokens": 10_000}}) + "\n"
    )
    result = cb.check_context_usage(str(p))
    assert result["over_budget"] is True
    assert result["fraction"] >= 0.60


def test_check_context_usage_exactly_at_threshold(tmp_path):
    p = tmp_path / "transcript.jsonl"
    # 60% of 200k = 120k → exactly at threshold → over_budget True
    p.write_text(
        json.dumps({"usage": {"input_tokens": 112_000, "output_tokens": 8_000}}) + "\n"
    )
    result = cb.check_context_usage(str(p))
    assert result["tokens_used"] == 120_000
    assert result["over_budget"] is True


def test_check_context_usage_fallback_to_char_count(tmp_path):
    p = tmp_path / "transcript.jsonl"
    # No usage metadata — falls back to char count // 4
    line = '{"content": "' + ("A" * 400) + '"}'
    p.write_text(line + "\n")
    result = cb.check_context_usage(str(p))
    # Char-based: len(line) // 4  (at least 100 tokens)
    assert result["tokens_used"] > 0
    assert isinstance(result["over_budget"], bool)


def test_check_context_usage_multiple_entries(tmp_path):
    p = tmp_path / "transcript.jsonl"
    lines = [
        json.dumps({"usage": {"input_tokens": 10_000, "output_tokens": 2_000}}),
        json.dumps({"usage": {"input_tokens": 30_000, "output_tokens": 5_000}}),
    ]
    p.write_text("\n".join(lines) + "\n")
    result = cb.check_context_usage(str(p))
    assert result["tokens_used"] == 47_000


def test_check_context_usage_custom_threshold(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        json.dumps({"usage": {"input_tokens": 50_000, "output_tokens": 0}}) + "\n"
    )
    # At 40% threshold: 50k/200k = 25% → NOT over budget
    result_40 = cb.check_context_usage(str(p), threshold=0.40)
    assert result_40["over_budget"] is False

    # At 20% threshold: 25% > 20% → over budget
    result_20 = cb.check_context_usage(str(p), threshold=0.20)
    assert result_20["over_budget"] is True


def test_check_context_usage_known_model(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        json.dumps({"usage": {"input_tokens": 10_000, "output_tokens": 0}}) + "\n"
    )
    result = cb.check_context_usage(str(p), model="claude-sonnet-4-5-20250929")
    assert result["limit"] == 200_000


def test_check_context_usage_unknown_model_uses_default(tmp_path):
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        json.dumps({"usage": {"input_tokens": 10_000, "output_tokens": 0}}) + "\n"
    )
    result = cb.check_context_usage(str(p), model="future-claude-9000")
    assert result["limit"] == 200_000


# ---------------------------------------------------------------------------
# emit_telemetry
# ---------------------------------------------------------------------------


def test_emit_telemetry_creates_events_jsonl(tmp_path):
    cb.emit_telemetry(
        event="CTX_BUDGET_KILL",
        feature_id="feat-abc",
        tokens=130_000,
        limit=200_000,
        workspace=str(tmp_path),
    )
    events_path = tmp_path / ".bob3" / "events.jsonl"
    assert events_path.exists()
    record = json.loads(events_path.read_text().strip())
    assert record["event"] == "CTX_BUDGET_KILL"
    assert record["feature_id"] == "feat-abc"
    assert record["tokens"] == 130_000
    assert record["limit"] == 200_000
    assert "timestamp" in record


def test_emit_telemetry_appends_multiple_events(tmp_path):
    for i in range(3):
        cb.emit_telemetry(
            event="CTX_BUDGET_KILL",
            feature_id=f"feat-{i}",
            tokens=100_000 + i,
            limit=200_000,
            workspace=str(tmp_path),
        )
    events_path = tmp_path / ".bob3" / "events.jsonl"
    lines = [l for l in events_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 3
    ids = [json.loads(l)["feature_id"] for l in lines]
    assert ids == ["feat-0", "feat-1", "feat-2"]


def test_emit_telemetry_none_feature_id(tmp_path):
    cb.emit_telemetry(
        event="CTX_BUDGET_KILL",
        feature_id=None,
        tokens=100_000,
        limit=200_000,
        workspace=str(tmp_path),
    )
    events_path = tmp_path / ".bob3" / "events.jsonl"
    record = json.loads(events_path.read_text().strip())
    assert record["feature_id"] is None


# ---------------------------------------------------------------------------
# main() — full hook entry point
# ---------------------------------------------------------------------------


def test_main_continue_on_empty_stdin(capsys):
    sys.stdin = io.StringIO("")
    cb.main()
    sys.stdin = sys.__stdin__
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["decision"] == "continue"


def test_main_continue_on_invalid_json(capsys):
    sys.stdin = io.StringIO("not json at all")
    cb.main()
    sys.stdin = sys.__stdin__
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["decision"] == "continue"


def test_main_continue_when_transcript_missing(capsys):
    payload = json.dumps({
        "session_id": "sess-123",
        "transcript_path": "/no/such/file.jsonl",
        "tool_name": "Bash",
        "tool_input": {},
    })
    sys.stdin = io.StringIO(payload)
    cb.main()
    sys.stdin = sys.__stdin__
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["decision"] == "continue"


def test_main_block_when_over_budget(tmp_path, capsys, monkeypatch):
    # Write a transcript at >60% usage
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"usage": {"input_tokens": 150_000, "output_tokens": 10_000}}) + "\n"
    )
    monkeypatch.setenv("BOB3_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("BOB3_FEATURE_ID", "feat-xyz")
    payload = json.dumps({
        "session_id": "sess-abc",
        "transcript_path": str(transcript),
        "tool_name": "Bash",
        "tool_input": {},
    })
    sys.stdin = io.StringIO(payload)
    cb.main()
    sys.stdin = sys.__stdin__
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["decision"] == "block"
    assert "context-budget-exceeded" in result["reason"]


def test_main_continue_when_under_budget(tmp_path, capsys, monkeypatch):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"usage": {"input_tokens": 10_000, "output_tokens": 5_000}}) + "\n"
    )
    monkeypatch.setenv("BOB3_WORKSPACE", str(tmp_path))
    payload = json.dumps({
        "session_id": "sess-abc",
        "transcript_path": str(transcript),
        "tool_name": "Bash",
        "tool_input": {},
    })
    sys.stdin = io.StringIO(payload)
    cb.main()
    sys.stdin = sys.__stdin__
    out = capsys.readouterr().out
    result = json.loads(out)
    assert result["decision"] == "continue"


def test_main_emits_telemetry_on_block(tmp_path, capsys, monkeypatch):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"usage": {"input_tokens": 150_000, "output_tokens": 20_000}}) + "\n"
    )
    monkeypatch.setenv("BOB3_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("BOB3_FEATURE_ID", "feat-telemetry-test")
    payload = json.dumps({
        "session_id": "sess-tel",
        "transcript_path": str(transcript),
    })
    sys.stdin = io.StringIO(payload)
    cb.main()
    sys.stdin = sys.__stdin__
    events_path = tmp_path / ".bob3" / "events.jsonl"
    assert events_path.exists()
    record = json.loads(events_path.read_text().strip())
    assert record["event"] == "CTX_BUDGET_KILL"
    assert record["feature_id"] == "feat-telemetry-test"


# ---------------------------------------------------------------------------
# CONTEXT_BUDGET_THRESHOLD constant
# ---------------------------------------------------------------------------


def test_context_budget_threshold_is_0_60():
    assert cb.CONTEXT_BUDGET_THRESHOLD == pytest.approx(0.60)
