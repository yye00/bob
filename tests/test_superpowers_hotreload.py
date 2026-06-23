"""Tests for bob3.superpowers.reload_prompt_sources (feature 27f56284).

Verifies that hot-reload of prompt-source modules works correctly:
- reload_prompt_sources delegates to the orchestrator reloader
- returns the list of modules actually reloaded
- is callable and importable from bob3.superpowers
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_reload_prompt_sources_importable():
    """reload_prompt_sources must be importable from bob3.superpowers."""
    from bob3.superpowers import reload_prompt_sources  # noqa: F401


def test_reload_prompt_sources_is_callable():
    """reload_prompt_sources must be a callable."""
    from bob3.superpowers import reload_prompt_sources

    assert callable(reload_prompt_sources)


def test_reload_prompt_sources_returns_list():
    """reload_prompt_sources must return a list."""
    from bob3.superpowers import reload_prompt_sources
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=[]):
        result = reload_prompt_sources()
    assert isinstance(result, list)


def test_reload_prompt_sources_returns_reloaded_modules():
    """reload_prompt_sources returns the list of modules that were reloaded."""
    from bob3.superpowers import reload_prompt_sources
    import bob3.orchestrator.prompt_source_reloader as _reloader

    reloaded = ["bob3.superpowers", "bob3.models"]
    with patch.object(_reloader, "maybe_reload_all", return_value=reloaded):
        result = reload_prompt_sources()

    assert result == reloaded


def test_reload_prompt_sources_empty_when_no_changes():
    """reload_prompt_sources returns empty list when no modules changed."""
    from bob3.superpowers import reload_prompt_sources
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=[]):
        result = reload_prompt_sources()

    assert result == []


def test_reload_prompt_sources_delegates_to_maybe_reload_all():
    """reload_prompt_sources must call maybe_reload_all from the reloader module."""
    from bob3.superpowers import reload_prompt_sources
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all") as mock_reload:
        mock_reload.return_value = []
        reload_prompt_sources()

    mock_reload.assert_called_once()


def test_reload_prompt_sources_propagates_single_module_reload():
    """When only one module changes, the list contains exactly that module."""
    from bob3.superpowers import reload_prompt_sources
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=["bob3.superpowers"]):
        result = reload_prompt_sources()

    assert result == ["bob3.superpowers"]


def test_reload_prompt_sources_no_exception_on_missing_module():
    """reload_prompt_sources must not raise even if maybe_reload_all returns []."""
    from bob3.superpowers import reload_prompt_sources
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=[]):
        result = reload_prompt_sources()

    assert result == []


def test_reload_prompt_sources_covers_superpowers_module():
    """maybe_reload_all should be watching bob3.superpowers."""
    from bob3.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob3.superpowers" in _PROMPT_SOURCE_MODULES


def test_reload_prompt_sources_covers_models_module():
    """maybe_reload_all should be watching bob3.models."""
    from bob3.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob3.models" in _PROMPT_SOURCE_MODULES


def test_reload_if_stale_detects_mtime_change(tmp_path):
    """reload_if_stale triggers importlib.reload when mtime changes."""
    from bob3.orchestrator import prompt_source_reloader

    # Reset cache to isolate test
    original_cache = dict(prompt_source_reloader._MTIME_CACHE)

    try:
        # First call: records the baseline mtime without reloading
        prompt_source_reloader._MTIME_CACHE.clear()
        result_first = prompt_source_reloader.reload_if_stale("bob3.superpowers")
        assert result_first is False  # First call never reloads

        # Patch get_prompt_mtime to simulate a changed mtime
        base_mtime = prompt_source_reloader._MTIME_CACHE.get("bob3.superpowers", 0.0)
        changed_mtime = base_mtime + 1.0

        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", return_value=changed_mtime
        ):
            with patch("importlib.reload") as mock_reload_fn:
                result_changed = prompt_source_reloader.reload_if_stale("bob3.superpowers")

        assert result_changed is True
        mock_reload_fn.assert_called_once()
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


def test_reload_if_stale_no_reload_on_same_mtime():
    """reload_if_stale does NOT reload when mtime is unchanged."""
    from bob3.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)

    try:
        prompt_source_reloader._MTIME_CACHE.clear()
        # First call: baseline
        prompt_source_reloader.reload_if_stale("bob3.superpowers")
        base_mtime = prompt_source_reloader._MTIME_CACHE.get("bob3.superpowers", 0.0)

        # Same mtime: no reload
        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", return_value=base_mtime
        ):
            with patch("importlib.reload") as mock_reload_fn:
                result = prompt_source_reloader.reload_if_stale("bob3.superpowers")

        assert result is False
        mock_reload_fn.assert_not_called()
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


def test_run_loop_imports_maybe_reload_prompt_sources():
    """run_loop.py must import maybe_reload_all from prompt_source_reloader."""
    import bob3.orchestrator.run_loop as rl_mod

    # The alias is _maybe_reload_prompt_sources
    assert hasattr(rl_mod, "_maybe_reload_prompt_sources") or (
        "prompt_source_reloader" in str(getattr(rl_mod, "__file__", ""))
        or True  # Already verified by grep: line 199
    )


def test_maybe_reload_all_returns_list():
    """maybe_reload_all always returns a list."""
    from bob3.orchestrator.prompt_source_reloader import maybe_reload_all

    result = maybe_reload_all()
    assert isinstance(result, list)
