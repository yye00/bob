"""Error-path tests for resolve_sub_agent_max_turns.

Invalid BOB_SUB_AGENT_MAX_TURNS values raise ValueError rather than silently
succeeding with a wrong or misleading budget.
"""

from __future__ import annotations

import pytest

from bob.orchestrator.claude_executor import resolve_sub_agent_max_turns


def test_non_numeric_env_raises_value_error(monkeypatch):
    """A non-numeric env value raises ValueError (not silently ignored)."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "abc")
    with pytest.raises(ValueError, match="BOB_SUB_AGENT_MAX_TURNS"):
        resolve_sub_agent_max_turns()


def test_zero_env_raises_value_error(monkeypatch):
    """Zero is not a valid turn budget and raises ValueError."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "0")
    with pytest.raises(ValueError):
        resolve_sub_agent_max_turns()


def test_negative_env_raises_value_error(monkeypatch):
    """A negative turn budget raises ValueError."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "-5")
    with pytest.raises(ValueError):
        resolve_sub_agent_max_turns()


def test_float_env_raises_value_error(monkeypatch):
    """A non-integer numeric string raises ValueError."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "3.5")
    with pytest.raises(ValueError):
        resolve_sub_agent_max_turns()


def test_error_message_names_the_env_var(monkeypatch):
    """The ValueError message names BOB_SUB_AGENT_MAX_TURNS for debuggability."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "not-a-number")
    with pytest.raises(ValueError, match="BOB_SUB_AGENT_MAX_TURNS"):
        resolve_sub_agent_max_turns()
