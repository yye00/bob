"""BF-8 boundary tests — empty, zero, or minimum input returns a well-defined result."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from bob.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    classify_feature_thinking,
    check_context_usage,
    emit_telemetry,
    thinking_kwargs,
)

# Load hook module directly to test its boundary cases independently
_HOOK_PATH = Path(__file__).parents[1] / ".claude" / "hooks" / "context_budget.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("context_budget", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cb = _load_hook()


# ---------------------------------------------------------------------------
# check_context_usage boundary cases
# ---------------------------------------------------------------------------


def test_empty_transcript_returns_zero_usage(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    result = cb.check_context_usage(str(p))
    assert result["tokens_used"] == 0
    assert result["fraction"] == 0.0
    assert result["over_budget"] is False


def test_nonexistent_transcript_returns_zero():
    result = cb.check_context_usage("/does/not/exist.jsonl")
    assert result["tokens_used"] == 0
    assert result["over_budget"] is False


def test_transcript_with_zero_tokens(tmp_path):
    p = tmp_path / "zero.jsonl"
    p.write_text(json.dumps({"usage": {"input_tokens": 0, "output_tokens": 0}}) + "\n")
    result = cb.check_context_usage(str(p))
    assert result["tokens_used"] == 0
    assert result["over_budget"] is False


def test_minimum_single_token(tmp_path):
    p = tmp_path / "one.jsonl"
    p.write_text(json.dumps({"usage": {"input_tokens": 1, "output_tokens": 0}}) + "\n")
    result = cb.check_context_usage(str(p))
    assert result["tokens_used"] == 1
    assert result["over_budget"] is False


def test_check_context_usage_with_none_model(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"usage": {"input_tokens": 10, "output_tokens": 5}}) + "\n")
    result = cb.check_context_usage(str(p), model=None)
    assert result["limit"] > 0
    assert result["fraction"] >= 0.0


def test_check_context_usage_with_empty_string_model(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"usage": {"input_tokens": 10, "output_tokens": 5}}) + "\n")
    result = cb.check_context_usage(str(p), model="")
    assert result["limit"] > 0


# ---------------------------------------------------------------------------
# emit_telemetry boundary cases
# ---------------------------------------------------------------------------


def test_emit_telemetry_zero_tokens(tmp_path):
    cb.emit_telemetry(
        event="CTX_BUDGET_KILL",
        feature_id="feat-zero",
        tokens=0,
        limit=200_000,
        workspace=str(tmp_path),
    )
    events_path = tmp_path / ".bob" / "events.jsonl"
    record = json.loads(events_path.read_text().strip())
    assert record["tokens"] == 0
    assert record["event"] == "CTX_BUDGET_KILL"


def test_emit_telemetry_empty_feature_id(tmp_path):
    cb.emit_telemetry(
        event="CTX_BUDGET_KILL",
        feature_id="",
        tokens=1000,
        limit=200_000,
        workspace=str(tmp_path),
    )
    events_path = tmp_path / ".bob" / "events.jsonl"
    record = json.loads(events_path.read_text().strip())
    assert record["feature_id"] == ""


# ---------------------------------------------------------------------------
# classify_feature_thinking boundary cases
# ---------------------------------------------------------------------------


def test_classify_empty_feature_name_returns_bool():
    result = classify_feature_thinking(feature_name="")
    assert isinstance(result, bool)


def test_classify_zero_files_returns_bool():
    result = classify_feature_thinking(feature_name="rename x", num_files=0)
    assert isinstance(result, bool)


def test_classify_zero_spec_quality_triggers_on():
    result = classify_feature_thinking(spec_quality=0.0, extended_thinking="auto")
    assert result is True


def test_classify_spec_quality_at_boundary_0_80():
    # spec_quality = 0.80 is at the gate: < 0.80 → ON, >= 0.80 → no signal
    below = classify_feature_thinking(spec_quality=0.799, num_files=1, retry_count=0, extended_thinking="auto")
    at = classify_feature_thinking(spec_quality=0.80, num_files=1, retry_count=0, extended_thinking="auto", feature_name="")
    assert below is True
    # at 0.80, no other signal → falls through to EXTENDED_THINKING_DEFAULT
    assert isinstance(at, bool)


def test_classify_retry_zero_does_not_force_on_alone():
    result = classify_feature_thinking(
        feature_name="neutral task",
        num_files=2,
        spec_quality=0.90,
        retry_count=0,
        extended_thinking=None,
    )
    # No signal → returns the default (could be True or False, but must be bool)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# thinking_kwargs boundary cases
# ---------------------------------------------------------------------------


def test_thinking_kwargs_enabled_has_positive_budget():
    kwargs = thinking_kwargs(True)
    assert kwargs.get("budget_tokens", 0) > 0


def test_thinking_kwargs_disabled_is_empty():
    kwargs = thinking_kwargs(False)
    assert len(kwargs) == 0
