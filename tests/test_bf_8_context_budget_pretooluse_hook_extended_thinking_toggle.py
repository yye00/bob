"""Tests for BF-8: Context-budget PreToolUse hook + extended_thinking toggle.

Verifies:
  - Part A: context_budget hook module is importable and functional
  - Part B: extended_thinking classifier and toggle functions work correctly
  - Integration: bob.orchestrator.run_loop is importable
  - Sentinel function: bf_8_context_budget_pretooluse_hook_extended_thinking_toggle
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from bob.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    CONTEXT_BUDGET_THRESHOLD,
    EXTENDED_THINKING_DEFAULT,
    bf_8_context_budget_pretooluse_hook_extended_thinking_toggle,
    check_context_usage,
    classify_feature_thinking,
    emit_telemetry,
    get_extended_thinking_setting,
    thinking_kwargs,
)


# ---------------------------------------------------------------------------
# Sentinel function (primary AC)
# ---------------------------------------------------------------------------


def test_bf_8_context_budget_pretooluse_hook_extended_thinking_toggle():
    """Primary AC test — sentinel function must return the feature identifier."""
    result = bf_8_context_budget_pretooluse_hook_extended_thinking_toggle()
    assert result == "BF-8"


# ---------------------------------------------------------------------------
# Part A — context-budget hook
# ---------------------------------------------------------------------------


def test_context_budget_threshold_is_sixty_percent():
    assert CONTEXT_BUDGET_THRESHOLD == 0.60


def test_check_context_usage_within_budget(tmp_path):
    p = tmp_path / "small.jsonl"
    # Write usage well within budget (1% of 200k = 2000 tokens)
    p.write_text(json.dumps({"usage": {"input_tokens": 1000, "output_tokens": 500}}) + "\n")
    result = check_context_usage(str(p))
    assert result["over_budget"] is False
    assert result["tokens_used"] == 1500
    assert result["fraction"] < 0.60


def test_check_context_usage_over_budget(tmp_path):
    p = tmp_path / "big.jsonl"
    # 130k tokens out of 200k = 65% > 60% threshold
    p.write_text(
        json.dumps({"usage": {"input_tokens": 120_000, "output_tokens": 10_000}}) + "\n"
    )
    result = check_context_usage(str(p))
    assert result["over_budget"] is True
    assert result["tokens_used"] == 130_000
    assert result["fraction"] > 0.60


def test_check_context_usage_at_exact_threshold(tmp_path):
    p = tmp_path / "boundary.jsonl"
    # Exactly 60% of 200k = 120k tokens
    p.write_text(
        json.dumps({"usage": {"input_tokens": 120_000, "output_tokens": 0}}) + "\n"
    )
    result = check_context_usage(str(p))
    # At exactly 60%, over_budget should be True (>=)
    assert result["over_budget"] is True


def test_check_context_usage_nonexistent_transcript():
    result = check_context_usage("/nonexistent/path/transcript.jsonl")
    assert result["over_budget"] is False
    assert result["tokens_used"] == 0


def test_check_context_usage_returns_required_keys(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"usage": {"input_tokens": 1000, "output_tokens": 0}}) + "\n")
    result = check_context_usage(str(p))
    assert "tokens_used" in result
    assert "limit" in result
    assert "fraction" in result
    assert "over_budget" in result


def test_emit_telemetry_writes_correct_fields(tmp_path):
    emit_telemetry(
        event="CTX_BUDGET_KILL",
        feature_id="test-feature-abc",
        tokens=150_000,
        limit=200_000,
        workspace=str(tmp_path),
    )
    events_path = tmp_path / ".bob" / "events.jsonl"
    assert events_path.exists()
    record = json.loads(events_path.read_text().strip())
    assert record["event"] == "CTX_BUDGET_KILL"
    assert record["feature_id"] == "test-feature-abc"
    assert record["tokens"] == 150_000
    assert record["limit"] == 200_000
    assert "timestamp" in record


def test_emit_telemetry_appends_multiple_events(tmp_path):
    for i in range(3):
        emit_telemetry(
            event="CTX_BUDGET_KILL",
            feature_id=f"feat-{i}",
            tokens=1000 * i,
            limit=200_000,
            workspace=str(tmp_path),
        )
    events_path = tmp_path / ".bob" / "events.jsonl"
    lines = [l for l in events_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 3


# ---------------------------------------------------------------------------
# Part B — extended_thinking toggle
# ---------------------------------------------------------------------------


def test_extended_thinking_default_is_true():
    assert EXTENDED_THINKING_DEFAULT is True


def test_get_extended_thinking_setting_returns_bool():
    result = get_extended_thinking_setting()
    assert isinstance(result, bool)


def test_classify_explicit_true_forces_on():
    result = classify_feature_thinking(feature_name="rename x", extended_thinking=True)
    assert result is True


def test_classify_explicit_false_forces_off():
    result = classify_feature_thinking(
        feature_name="refactor everything", extended_thinking=False
    )
    assert result is False


def test_classify_auto_rename_single_file_returns_off():
    result = classify_feature_thinking(
        feature_name="rename function",
        num_files=1,
        spec_quality=0.95,
        retry_count=0,
        extended_thinking="auto",
    )
    assert result is False


def test_classify_auto_refactor_returns_on():
    result = classify_feature_thinking(
        feature_name="refactor auth module",
        num_files=2,
        spec_quality=0.95,
        retry_count=0,
        extended_thinking="auto",
    )
    assert result is True


def test_classify_auto_multi_file_returns_on():
    result = classify_feature_thinking(
        feature_name="update docs",
        num_files=5,  # >= 4 files
        spec_quality=0.95,
        retry_count=0,
        extended_thinking="auto",
    )
    assert result is True


def test_classify_auto_low_spec_quality_returns_on():
    result = classify_feature_thinking(
        feature_name="neutral feature",
        num_files=1,
        spec_quality=0.70,  # < 0.80
        retry_count=0,
        extended_thinking="auto",
    )
    assert result is True


def test_classify_auto_retry_returns_on():
    result = classify_feature_thinking(
        feature_name="neutral feature",
        num_files=1,
        spec_quality=0.95,
        retry_count=2,  # >= 1
        extended_thinking="auto",
    )
    assert result is True


def test_classify_none_falls_back_to_auto():
    # None should behave same as "auto"
    result_auto = classify_feature_thinking(
        feature_name="rename x",
        num_files=1,
        spec_quality=0.95,
        retry_count=0,
        extended_thinking="auto",
    )
    result_none = classify_feature_thinking(
        feature_name="rename x",
        num_files=1,
        spec_quality=0.95,
        retry_count=0,
        extended_thinking=None,
    )
    assert result_auto == result_none


def test_thinking_kwargs_enabled():
    result = thinking_kwargs(True)
    assert result.get("type") == "enabled"
    assert result.get("budget_tokens", 0) > 0


def test_thinking_kwargs_disabled_empty():
    result = thinking_kwargs(False)
    assert result == {}


def test_thinking_kwargs_enabled_is_dict():
    result = thinking_kwargs(True)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Integration: orchestrator.run_loop
# ---------------------------------------------------------------------------


def test_integration_orchestrator_run_loop_importable():
    """Verify bob.orchestrator.run_loop is accessible (integration AC)."""
    import bob.orchestrator.run_loop as run_loop_mod
    # The module must be importable and expose the OrchestrationLoop class
    assert hasattr(run_loop_mod, "OrchestrationLoop"), (
        "bob.orchestrator.run_loop must expose OrchestrationLoop"
    )
    # Also accessible as an attribute on the parent package
    import bob.orchestrator as orchestrator
    assert hasattr(orchestrator, "run_loop")


# ---------------------------------------------------------------------------
# File existence: file.claude/hooks/context_budget.py
# ---------------------------------------------------------------------------


def test_file_claude_hooks_context_budget_exists():
    hook_path = Path(__file__).parents[1] / "file.claude" / "hooks" / "context_budget.py"
    assert hook_path.exists(), (
        f"Expected hook file at {hook_path} but it does not exist"
    )


def test_hook_file_is_valid_python():
    hook_path = Path(__file__).parents[1] / "file.claude" / "hooks" / "context_budget.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("context_budget_check", hook_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    assert hasattr(mod, "check_context_usage")
    assert hasattr(mod, "emit_telemetry")
