"""Tests for BF-8 Part A — bob.hooks.context_budget.enforce_context_budget."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bob.hooks.context_budget import (
    CONTEXT_BUDGET_THRESHOLD,
    check_context_usage,
    enforce_context_budget,
)


# ---------------------------------------------------------------------------
# enforce_context_budget — under budget
# ---------------------------------------------------------------------------


def test_enforce_context_budget_under_budget_continues(tmp_path):
    p = tmp_path / "transcript.jsonl"
    # 30k tokens — well under 60% of 200k
    p.write_text(json.dumps({"usage": {"input_tokens": 25_000, "output_tokens": 5_000}}) + "\n")
    result = enforce_context_budget(str(p))
    assert result["decision"] == "continue"
    assert result["reason"] == ""
    assert result["metrics"]["over_budget"] is False


def test_enforce_context_budget_over_budget_blocks(tmp_path):
    p = tmp_path / "transcript.jsonl"
    # 130k tokens — over 60% of 200k
    p.write_text(json.dumps({"usage": {"input_tokens": 120_000, "output_tokens": 10_000}}) + "\n")
    result = enforce_context_budget(str(p), feature_id="test-feature-123")
    assert result["decision"] == "block"
    assert "context-budget-exceeded" in result["reason"]
    assert "test-feature-123" in result["reason"]
    assert result["metrics"]["over_budget"] is True


def test_enforce_context_budget_missing_transcript_continues(tmp_path):
    result = enforce_context_budget(str(tmp_path / "nonexistent.jsonl"))
    assert result["decision"] == "continue"


def test_enforce_context_budget_emits_telemetry_event(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("BOB_WORKSPACE", str(workspace))

    p = tmp_path / "transcript.jsonl"
    p.write_text(json.dumps({"usage": {"input_tokens": 150_000, "output_tokens": 10_000}}) + "\n")

    result = enforce_context_budget(str(p), feature_id="feat-abc", workspace=str(workspace))
    assert result["decision"] == "block"

    events_path = workspace / ".bob" / "events.jsonl"
    assert events_path.exists()
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    assert any(e["event"] == "CTX_BUDGET_KILL" for e in events)
    kill_event = next(e for e in events if e["event"] == "CTX_BUDGET_KILL")
    assert kill_event["feature_id"] == "feat-abc"
    assert kill_event["tokens"] == 160_000


def test_enforce_context_budget_custom_threshold(tmp_path):
    p = tmp_path / "transcript.jsonl"
    # 45% usage — over 40% threshold but under default 60%
    p.write_text(json.dumps({"usage": {"input_tokens": 85_000, "output_tokens": 5_000}}) + "\n")
    result_default = enforce_context_budget(str(p))
    assert result_default["decision"] == "continue"

    result_tight = enforce_context_budget(str(p), threshold=0.40)
    assert result_tight["decision"] == "block"


# ---------------------------------------------------------------------------
# check_context_usage — verify threshold constant is reasonable
# ---------------------------------------------------------------------------


def test_context_budget_threshold_is_0_60():
    assert CONTEXT_BUDGET_THRESHOLD == pytest.approx(0.60)


def test_check_context_usage_returns_fraction(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"usage": {"input_tokens": 60_000, "output_tokens": 0}}) + "\n")
    result = check_context_usage(str(p))
    assert result["fraction"] == pytest.approx(60_000 / 200_000, rel=1e-6)
    assert result["tokens_used"] == 60_000
