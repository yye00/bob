"""Tests for .claude/hooks/extended_thinking.py (BF-8 Part B)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HOOK_PATH = Path(__file__).parents[2] / ".claude" / "hooks" / "extended_thinking.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("extended_thinking", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


et = _load_module()


# ---------------------------------------------------------------------------
# classify_and_apply — explicit overrides
# ---------------------------------------------------------------------------


def test_classify_and_apply_explicit_true():
    result = et.classify_and_apply(feature_name="rename x", extended_thinking=True)
    assert result["enabled"] is True
    assert result["thinking"]["type"] == "enabled"
    assert result["reason"] == "explicit override: extended_thinking=True"


def test_classify_and_apply_explicit_false():
    result = et.classify_and_apply(
        feature_name="refactor everything", num_files=10, extended_thinking=False
    )
    assert result["enabled"] is False
    assert result["thinking"] == {}
    assert result["reason"] == "explicit override: extended_thinking=False"


# ---------------------------------------------------------------------------
# classify_and_apply — auto classifier
# ---------------------------------------------------------------------------


def test_classify_auto_off_rename_single_file():
    result = et.classify_and_apply(
        feature_name="rename the variable", num_files=1, extended_thinking="auto"
    )
    assert result["enabled"] is False
    assert "rename" in result["reason"]


def test_classify_auto_off_typo_single_file():
    result = et.classify_and_apply(
        feature_name="fix typo in README", num_files=1, extended_thinking="auto"
    )
    assert result["enabled"] is False


def test_classify_auto_on_many_files():
    result = et.classify_and_apply(
        feature_name="some task", num_files=5, extended_thinking="auto"
    )
    assert result["enabled"] is True
    assert "4" in result["reason"]


def test_classify_auto_on_low_spec_quality():
    result = et.classify_and_apply(
        spec_quality=0.70, num_files=1, extended_thinking="auto"
    )
    assert result["enabled"] is True
    assert "spec quality" in result["reason"]


def test_classify_auto_on_retry():
    result = et.classify_and_apply(
        feature_name="neutral task", num_files=2, retry_count=1, extended_thinking="auto"
    )
    assert result["enabled"] is True
    assert "retry" in result["reason"]


def test_classify_auto_on_refactor_keyword():
    result = et.classify_and_apply(
        feature_name="refactor auth module", num_files=3, extended_thinking="auto"
    )
    assert result["enabled"] is True


def test_classify_auto_on_bugfix_keyword():
    result = et.classify_and_apply(
        feature_name="bugfix for login error", num_files=2, extended_thinking="auto"
    )
    assert result["enabled"] is True


def test_classify_none_uses_auto_path():
    result = et.classify_and_apply(feature_name="neutral plain task", extended_thinking=None)
    assert isinstance(result["enabled"], bool)


# ---------------------------------------------------------------------------
# classify_and_apply — invalid extended_thinking value
# ---------------------------------------------------------------------------


def test_classify_invalid_string_raises():
    with pytest.raises((ValueError, TypeError)):
        et.classify_and_apply(feature_name="x", extended_thinking="yes_please")


# ---------------------------------------------------------------------------
# fresh_subagent_required when flag changes from default
# ---------------------------------------------------------------------------


def test_fresh_subagent_required_when_off_and_default_is_on():
    # Default is ON; forcing OFF requires a fresh subagent
    result = et.classify_and_apply(
        feature_name="rename x", num_files=1, extended_thinking="auto"
    )
    if result["enabled"] != et.EXTENDED_THINKING_DEFAULT:
        assert result["fresh_subagent_required"] is True


def test_fresh_subagent_not_required_when_matches_default():
    # Explicitly set to default value — no change, no fresh subagent
    result = et.classify_and_apply(
        feature_name="refactor big system", num_files=10,
        extended_thinking=et.EXTENDED_THINKING_DEFAULT,
    )
    assert result["fresh_subagent_required"] is False


# ---------------------------------------------------------------------------
# thinking dict shape
# ---------------------------------------------------------------------------


def test_thinking_dict_when_enabled():
    result = et.classify_and_apply(feature_name="x", extended_thinking=True)
    assert "type" in result["thinking"]
    assert result["thinking"]["type"] == "enabled"
    assert result["thinking"].get("budget_tokens", 0) > 0


def test_thinking_dict_empty_when_disabled():
    result = et.classify_and_apply(
        feature_name="rename x", num_files=1, extended_thinking=False
    )
    assert result["thinking"] == {}


# ---------------------------------------------------------------------------
# get_default
# ---------------------------------------------------------------------------


def test_get_default_returns_bool():
    val = et.get_default()
    assert isinstance(val, bool)
