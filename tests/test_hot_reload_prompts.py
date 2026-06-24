"""Tests for bob.superpowers.reload_prompt_source_if_changed (feature 6a31a708).

Verifies that the per-module hot-reload function:
- is importable and callable from bob.superpowers
- delegates to prompt_source_reloader.reload_if_stale
- returns True only when a reload was performed
- returns False when the module is unchanged or not found
- works for the default module (bob.superpowers) and for explicit names
- integrates with the orchestrator dispatch path
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Importability and callable contract
# ---------------------------------------------------------------------------


def test_reload_prompt_source_if_changed_importable():
    """reload_prompt_source_if_changed must be importable from bob.superpowers."""
    from bob.superpowers import reload_prompt_source_if_changed  # noqa: F401


def test_reload_prompt_source_if_changed_is_callable():
    """reload_prompt_source_if_changed must be callable."""
    from bob.superpowers import reload_prompt_source_if_changed

    assert callable(reload_prompt_source_if_changed)


def test_reload_prompt_source_if_changed_returns_bool():
    """reload_prompt_source_if_changed must return a bool."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed()

    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Default module is bob.superpowers
# ---------------------------------------------------------------------------


def test_reload_prompt_source_if_changed_default_module():
    """Default module_name is bob.superpowers."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    called_with = []

    def capture_reload_if_stale(module_name):
        called_with.append(module_name)
        return False

    with patch.object(_reloader, "reload_if_stale", side_effect=capture_reload_if_stale):
        reload_prompt_source_if_changed()

    assert called_with == ["bob.superpowers"]


# ---------------------------------------------------------------------------
# Delegates to reload_if_stale
# ---------------------------------------------------------------------------


def test_reload_prompt_source_if_changed_delegates_to_reload_if_stale():
    """reload_prompt_source_if_changed calls reload_if_stale exactly once."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_prompt_source_if_changed("bob.superpowers")

    mock_fn.assert_called_once_with("bob.superpowers")


def test_reload_prompt_source_if_changed_explicit_module():
    """Explicit module_name is forwarded to reload_if_stale."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_prompt_source_if_changed("bob.models")

    mock_fn.assert_called_once_with("bob.models")


# ---------------------------------------------------------------------------
# Return value reflects whether a reload occurred
# ---------------------------------------------------------------------------


def test_reload_prompt_source_if_changed_returns_true_on_reload():
    """Returns True when reload_if_stale reports a reload was performed."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=True):
        result = reload_prompt_source_if_changed()

    assert result is True


def test_reload_prompt_source_if_changed_returns_false_when_unchanged():
    """Returns False when the module is already up-to-date."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed()

    assert result is False


def test_reload_prompt_source_if_changed_returns_false_on_missing_module():
    """Returns False when the module file cannot be found."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed("bob.nonexistent_module_xyz")

    assert result is False


# ---------------------------------------------------------------------------
# mtime-based reload detection (integration with reloader internals)
# ---------------------------------------------------------------------------


def test_reload_detects_mtime_change_for_superpowers():
    """reload_prompt_source_if_changed triggers reload when superpowers mtime changes."""
    from bob.orchestrator import prompt_source_reloader
    from bob.superpowers import reload_prompt_source_if_changed

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()

        # First call: baseline (never reloads on first check)
        first_result = reload_prompt_source_if_changed("bob.superpowers")
        assert first_result is False

        base_mtime = prompt_source_reloader._MTIME_CACHE.get("bob.superpowers", 0.0)
        changed_mtime = base_mtime + 1.0

        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", return_value=changed_mtime
        ):
            with patch("importlib.reload"):
                second_result = reload_prompt_source_if_changed("bob.superpowers")

        assert second_result is True
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


def test_no_reload_when_mtime_unchanged():
    """reload_prompt_source_if_changed does not reload when mtime is stable."""
    from bob.orchestrator import prompt_source_reloader
    from bob.superpowers import reload_prompt_source_if_changed

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()

        # Establish baseline
        reload_prompt_source_if_changed("bob.superpowers")
        base_mtime = prompt_source_reloader._MTIME_CACHE.get("bob.superpowers", 0.0)

        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", return_value=base_mtime
        ):
            with patch("importlib.reload") as mock_reload_fn:
                result = reload_prompt_source_if_changed("bob.superpowers")

        assert result is False
        mock_reload_fn.assert_not_called()
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


# ---------------------------------------------------------------------------
# Orchestrator integration — reload is called before subagent dispatch
# ---------------------------------------------------------------------------


def test_orchestrator_run_loop_imports_reload():
    """run_loop.py must import the prompt-source reloader for dispatch hot-reload."""
    import bob.orchestrator.run_loop as rl_mod

    # The orchestrator imports maybe_reload_all as _maybe_reload_prompt_sources
    assert hasattr(rl_mod, "_maybe_reload_prompt_sources")


def test_orchestrator_reloader_module_watches_superpowers():
    """The reloader's module watch-list includes bob.superpowers."""
    from bob.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob.superpowers" in _PROMPT_SOURCE_MODULES


def test_orchestrator_reloader_module_watches_models():
    """The reloader's module watch-list includes bob.models."""
    from bob.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob.models" in _PROMPT_SOURCE_MODULES


def test_reload_prompt_source_if_changed_no_exception_on_call():
    """reload_prompt_source_if_changed must not raise under normal conditions."""
    from bob.superpowers import reload_prompt_source_if_changed

    # Should complete without error (may or may not trigger a reload)
    result = reload_prompt_source_if_changed()
    assert isinstance(result, bool)


def test_reload_prompt_source_if_changed_idempotent_on_consecutive_calls():
    """Consecutive calls with no file change return False after the first call."""
    from bob.superpowers import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    original_cache = dict(_reloader._MTIME_CACHE)
    try:
        _reloader._MTIME_CACHE.clear()

        # First call: baseline
        reload_prompt_source_if_changed("bob.superpowers")

        mtime = _reloader._MTIME_CACHE.get("bob.superpowers", 0.0)
        with patch.object(_reloader, "get_prompt_mtime", return_value=mtime):
            r1 = reload_prompt_source_if_changed("bob.superpowers")
            r2 = reload_prompt_source_if_changed("bob.superpowers")

        assert r1 is False
        assert r2 is False
    finally:
        _reloader._MTIME_CACHE.clear()
        _reloader._MTIME_CACHE.update(original_cache)
