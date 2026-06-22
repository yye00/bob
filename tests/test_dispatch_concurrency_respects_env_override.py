"""Tests that BOB3_MAX_CONCURRENT_FEATURES env var overrides the default.

AC: pytest: tests/test_dispatch_concurrency_respects_env_override.py
"""

from __future__ import annotations

import os
import importlib

import pytest


def _reload_resolver():
    """Re-import the resolver function after env var change."""
    import bob3.orchestrator.run_loop as rl
    return rl._resolve_max_concurrent_features


def test_env_override_returns_configured_value(monkeypatch):
    """_resolve_max_concurrent_features returns the env var integer when set."""
    monkeypatch.setenv("BOB3_MAX_CONCURRENT_FEATURES", "5")
    resolve = _reload_resolver()
    assert resolve() == 5


def test_env_override_default_is_three(monkeypatch):
    """_resolve_max_concurrent_features returns 3 when env var is not set."""
    monkeypatch.delenv("BOB3_MAX_CONCURRENT_FEATURES", raising=False)
    resolve = _reload_resolver()
    assert resolve() == 3


def test_env_override_invalid_value_falls_back_to_default(monkeypatch):
    """_resolve_max_concurrent_features falls back to 3 for non-integer values."""
    monkeypatch.setenv("BOB3_MAX_CONCURRENT_FEATURES", "not_a_number")
    resolve = _reload_resolver()
    assert resolve() == 3


def test_env_override_zero_clamps_to_one(monkeypatch):
    """_resolve_max_concurrent_features clamps 0 to 1 (never returns 0)."""
    monkeypatch.setenv("BOB3_MAX_CONCURRENT_FEATURES", "0")
    resolve = _reload_resolver()
    assert resolve() == 1


def test_env_override_negative_clamps_to_one(monkeypatch):
    """_resolve_max_concurrent_features clamps negative values to 1."""
    monkeypatch.setenv("BOB3_MAX_CONCURRENT_FEATURES", "-2")
    resolve = _reload_resolver()
    assert resolve() == 1


def test_env_override_one_is_sequential(monkeypatch):
    """BOB3_MAX_CONCURRENT_FEATURES=1 gives sequential mode (cap=1)."""
    monkeypatch.setenv("BOB3_MAX_CONCURRENT_FEATURES", "1")
    resolve = _reload_resolver()
    assert resolve() == 1


def test_env_override_large_value_accepted(monkeypatch):
    """Large values are accepted without capping."""
    monkeypatch.setenv("BOB3_MAX_CONCURRENT_FEATURES", "20")
    resolve = _reload_resolver()
    assert resolve() == 20
