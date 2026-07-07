"""Regression tests: BOB_SUB_AGENT_MAX_TURNS is honored at the spawn call site.

The define-vs-honor gap (bob95 build defect): DEFAULT_SUB_AGENT_MAX_TURNS was a
module-level default read once at import, and the spawn call site in
orchestrator/run_loop.py passed a hardcoded literal (max_turns=25) into
build_sub_agent_options(...). Setting BOB_SUB_AGENT_MAX_TURNS therefore changed
nothing. These tests prove the env value reaches the spawned sub-agent options.
"""

from __future__ import annotations

import pytest

from bob.orchestrator import run_loop
from bob.orchestrator.claude_executor import (
    build_sub_agent_options,
    resolve_sub_agent_max_turns,
)


def test_build_sub_agent_options_is_reachable_from_run_loop():
    """AC: build_sub_agent_options is importable via bob.orchestrator.run_loop."""
    assert run_loop.build_sub_agent_options is build_sub_agent_options


def test_env_max_turns_reaches_spawned_options(monkeypatch):
    """WHEN BOB_SUB_AGENT_MAX_TURNS is set THEN spawned options.max_turns equals it."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "77")
    options = build_sub_agent_options()
    assert options.max_turns == 77


def test_env_change_is_honored_after_import(monkeypatch):
    """Setting the env AFTER module import is honored (not frozen at import time)."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "123")
    assert resolve_sub_agent_max_turns() == 123
    assert build_sub_agent_options().max_turns == 123


def test_default_when_env_unset(monkeypatch):
    """WHEN BOB_SUB_AGENT_MAX_TURNS is unset THEN the default (25) is used."""
    monkeypatch.delenv("BOB_SUB_AGENT_MAX_TURNS", raising=False)
    assert resolve_sub_agent_max_turns() == 25
    assert build_sub_agent_options().max_turns == 25


def test_explicit_max_turns_overrides_env(monkeypatch):
    """An explicit max_turns argument takes precedence over the env default."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "50")
    options = build_sub_agent_options(max_turns=10)
    assert options.max_turns == 10


def test_raising_env_relieves_completability_cliff(monkeypatch):
    """A raised budget is actually observable on the spawned options (F-R7-649)."""
    monkeypatch.setenv("BOB_SUB_AGENT_MAX_TURNS", "200")
    assert build_sub_agent_options().max_turns == 200
