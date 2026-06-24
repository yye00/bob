"""Tests for bob.orchestrator.reload_prompt_source_if_changed (feature e1bb8261).

Verifies that hot-reload of prompt-source modules works correctly when accessed
through the bob.orchestrator namespace, so code-fixes to superpowers.py land
without an orchestrator restart.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Importability and callable contract via bob.orchestrator
# ---------------------------------------------------------------------------


def test_reload_prompt_source_if_changed_importable_from_orchestrator():
    """reload_prompt_source_if_changed must be importable from bob.orchestrator."""
    from bob.orchestrator import reload_prompt_source_if_changed  # noqa: F401


def test_reload_prompt_source_if_changed_is_callable_via_orchestrator():
    """reload_prompt_source_if_changed imported from bob.orchestrator must be callable."""
    from bob.orchestrator import reload_prompt_source_if_changed

    assert callable(reload_prompt_source_if_changed)


def test_reload_prompt_source_if_changed_returns_bool_via_orchestrator():
    """reload_prompt_source_if_changed must return a bool."""
    from bob.orchestrator import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed()

    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Default module is bob.superpowers
# ---------------------------------------------------------------------------


def test_default_module_is_superpowers():
    """Default module_name must be bob.superpowers."""
    from bob.orchestrator import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    called_with: list[str] = []

    def capture(module_name: str) -> bool:
        called_with.append(module_name)
        return False

    with patch.object(_reloader, "reload_if_stale", side_effect=capture):
        reload_prompt_source_if_changed()

    assert called_with == ["bob.superpowers"]


# ---------------------------------------------------------------------------
# Delegates to prompt_source_reloader.reload_if_stale
# ---------------------------------------------------------------------------


def test_delegates_to_reload_if_stale():
    """reload_prompt_source_if_changed must call reload_if_stale exactly once."""
    from bob.orchestrator import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_prompt_source_if_changed("bob.superpowers")

    mock_fn.assert_called_once_with("bob.superpowers")


def test_explicit_module_name_forwarded():
    """An explicit module_name is forwarded to reload_if_stale."""
    from bob.orchestrator import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=True) as mock_fn:
        result = reload_prompt_source_if_changed("bob.models")

    mock_fn.assert_called_once_with("bob.models")
    assert result is True


# ---------------------------------------------------------------------------
# Return value reflects whether a reload occurred
# ---------------------------------------------------------------------------


def test_returns_true_when_reload_performed():
    """Returns True when reload_if_stale reports a reload was performed."""
    from bob.orchestrator import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=True):
        result = reload_prompt_source_if_changed()

    assert result is True


def test_returns_false_when_unchanged():
    """Returns False when the module is already up-to-date."""
    from bob.orchestrator import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed()

    assert result is False


def test_returns_false_for_missing_module():
    """Returns False when the module file cannot be found."""
    from bob.orchestrator import reload_prompt_source_if_changed
    import bob.orchestrator.prompt_source_reloader as _reloader

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_source_if_changed("bob.nonexistent_module_xyz")

    assert result is False


# ---------------------------------------------------------------------------
# mtime-based reload detection (integration with reloader internals)
# ---------------------------------------------------------------------------


def test_detects_mtime_change():
    """Returns True when the on-disk mtime has increased since last check."""
    from bob.orchestrator import reload_prompt_source_if_changed
    from bob.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()

        # First call establishes the baseline — never reloads on first observation.
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


def test_no_reload_when_mtime_stable():
    """Does not reload when mtime has not changed between calls."""
    from bob.orchestrator import reload_prompt_source_if_changed
    from bob.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()

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
# Orchestrator integration — reloader module is wired correctly
# ---------------------------------------------------------------------------


def test_orchestrator_exposes_maybe_reload_all():
    """maybe_reload_all must also be importable from bob.orchestrator."""
    from bob.orchestrator import maybe_reload_all  # noqa: F401

    assert callable(maybe_reload_all)


def test_prompt_source_modules_includes_superpowers():
    """The watched module list must include bob.superpowers."""
    from bob.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob.superpowers" in _PROMPT_SOURCE_MODULES


def test_prompt_source_modules_includes_models():
    """The watched module list must include bob.models."""
    from bob.orchestrator.prompt_source_reloader import _PROMPT_SOURCE_MODULES

    assert "bob.models" in _PROMPT_SOURCE_MODULES


def test_no_exception_on_normal_call():
    """reload_prompt_source_if_changed must not raise under normal conditions."""
    from bob.orchestrator import reload_prompt_source_if_changed

    result = reload_prompt_source_if_changed()
    assert isinstance(result, bool)


def test_idempotent_consecutive_calls():
    """Consecutive calls with no file change return False after the first."""
    from bob.orchestrator import reload_prompt_source_if_changed
    from bob.orchestrator import prompt_source_reloader

    original_cache = dict(prompt_source_reloader._MTIME_CACHE)
    try:
        prompt_source_reloader._MTIME_CACHE.clear()

        # Establish baseline
        reload_prompt_source_if_changed("bob.superpowers")
        mtime = prompt_source_reloader._MTIME_CACHE.get("bob.superpowers", 0.0)

        with patch.object(prompt_source_reloader, "get_prompt_mtime", return_value=mtime):
            r1 = reload_prompt_source_if_changed("bob.superpowers")
            r2 = reload_prompt_source_if_changed("bob.superpowers")

        assert r1 is False
        assert r2 is False
    finally:
        prompt_source_reloader._MTIME_CACHE.clear()
        prompt_source_reloader._MTIME_CACHE.update(original_cache)
