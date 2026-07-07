"""Boundary/edge-case tests for resolve_sub_agent_max_turns.

Empty, zero, or minimum inputs return a well-defined result rather than raising.
"""

from __future__ import annotations

from bob.orchestrator.claude_executor import (
    DEFAULT_SUB_AGENT_MAX_TURNS_FALLBACK,
    build_sub_agent_options,
    resolve_sub_agent_max_turns,
)


def test_unset_env_returns_fallback_default(monkeypatch):
    """WHEN env is unset THEN the fallback default is returned (no error)."""
    monkeypatch.delenv("BOB_SUB_AGENT_MAX_TURNS", raising=False)
    assert resolve_sub_agent_max_turns() == DEFAULT_SUB_AGENT_MAX_TURNS_FALLBACK


def test_empty_string_env_returns_fallback_default(monkeypatch):
    """WHEN env is the empty string THEN the fallback default is returned."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "")
    assert resolve_sub_agent_max_turns() == DEFAULT_SUB_AGENT_MAX_TURNS_FALLBACK


def test_whitespace_env_returns_fallback_default(monkeypatch):
    """WHEN env is only whitespace THEN the fallback default is returned."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "   ")
    assert resolve_sub_agent_max_turns() == DEFAULT_SUB_AGENT_MAX_TURNS_FALLBACK


def test_minimum_valid_value_one(monkeypatch):
    """WHEN env is the minimum valid value (1) THEN it is honored."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "1")
    assert resolve_sub_agent_max_turns() == 1
    assert build_sub_agent_options().max_turns == 1


def test_surrounding_whitespace_is_stripped(monkeypatch):
    """A numeric value with surrounding whitespace parses cleanly."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "  42  ")
    assert resolve_sub_agent_max_turns() == 42


def test_fallback_default_constant_is_positive_int():
    """The fallback default is a well-defined positive integer."""
    assert isinstance(DEFAULT_SUB_AGENT_MAX_TURNS_FALLBACK, int)
    assert DEFAULT_SUB_AGENT_MAX_TURNS_FALLBACK > 0
