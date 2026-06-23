"""Tests for bob3.extended_thinking_classifier.classify_extended_thinking (BF-8 Part B).

Verifies the AC-required function classify_extended_thinking in the
extended_thinking_classifier module, covering:
  - Explicit True/False overrides
  - Auto-classifier OFF branch (rename, doc, typo, format + single file)
  - Auto-classifier ON branch (multi-file, low spec quality, retry, keywords)
  - Default fallback to EXTENDED_THINKING_DEFAULT
  - Invalid extended_thinking string raises ValueError
  - thinking_kwargs helpers
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from bob3.extended_thinking_classifier import (
    EXTENDED_THINKING_DEFAULT,
    classify_extended_thinking,
    thinking_kwargs,
)


# ---------------------------------------------------------------------------
# Explicit overrides
# ---------------------------------------------------------------------------


def test_explicit_true_forces_on():
    assert classify_extended_thinking(feature_name="rename x", extended_thinking=True) is True


def test_explicit_false_forces_off():
    assert classify_extended_thinking(feature_name="complex refactor", extended_thinking=False) is False


# ---------------------------------------------------------------------------
# Auto-classifier — OFF branch
# ---------------------------------------------------------------------------


def test_auto_off_rename_single_file():
    assert classify_extended_thinking(feature_name="rename FooBar", num_files=1, extended_thinking="auto") is False


def test_auto_off_doc_update():
    assert classify_extended_thinking(feature_name="update doc strings", num_files=1, extended_thinking=None) is False


def test_auto_off_typo_fix():
    assert classify_extended_thinking(feature_name="fix typo in README", num_files=1, extended_thinking=None) is False


def test_auto_off_format_change():
    assert classify_extended_thinking(feature_name="format Python files", num_files=1, extended_thinking="auto") is False


# ---------------------------------------------------------------------------
# Auto-classifier — ON branch
# ---------------------------------------------------------------------------


def test_auto_on_multi_file():
    assert classify_extended_thinking(feature_name="neutral task", num_files=4, extended_thinking="auto") is True


def test_auto_on_low_spec_quality():
    assert classify_extended_thinking(spec_quality=0.70, extended_thinking="auto") is True


def test_auto_on_retry_count():
    assert classify_extended_thinking(feature_name="some feature", retry_count=1, extended_thinking="auto") is True


def test_auto_on_refactor_keyword():
    assert classify_extended_thinking(feature_name="refactor auth module", extended_thinking="auto") is True


def test_auto_on_migration_keyword():
    assert classify_extended_thinking(feature_name="migration to new schema", extended_thinking="auto") is True


def test_auto_on_bugfix_keyword():
    assert classify_extended_thinking(feature_name="bugfix in orchestrator", extended_thinking="auto") is True


def test_auto_on_integration_keyword():
    assert classify_extended_thinking(feature_name="integration with MCP", extended_thinking="auto") is True


# ---------------------------------------------------------------------------
# Default fallback
# ---------------------------------------------------------------------------


def test_default_fallback_when_no_signals():
    result = classify_extended_thinking(
        feature_name="neutral feature",
        num_files=2,
        spec_quality=0.90,
        retry_count=0,
        extended_thinking=None,
    )
    assert result is EXTENDED_THINKING_DEFAULT


def test_extended_thinking_default_is_true():
    assert EXTENDED_THINKING_DEFAULT is True


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------


def test_invalid_string_raises_value_error():
    with pytest.raises((ValueError, TypeError)):
        classify_extended_thinking(feature_name="x", extended_thinking="yes_please")


def test_none_extended_thinking_uses_classifier():
    result = classify_extended_thinking(feature_name="rename y", num_files=1, extended_thinking=None)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# thinking_kwargs helper
# ---------------------------------------------------------------------------


def test_thinking_kwargs_enabled_returns_type_enabled():
    kwargs = thinking_kwargs(True)
    assert kwargs.get("type") == "enabled"
    assert kwargs.get("budget_tokens", 0) > 0


def test_thinking_kwargs_disabled_returns_empty():
    assert thinking_kwargs(False) == {}
