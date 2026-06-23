"""Tests for bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes.

Feature: 06837761-7fc1-400c-a77c-ae791520bce0
AC: pytest: tests/test_hot_reload_subagent_prompt_source_each_dispatch_code_fixes.py::test_hot_reload_subagent_prompt_source_each_dispatch_code_fixes
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Canonical AC test
# ---------------------------------------------------------------------------


def test_hot_reload_subagent_prompt_source_each_dispatch_code_fixes():
    """Core AC: function exists, delegates to reloader, returns list of reloaded modules."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=[]) as mock_fn:
        result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

    mock_fn.assert_called_once()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_module_importable():
    """The feature module must be importable."""
    import bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes  # noqa: F401


def test_function_importable():
    """The canonical function must be importable from the feature module."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )

    assert callable(hot_reload_subagent_prompt_source_each_dispatch_code_fixes)


# ---------------------------------------------------------------------------
# Delegates to prompt_source_reloader.maybe_reload_all
# ---------------------------------------------------------------------------


def test_delegates_to_maybe_reload_all():
    """Function must call maybe_reload_all exactly once per dispatch."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=[]) as mock_fn:
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

    mock_fn.assert_called_once()


def test_returns_empty_list_when_nothing_reloaded():
    """Returns empty list when all modules are up-to-date."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=[]):
        result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

    assert result == []


def test_returns_reloaded_module_names_when_stale():
    """Returns list of reloaded module names when stale modules are detected."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(
        _reloader, "maybe_reload_all", return_value=["bob3.superpowers"]
    ):
        result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

    assert result == ["bob3.superpowers"]


def test_returns_multiple_reloaded_modules():
    """Returns list of all reloaded modules when multiple are stale."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    import bob3.orchestrator.prompt_source_reloader as _reloader

    reloaded = ["bob3.superpowers", "bob3.models"]
    with patch.object(_reloader, "maybe_reload_all", return_value=reloaded):
        result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

    assert result == reloaded


# ---------------------------------------------------------------------------
# Return type contract
# ---------------------------------------------------------------------------


def test_return_type_is_list():
    """Function must always return a list."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "maybe_reload_all", return_value=[]):
        result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

    assert isinstance(result, list)


def test_list_elements_are_strings():
    """Returned list elements must be strings (module names)."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    import bob3.orchestrator.prompt_source_reloader as _reloader

    with patch.object(
        _reloader, "maybe_reload_all", return_value=["bob3.superpowers"]
    ):
        result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

    for item in result:
        assert isinstance(item, str)


# ---------------------------------------------------------------------------
# Idempotency — safe to call multiple times per process lifetime
# ---------------------------------------------------------------------------


def test_idempotent_multiple_calls():
    """Multiple consecutive calls without file changes return empty list after first."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    from bob3.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()

        # First call establishes baseline mtime for all modules
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

        # Freeze the mtime for every watched module using the recorded cache values
        frozen_cache = dict(prompt_source_reloader._MTIME_CACHE)

        def stable_mtime(module_name: str):
            return frozen_cache.get(module_name, 0.0)

        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", side_effect=stable_mtime
        ):
            r1 = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()
            r2 = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

        assert r1 == []
        assert r2 == []
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


# ---------------------------------------------------------------------------
# Integration with prompt_source_reloader — mtime change triggers reload
# ---------------------------------------------------------------------------


def test_detects_mtime_change_and_reloads():
    """Returns non-empty list when superpowers.py mtime has increased."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )
    from bob3.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()

        # Establish baseline
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes()
        base_mtime = prompt_source_reloader._MTIME_CACHE.get("bob3.superpowers", 0.0)
        changed_mtime = base_mtime + 1.0

        with patch.object(
            prompt_source_reloader, "get_prompt_mtime", return_value=changed_mtime
        ):
            with patch("importlib.reload"):
                result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()

        assert "bob3.superpowers" in result
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)


# ---------------------------------------------------------------------------
# No exception on normal call (resilience)
# ---------------------------------------------------------------------------


def test_no_exception_on_normal_call():
    """Function must not raise under normal operating conditions."""
    from bob3.hot_reload_subagent_prompt_source_each_dispatch_code_fixes import (
        hot_reload_subagent_prompt_source_each_dispatch_code_fixes,
    )

    result = hot_reload_subagent_prompt_source_each_dispatch_code_fixes()
    assert isinstance(result, list)
