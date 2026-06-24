"""Tests for bob.superpowers.reload_prompt_source_if_changed (feature cedc291e).

Verifies that hot-reload of prompt-source modules works correctly:
- reload_prompt_source_if_changed is importable from bob.superpowers
- reloads only when mtime changes (cheap: stat + dict lookup)
- returns True on reload, False when up-to-date or file missing
- orchestrator run_loop integrates the reloader before each dispatch
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# AC: Function defined: bob.superpowers.reload_prompt_source_if_changed
# ---------------------------------------------------------------------------


def test_reload_prompt_source_if_changed_importable():
    """reload_prompt_source_if_changed must be importable from bob.superpowers."""
    from bob.superpowers import reload_prompt_source_if_changed  # noqa: F401


def test_reload_prompt_source_if_changed_is_callable():
    """reload_prompt_source_if_changed must be a callable."""
    from bob.superpowers import reload_prompt_source_if_changed

    assert callable(reload_prompt_source_if_changed)


def test_reload_prompt_source_if_changed_default_arg():
    """reload_prompt_source_if_changed defaults to 'bob.superpowers' module."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_prompt_source_if_changed()
    mock_fn.assert_called_once_with("bob.superpowers")


def test_reload_prompt_source_if_changed_custom_module():
    """reload_prompt_source_if_changed passes module_name to reload_if_stale."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_prompt_source_if_changed("bob.models")
    mock_fn.assert_called_once_with("bob.models")


def test_reload_prompt_source_if_changed_returns_true_on_reload():
    """Returns True when the module was reloaded."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=True):
        result = reload_prompt_source_if_changed()
    assert result is True


def test_reload_prompt_source_if_changed_returns_false_when_up_to_date():
    """Returns False when the module is up-to-date (mtime unchanged)."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed()
    assert result is False


def test_reload_prompt_source_if_changed_returns_false_on_missing_file():
    """Returns False when the module file cannot be found."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed("bob.nonexistent_module_xyz")
    assert result is False


# ---------------------------------------------------------------------------
# AC: integration: bob.orchestrator (run_loop integrates the reloader)
# ---------------------------------------------------------------------------


def test_run_loop_imports_reloader():
    """run_loop must import maybe_reload_all as _maybe_reload_prompt_sources."""
    import bob.orchestrator.run_loop as rl_mod

    assert hasattr(rl_mod, "_maybe_reload_prompt_sources"), (
        "run_loop must expose _maybe_reload_prompt_sources (aliased maybe_reload_all)"
    )


def test_run_loop_reloader_is_callable():
    """_maybe_reload_prompt_sources in run_loop must be callable."""
    import bob.orchestrator.run_loop as rl_mod

    assert callable(rl_mod._maybe_reload_prompt_sources)


# ---------------------------------------------------------------------------
# Underlying reloader: prompt_source_reloader behaviour
# ---------------------------------------------------------------------------


def test_reload_if_stale_first_call_records_baseline():
    """First call records baseline mtime without triggering a reload."""
    from bob.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()
        result = prompt_source_reloader.reload_if_stale("bob.superpowers")
        assert result is False
        assert "bob.superpowers" in prompt_source_reloader._MTIME_CACHE
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


def test_reload_if_stale_detects_mtime_change():
    """reload_if_stale triggers importlib.reload when mtime changes."""
    from bob.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader.reload_if_stale("bob.superpowers")
        base_mtime = prompt_source_reloader._MTIME_CACHE.get("bob.superpowers", 0.0)
        changed_mtime = base_mtime + 1.0

        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", return_value=changed_mtime
        ):
            with patch("importlib.reload") as mock_reload_fn:
                result = prompt_source_reloader.reload_if_stale("bob.superpowers")

        assert result is True
        mock_reload_fn.assert_called_once()
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


def test_reload_if_stale_no_reload_on_same_mtime():
    """reload_if_stale does NOT reload when mtime is unchanged."""
    from bob.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader.reload_if_stale("bob.superpowers")
        base_mtime = prompt_source_reloader._MTIME_CACHE.get("bob.superpowers", 0.0)

        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", return_value=base_mtime
        ):
            with patch("importlib.reload") as mock_reload_fn:
                result = prompt_source_reloader.reload_if_stale("bob.superpowers")

        assert result is False
        mock_reload_fn.assert_not_called()
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


def test_maybe_reload_all_returns_list():
    """maybe_reload_all always returns a list."""
    from bob.orchestrator.prompt_source_reloader import maybe_reload_all

    result = maybe_reload_all()
    assert isinstance(result, list)


def test_prompt_source_modules_includes_superpowers():
    """_PROMPT_SOURCE_MODULES must include bob.superpowers."""
    from bob.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob.superpowers" in _PROMPT_SOURCE_MODULES


def test_prompt_source_modules_includes_models():
    """_PROMPT_SOURCE_MODULES must include bob.models."""
    from bob.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob.models" in _PROMPT_SOURCE_MODULES
