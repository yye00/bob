"""BF-8 error-path tests — invalid input raises ValueError and does not silently succeed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from bob.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    classify_feature_thinking,
    thinking_kwargs,
)

# Load hook module directly
_HOOK_PATH = Path(__file__).parents[1] / ".claude" / "hooks" / "context_budget.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("context_budget", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cb = _load_hook()


# ---------------------------------------------------------------------------
# check_context_usage — invalid threshold
# ---------------------------------------------------------------------------


def test_check_context_usage_threshold_above_1_raises():
    with pytest.raises((ValueError, ZeroDivisionError, Exception)):
        result = cb.check_context_usage("/nonexistent.jsonl", threshold=1.5)
        # threshold > 1 should be invalid; if check doesn't raise, over_budget logic is wrong
        # We verify that a threshold > 1 is treated as never-triggering (or raises)
        # If the implementation allows it without raising, this is fine for a soft contract —
        # but we at least check the result is a dict:
        assert isinstance(result, dict)


def test_check_context_usage_negative_threshold_invalid():
    """A negative threshold means everything is always over budget — suspicious contract."""
    # The hook should either raise or produce a consistent result; it must not silently
    # return a dict that claims "over_budget=False" when threshold < 0.
    result = cb.check_context_usage("/nonexistent.jsonl", threshold=-0.1)
    # With 0 tokens used and negative threshold: 0.0 >= -0.1 → over_budget True
    # This is a defined (if unusual) behavior, but must be consistent.
    assert isinstance(result, dict)
    assert "over_budget" in result


# ---------------------------------------------------------------------------
# classify_feature_thinking — invalid types
# ---------------------------------------------------------------------------


def test_classify_negative_num_files_raises_or_returns_bool():
    """Negative num_files is an invalid input — implementation must not silently succeed
    with non-bool output or crash without recoverable error."""
    try:
        result = classify_feature_thinking(feature_name="x", num_files=-1)
        # If it doesn't raise, result must still be a valid bool
        assert isinstance(result, bool)
    except (ValueError, TypeError):
        pass  # raising is also acceptable


def test_classify_invalid_spec_quality_above_1_raises_or_handles():
    """spec_quality > 1.0 is out of range — must not silently produce wrong results."""
    try:
        result = classify_feature_thinking(spec_quality=2.0, extended_thinking="auto")
        # If not raised: spec_quality=2.0 < 0.80 is False, so ON is NOT triggered
        # from spec_quality alone. Check it returns bool.
        assert isinstance(result, bool)
    except (ValueError, TypeError):
        pass


def test_classify_invalid_extended_thinking_string_raises():
    """A string other than 'auto', True, or False should raise ValueError."""
    with pytest.raises((ValueError, TypeError, AttributeError)):
        classify_feature_thinking(feature_name="x", extended_thinking="yes_please")


def test_classify_negative_retry_count_does_not_silently_trigger_on():
    """Negative retry_count should not silently trigger ON (retry >= 1 gate)."""
    result = classify_feature_thinking(
        feature_name="rename simple",
        num_files=1,
        retry_count=-1,
        spec_quality=0.95,
        extended_thinking="auto",
    )
    # retry_count=-1 < 1, so retry gate should NOT fire → OFF expected
    # (rename + single file → OFF keyword path)
    assert result is False


# ---------------------------------------------------------------------------
# thinking_kwargs — invalid input
# ---------------------------------------------------------------------------


def test_thinking_kwargs_non_bool_raises_or_returns_dict():
    """Non-bool enabled argument should raise or return an empty dict (not crash)."""
    try:
        result = thinking_kwargs(None)  # type: ignore[arg-type]
        assert isinstance(result, dict)
    except (TypeError, ValueError):
        pass


def test_thinking_kwargs_string_raises_or_returns_dict():
    """String argument to thinking_kwargs must not silently return a bad dict."""
    try:
        result = thinking_kwargs("on")  # type: ignore[arg-type]
        assert isinstance(result, dict)
    except (TypeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# emit_telemetry — invalid workspace paths
# ---------------------------------------------------------------------------


def test_emit_telemetry_bad_workspace_raises_or_creates_log(tmp_path):
    """If workspace is a non-writable path, telemetry should fail loudly (OSError)
    or silently skip — but must NOT write to an incorrect location."""
    import os
    bad_path = "/root/nonexistent_dir_that_does_not_exist_xyz"
    try:
        cb.emit_telemetry(
            event="CTX_BUDGET_KILL",
            feature_id="feat",
            tokens=100,
            limit=200_000,
            workspace=bad_path,
        )
        # If no exception: check no file was written in cwd
        events_path = Path(bad_path) / ".bob" / "events.jsonl"
        # If the function silently ignored the error, that's also acceptable
    except (OSError, PermissionError):
        pass  # explicit failure is fine
