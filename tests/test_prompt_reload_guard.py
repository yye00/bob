"""Tests for bob3.prompt_reload_guard — feature 43aa5d71.

Verifies that reload_prompt_source_if_changed delegates correctly to
bob3.orchestrator.prompt_source_reloader and enforces its contract.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch


def test_module_importable():
    """bob3.prompt_reload_guard is importable."""
    import bob3.prompt_reload_guard  # noqa: F401


def test_reload_prompt_source_if_changed_exists():
    """reload_prompt_source_if_changed is defined in bob3.prompt_reload_guard."""
    from bob3.prompt_reload_guard import reload_prompt_source_if_changed

    assert callable(reload_prompt_source_if_changed)


def test_reload_prompt_sources_exists():
    """reload_prompt_sources is defined in bob3.prompt_reload_guard."""
    from bob3.prompt_reload_guard import reload_prompt_sources

    assert callable(reload_prompt_sources)


def test_reload_prompt_source_if_changed_returns_bool_for_known_module():
    """reload_prompt_source_if_changed returns a bool for a known module."""
    from bob3.prompt_reload_guard import reload_prompt_source_if_changed

    result = reload_prompt_source_if_changed("bob3.orchestrator.prompt_source_reloader")
    assert isinstance(result, bool)


def test_reload_prompt_source_if_changed_returns_false_for_unknown_module():
    """reload_prompt_source_if_changed returns False for an unknown module (no raise)."""
    from bob3.prompt_reload_guard import reload_prompt_source_if_changed

    result = reload_prompt_source_if_changed("bob3.__nonexistent_guard_test_module__")
    assert result is False


def test_reload_prompt_source_if_changed_raises_on_non_string():
    """reload_prompt_source_if_changed raises ValueError when given a non-string."""
    from bob3.prompt_reload_guard import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(42)  # type: ignore[arg-type]


def test_reload_prompt_source_if_changed_raises_on_none():
    """reload_prompt_source_if_changed raises ValueError when given None."""
    from bob3.prompt_reload_guard import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(None)  # type: ignore[arg-type]


def test_reload_prompt_sources_returns_list():
    """reload_prompt_sources returns a list."""
    from bob3.prompt_reload_guard import reload_prompt_sources

    result = reload_prompt_sources()
    assert isinstance(result, list)


def test_reload_prompt_sources_delegates_to_reloader():
    """reload_prompt_sources delegates to prompt_source_reloader.maybe_reload_all."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.prompt_reload_guard import reload_prompt_sources

    with patch.object(_reloader, "maybe_reload_all", return_value=["bob3.superpowers"]) as mock:
        result = reload_prompt_sources()

    mock.assert_called_once()
    assert result == ["bob3.superpowers"]


def test_reload_prompt_source_if_changed_delegates_to_reloader():
    """reload_prompt_source_if_changed delegates to prompt_source_reloader.reload_if_stale."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.prompt_reload_guard import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=True) as mock:
        result = reload_prompt_source_if_changed("bob3.superpowers")

    mock.assert_called_once_with("bob3.superpowers")
    assert result is True


def test_reload_prompt_source_if_changed_default_module():
    """reload_prompt_source_if_changed defaults to bob3.superpowers."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.prompt_reload_guard import reload_prompt_source_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock:
        reload_prompt_source_if_changed()

    mock.assert_called_once_with("bob3.superpowers")


def test_reload_prompt_sources_returns_empty_when_no_changes():
    """reload_prompt_sources returns [] when no modules have changed mtime."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.prompt_reload_guard import reload_prompt_sources

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_sources()

    assert result == []
