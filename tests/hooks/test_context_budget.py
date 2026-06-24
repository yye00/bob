"""Tests for .claude/hooks/context_budget.py (BF-8 Part A)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Load context_budget from the non-package .claude/hooks/ path
_HOOK_PATH = Path(__file__).parents[2] / ".claude" / "hooks" / "context_budget.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("context_budget", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cb = _load_module()


# ---------------------------------------------------------------------------
# check_context_usage
# ---------------------------------------------------------------------------


def _make_transcript(lines: list[dict], tmp_path: Path) -> Path:
    p = tmp_path / "transcript.jsonl"
    with p.open("w") as fh:
        for rec in lines:
            fh.write(json.dumps(rec) + "\n")
    return p


def test_check_context_usage_under_budget(tmp_path):
    p = _make_transcript([
        {"usage": {"input_tokens": 50_000, "output_tokens": 10_000}}
    ], tmp_path)
    result = cb.check_context_usage(str(p), model="default", threshold=0.60)
    assert result["tokens_used"] == 60_000
    assert result["limit"] == 200_000
    assert result["fraction"] == pytest.approx(0.30, rel=1e-3)
    assert result["over_budget"] is False


def test_check_context_usage_over_budget(tmp_path):
    p = _make_transcript([
        {"usage": {"input_tokens": 100_000, "output_tokens": 30_000}}
    ], tmp_path)
    result = cb.check_context_usage(str(p), model="default", threshold=0.60)
    assert result["tokens_used"] == 130_000
    assert result["over_budget"] is True


def test_check_context_usage_exactly_at_threshold(tmp_path):
    # 60% of 200_000 = 120_000 — should trigger over_budget
    p = _make_transcript([
        {"usage": {"input_tokens": 100_000, "output_tokens": 20_000}}
    ], tmp_path)
    result = cb.check_context_usage(str(p), model="default", threshold=0.60)
    assert result["tokens_used"] == 120_000
    assert result["over_budget"] is True


def test_check_context_usage_no_usage_field_fallback(tmp_path):
    # Transcript has no usage field — falls back to char-count heuristic.
    p = tmp_path / "transcript.jsonl"
    text = json.dumps({"role": "assistant", "content": "x" * 800})
    p.write_text(text + "\n")
    result = cb.check_context_usage(str(p), threshold=0.60)
    # char_count // 4 should be 200 tokens; well under budget
    assert result["tokens_used"] > 0
    assert result["over_budget"] is False


def test_check_context_usage_missing_file():
    result = cb.check_context_usage("/nonexistent/path.jsonl", threshold=0.60)
    assert result["tokens_used"] == 0
    assert result["over_budget"] is False


def test_check_context_usage_multiple_messages(tmp_path):
    p = _make_transcript([
        {"usage": {"input_tokens": 40_000, "output_tokens": 10_000}},
        {"usage": {"input_tokens": 30_000, "output_tokens": 10_000}},
    ], tmp_path)
    result = cb.check_context_usage(str(p), threshold=0.60)
    assert result["tokens_used"] == 90_000


# ---------------------------------------------------------------------------
# emit_telemetry
# ---------------------------------------------------------------------------


def test_emit_telemetry_creates_events_file(tmp_path):
    cb.emit_telemetry(
        event="CTX_BUDGET_KILL",
        feature_id="test-feature-123",
        tokens=130_000,
        limit=200_000,
        workspace=str(tmp_path),
    )
    events_path = tmp_path / ".bob" / "events.jsonl"
    assert events_path.exists()
    record = json.loads(events_path.read_text().strip())
    assert record["event"] == "CTX_BUDGET_KILL"
    assert record["feature_id"] == "test-feature-123"
    assert record["tokens"] == 130_000
    assert record["limit"] == 200_000
    assert "timestamp" in record


def test_emit_telemetry_appends_multiple_events(tmp_path):
    for i in range(3):
        cb.emit_telemetry(
            event="CTX_BUDGET_KILL",
            feature_id=f"feat-{i}",
            tokens=i * 10_000,
            limit=200_000,
            workspace=str(tmp_path),
        )
    events_path = tmp_path / ".bob" / "events.jsonl"
    lines = events_path.read_text().strip().splitlines()
    assert len(lines) == 3
    for i, line in enumerate(lines):
        rec = json.loads(line)
        assert rec["feature_id"] == f"feat-{i}"


def test_emit_telemetry_none_feature_id(tmp_path):
    cb.emit_telemetry(
        event="CTX_BUDGET_KILL",
        feature_id=None,
        tokens=100,
        limit=200_000,
        workspace=str(tmp_path),
    )
    events_path = tmp_path / ".bob" / "events.jsonl"
    record = json.loads(events_path.read_text().strip())
    assert record["feature_id"] is None


# ---------------------------------------------------------------------------
# main (PreToolUse hook entry point)
# ---------------------------------------------------------------------------


def test_main_continue_on_empty_stdin(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    cb.main()
    out = capsys.readouterr().out
    assert json.loads(out)["decision"] == "continue"


def test_main_continue_when_under_budget(tmp_path, capsys, monkeypatch):
    p = _make_transcript([
        {"usage": {"input_tokens": 10_000, "output_tokens": 5_000}}
    ], tmp_path)
    payload = json.dumps({
        "session_id": "sess-abc",
        "transcript_path": str(p),
        "tool_name": "Bash",
        "tool_input": {},
    })
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    cb.main()
    out = capsys.readouterr().out
    assert json.loads(out)["decision"] == "continue"


def test_main_block_when_over_budget(tmp_path, capsys, monkeypatch):
    p = _make_transcript([
        {"usage": {"input_tokens": 150_000, "output_tokens": 50_000}}
    ], tmp_path)
    payload = json.dumps({
        "session_id": "sess-xyz",
        "transcript_path": str(p),
        "tool_name": "Read",
        "tool_input": {},
    })
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    monkeypatch.setenv("BOB_WORKSPACE", str(tmp_path))
    cb.main()
    out = capsys.readouterr().out
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "context-budget-exceeded" in decision["reason"]


def test_main_block_emits_telemetry(tmp_path, capsys, monkeypatch):
    p = _make_transcript([
        {"usage": {"input_tokens": 150_000, "output_tokens": 50_000}}
    ], tmp_path)
    payload = json.dumps({
        "session_id": "sess-telem",
        "transcript_path": str(p),
        "tool_name": "Read",
        "tool_input": {},
    })
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    monkeypatch.setenv("BOB_WORKSPACE", str(tmp_path))
    cb.main()
    events_path = tmp_path / ".bob" / "events.jsonl"
    assert events_path.exists()
    record = json.loads(events_path.read_text().strip())
    assert record["event"] == "CTX_BUDGET_KILL"


def test_main_continue_on_bad_json(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not-valid-json"))
    cb.main()
    out = capsys.readouterr().out
    assert json.loads(out)["decision"] == "continue"


def test_main_continue_on_missing_transcript_path(capsys, monkeypatch):
    payload = json.dumps({
        "session_id": "sess-no-path",
        "transcript_path": "",
        "tool_name": "Bash",
        "tool_input": {},
    })
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    cb.main()
    out = capsys.readouterr().out
    assert json.loads(out)["decision"] == "continue"
