"""Error-path tests for model-escalation ladder (F-R7-633).

These tests verify that invalid inputs raise ValueError and never silently
succeed — the resolver must signal errors, not return a plausible-but-wrong
model ID that would cause silent misbehaviour downstream.
"""

from __future__ import annotations

import pytest

from bob3.orchestrator.claude_executor import resolve_model_name


# ---------------------------------------------------------------------------
# resolve_model_name — error paths (raises ValueError for unknown aliases)


def test_resolve_model_name_unknown_alias_raises():
    """A completely unknown alias must raise ValueError, not return None or a guess."""
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model_name("gpt4")


def test_resolve_model_name_typo_raises():
    """A near-miss typo must raise ValueError — not silently succeed."""
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model_name("sonnet-")  # trailing dash typo


def test_resolve_model_name_empty_string_raises():
    """An empty string (after stripping) is not a valid alias — must raise."""
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model_name("")


def test_resolve_model_name_whitespace_only_raises():
    """Whitespace-only input normalises to empty, which is invalid — must raise."""
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model_name("   ")


def test_resolve_model_name_garbage_string_raises():
    """Arbitrary garbage must raise ValueError, not return a default."""
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model_name("not-a-model-at-all-xyz")


def test_resolve_model_name_none_does_not_raise():
    """None is the documented sentinel for 'no model specified' — must return None."""
    result = resolve_model_name(None)
    assert result is None


def test_resolve_model_name_valid_alias_does_not_raise():
    """A known alias must succeed without raising."""
    result = resolve_model_name("sonnet")
    assert result is not None
    assert "claude" in result.lower()


def test_resolve_model_name_valid_opus_does_not_raise():
    """opus alias must resolve without raising."""
    result = resolve_model_name("opus")
    assert result is not None


def test_resolve_model_name_raises_with_helpful_message():
    """The ValueError message must list valid options so callers can self-correct."""
    with pytest.raises(ValueError) as exc_info:
        resolve_model_name("badmodel")
    message = str(exc_info.value)
    # Must name the model that was rejected
    assert "badmodel" in message
    # Must suggest alternatives
    assert "sonnet" in message or "Use an alias" in message


def test_resolve_model_name_numeric_input_raises():
    """A numeric string is not a valid model alias — must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model_name("42")


def test_resolve_model_name_sql_injection_string_raises():
    """Injection-like string is invalid — must raise, not match a model."""
    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model_name("'; DROP TABLE features; --")
