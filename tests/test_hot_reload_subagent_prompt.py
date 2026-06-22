"""Tests for bob3.hot_reload_subagent_prompt (feature f417f178).

Verifies that reload_prompt_source_if_changed correctly delegates to the
prompt_source_reloader and handles stale/fresh module states.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def test_module_exists():
    """src/bob3/hot_reload_subagent_prompt.py is importable."""
    import bob3.hot_reload_subagent_prompt  # noqa: F401


def test_function_defined():
    """reload_prompt_source_if_changed is defined in the module."""
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    assert callable(reload_prompt_source_if_changed)


def test_default_module_name_is_superpowers():
    """Default module_name targets bob3.superpowers."""
    import inspect
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    sig = inspect.signature(reload_prompt_source_if_changed)
    default = sig.parameters["module_name"].default
    assert default == "bob3.superpowers"


def test_returns_bool():
    """reload_prompt_source_if_changed returns a bool."""
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    result = reload_prompt_source_if_changed()
    assert isinstance(result, bool)


def test_returns_false_when_no_change():
    """Returns False when the module has not changed since last call."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_reload:
        result = reload_prompt_source_if_changed("bob3.superpowers")

    assert result is False
    mock_reload.assert_called_once_with("bob3.superpowers")


def test_returns_true_when_module_is_stale():
    """Returns True when the underlying reloader detects a changed mtime."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=True) as mock_reload:
        result = reload_prompt_source_if_changed("bob3.superpowers")

    assert result is True
    mock_reload.assert_called_once_with("bob3.superpowers")


def test_delegates_to_prompt_source_reloader():
    """reload_prompt_source_if_changed delegates to prompt_source_reloader.reload_if_stale."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    custom_module = "bob3.models"
    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_reload:
        reload_prompt_source_if_changed(custom_module)

    mock_reload.assert_called_once_with(custom_module)


def test_raises_value_error_on_non_string():
    """Passing a non-string raises ValueError."""
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(42)  # type: ignore[arg-type]


def test_raises_value_error_on_none():
    """Passing None raises ValueError."""
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(None)  # type: ignore[arg-type]


def test_unknown_module_returns_false():
    """An unimportable module name returns False, not raises."""
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    result = reload_prompt_source_if_changed("bob3.__nonexistent_xyz_module__")
    assert result is False


def test_multiple_calls_stable():
    """Multiple calls with no file changes consistently return False after first call."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.hot_reload_subagent_prompt import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        results = [reload_prompt_source_if_changed() for _ in range(3)]

    assert all(r is False for r in results)
