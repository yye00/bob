"""Tests for bob3.hot_reload — hot-reload prompt source on each dispatch.

Feature: bfef8e7f-d936-4c06-8e75-0f125b79fe1d
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Import surface
# ---------------------------------------------------------------------------

def test_module_importable():
    """bob3.hot_reload is importable without error."""
    import bob3.hot_reload  # noqa: F401


def test_function_defined():
    """bob3.hot_reload.reload_prompt_source_if_changed is callable."""
    from bob3.hot_reload import reload_prompt_source_if_changed

    assert callable(reload_prompt_source_if_changed)


# ---------------------------------------------------------------------------
# Correct-path behaviour
# ---------------------------------------------------------------------------

def test_returns_false_when_no_change():
    """reload_prompt_source_if_changed returns False when mtime has not changed."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        result = reload_prompt_source_if_changed("bob3.superpowers")

    assert result is False
    mock_fn.assert_called_once_with("bob3.superpowers")


def test_returns_true_when_module_stale():
    """reload_prompt_source_if_changed returns True when the source file has changed."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=True) as mock_fn:
        result = reload_prompt_source_if_changed("bob3.superpowers")

    assert result is True
    mock_fn.assert_called_once_with("bob3.superpowers")


def test_default_module_is_superpowers():
    """The default module_name is bob3.superpowers."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_prompt_source_if_changed()

    mock_fn.assert_called_once_with("bob3.superpowers")


def test_accepts_custom_module_name():
    """reload_prompt_source_if_changed forwards any module name to the reloader."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_prompt_source_if_changed("bob3.models")

    mock_fn.assert_called_once_with("bob3.models")


def test_return_type_is_bool():
    """Return value is always a bool."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed()

    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_raises_value_error_on_non_string():
    """ValueError is raised when module_name is not a string."""
    from bob3.hot_reload import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(42)  # type: ignore[arg-type]


def test_raises_value_error_on_none():
    """ValueError is raised when module_name is None."""
    from bob3.hot_reload import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(None)  # type: ignore[arg-type]


def test_unknown_module_returns_false():
    """An unimportable module name returns False rather than raising."""
    from bob3.hot_reload import reload_prompt_source_if_changed

    result = reload_prompt_source_if_changed("bob3.__nonexistent_xyz_module__")
    assert result is False


# ---------------------------------------------------------------------------
# Integration: delegates to prompt_source_reloader.reload_if_stale
# ---------------------------------------------------------------------------

def test_delegates_to_reload_if_stale():
    """reload_prompt_source_if_changed delegates to prompt_source_reloader.reload_if_stale."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload import reload_prompt_source_if_changed

    call_log: list[str] = []

    def fake_reload_if_stale(name: str) -> bool:
        call_log.append(name)
        return False

    with patch.object(_reloader, "reload_if_stale", side_effect=fake_reload_if_stale):
        reload_prompt_source_if_changed("bob3.superpowers")

    assert call_log == ["bob3.superpowers"]
