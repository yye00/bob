"""Boundary tests for bob3.orchestrator.reload_prompt_sources (feature 804db4ef).

Verifies that zero-input, empty, and minimum boundary cases return well-defined
results rather than raising an exception.
"""

from __future__ import annotations

from unittest.mock import patch


def test_reload_prompt_sources_returns_list():
    """reload_prompt_sources returns a list (possibly empty) when called normally."""
    from bob3.orchestrator import reload_prompt_sources

    result = reload_prompt_sources()
    assert isinstance(result, list)


def test_reload_prompt_sources_returns_empty_when_no_changes():
    """reload_prompt_sources returns [] when no modules have changed mtime."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.orchestrator import reload_prompt_sources

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        result = reload_prompt_sources()

    assert result == []


def test_reload_prompt_sources_idempotent_on_repeated_calls():
    """Repeated calls with no mtime change consistently return [] after baseline."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.orchestrator import reload_prompt_sources

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        r1 = reload_prompt_sources()
        r2 = reload_prompt_sources()
        r3 = reload_prompt_sources()

    assert r1 == []
    assert r2 == []
    assert r3 == []


def test_reload_prompt_sources_returns_reloaded_names_when_changed():
    """reload_prompt_sources returns module name list when modules are stale."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.orchestrator import reload_prompt_sources

    # Simulate all watched modules being stale.
    with patch.object(_reloader, "reload_if_stale", return_value=True):
        result = reload_prompt_sources()

    # Should contain the watched module names.
    assert isinstance(result, list)
    assert len(result) == len(_reloader._PROMPT_SOURCE_MODULES)


def test_reload_prompt_sources_callable_with_no_args():
    """reload_prompt_sources accepts zero arguments — boundary: minimum call form."""
    from bob3.orchestrator import reload_prompt_sources

    # Must not raise TypeError or any other exception.
    result = reload_prompt_sources()
    assert result is not None


def test_reload_prompt_sources_result_contains_only_strings():
    """Every element in the returned list is a module name string."""
    import bob3.orchestrator.prompt_source_reloader as _reloader
    from bob3.orchestrator import reload_prompt_sources

    with patch.object(_reloader, "reload_if_stale", return_value=True):
        result = reload_prompt_sources()

    for name in result:
        assert isinstance(name, str)
        assert len(name) > 0


def test_reload_if_stale_returns_false_for_unknown_module():
    """reload_if_stale returns False (not raises) for an unknown module name."""
    from bob3.orchestrator.prompt_source_reloader import reload_if_stale

    # An unimportable module should silently return False, not raise.
    result = reload_if_stale("bob3.__nonexistent_boundary_module_xyz__")
    assert result is False


def test_get_prompt_mtime_returns_none_for_missing_module():
    """get_prompt_mtime returns None (not raises) when module cannot be found."""
    from bob3.orchestrator.prompt_source_reloader import get_prompt_mtime

    result = get_prompt_mtime("bob3.__nonexistent_boundary_module_xyz__")
    assert result is None


def test_maybe_reload_all_returns_list():
    """maybe_reload_all returns a list — minimum input boundary."""
    from bob3.orchestrator.prompt_source_reloader import maybe_reload_all

    result = maybe_reload_all()
    assert isinstance(result, list)
