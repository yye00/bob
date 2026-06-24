"""Tests for bob.subagent_prompt_reloader.

Feature: 0f3f0691-e526-41a5-ba81-6f9e71f84c5d
AC: pytest: tests/test_subagent_prompt_reloader.py
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Importability
# ---------------------------------------------------------------------------


def test_module_importable():
    """The feature module must be importable."""
    import bob.subagent_prompt_reloader  # noqa: F401


def test_function_importable():
    """reload_prompt_sources_if_changed must be importable from the feature module."""
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    assert callable(reload_prompt_sources_if_changed)


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


def test_reload_prompt_sources_if_changed_returns_list():
    """reload_prompt_sources_if_changed must return a list."""
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    result = reload_prompt_sources_if_changed()
    assert isinstance(result, list)


def test_reload_prompt_sources_if_changed_returns_empty_when_no_changes():
    """Returns [] when no watched modules have changed mtime."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_sources_if_changed()

    assert result == []


def test_reload_prompt_sources_if_changed_returns_module_names_when_changed():
    """Returns list of reloaded module names when mtime change detected."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    with patch.object(_reloader, "maybe_reload_all", return_value=["bob.superpowers"]):
        result = reload_prompt_sources_if_changed()

    assert result == ["bob.superpowers"]


def test_delegates_to_maybe_reload_all():
    """reload_prompt_sources_if_changed must delegate to maybe_reload_all."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    with patch.object(_reloader, "maybe_reload_all", return_value=[]) as mock_fn:
        reload_prompt_sources_if_changed()

    mock_fn.assert_called_once()


def test_reload_prompt_sources_if_changed_result_contains_only_strings():
    """All entries in returned list must be strings (module names)."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    with patch.object(
        _reloader,
        "maybe_reload_all",
        return_value=["bob.superpowers", "bob.models"],
    ):
        result = reload_prompt_sources_if_changed()

    assert all(isinstance(name, str) for name in result)


def test_reload_prompt_sources_if_changed_idempotent_no_changes():
    """Repeated calls with no mtime changes consistently return []."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        r1 = reload_prompt_sources_if_changed()
        r2 = reload_prompt_sources_if_changed()
        r3 = reload_prompt_sources_if_changed()

    assert r1 == r2 == r3 == []


def test_reload_prompt_sources_if_changed_callable_with_no_args():
    """reload_prompt_sources_if_changed must accept zero arguments."""
    from bob.subagent_prompt_reloader import reload_prompt_sources_if_changed

    # Must not raise TypeError for zero-arg call.
    result = reload_prompt_sources_if_changed()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Integration: orchestrator wires reload before dispatch
# ---------------------------------------------------------------------------


def test_orchestrator_reload_prompt_sources_if_changed_importable():
    """bob.orchestrator must expose reload_prompt_sources_if_changed."""
    from bob.orchestrator import reload_prompt_sources_if_changed  # noqa: F401

    assert callable(reload_prompt_sources_if_changed)


def test_subagent_prompt_reloader_in_all():
    """reload_prompt_sources_if_changed must be listed in __all__."""
    import bob.subagent_prompt_reloader as mod

    assert "reload_prompt_sources_if_changed" in mod.__all__
