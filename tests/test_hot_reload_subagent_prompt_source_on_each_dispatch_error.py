"""Error-path tests for hot-reload prompt source on each dispatch (feature 804db4ef).

Verifies that invalid inputs raise ValueError and that the functions do not
silently succeed when given bad arguments.
"""

from __future__ import annotations

import pytest


def test_reload_prompt_sources_not_accepts_positional_args():
    """reload_prompt_sources takes no positional arguments; passing one raises TypeError."""
    from bob.orchestrator import reload_prompt_sources

    with pytest.raises(TypeError):
        reload_prompt_sources("unexpected_arg")  # type: ignore[call-arg]


def test_reload_prompt_source_if_changed_raises_on_non_string_module():
    """reload_prompt_source_if_changed raises ValueError when module_name is not a string."""
    from bob.orchestrator import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(12345)  # type: ignore[arg-type]


def test_reload_prompt_source_if_changed_raises_on_none_module():
    """reload_prompt_source_if_changed raises ValueError when module_name is None."""
    from bob.orchestrator import reload_prompt_source_if_changed

    with pytest.raises(ValueError):
        reload_prompt_source_if_changed(None)  # type: ignore[arg-type]


def test_reload_if_stale_raises_on_non_string_module():
    """reload_if_stale raises ValueError when module_name is not a string."""
    from bob.orchestrator.prompt_source_reloader import reload_if_stale

    with pytest.raises(ValueError):
        reload_if_stale(42)  # type: ignore[arg-type]


def test_reload_if_stale_raises_on_none():
    """reload_if_stale raises ValueError when module_name is None."""
    from bob.orchestrator.prompt_source_reloader import reload_if_stale

    with pytest.raises(ValueError):
        reload_if_stale(None)  # type: ignore[arg-type]


def test_get_prompt_mtime_raises_on_non_string():
    """get_prompt_mtime raises ValueError when module_name is not a string."""
    from bob.orchestrator.prompt_source_reloader import get_prompt_mtime

    with pytest.raises(ValueError):
        get_prompt_mtime(99)  # type: ignore[arg-type]


def test_get_prompt_mtime_raises_on_none():
    """get_prompt_mtime raises ValueError when module_name is None."""
    from bob.orchestrator.prompt_source_reloader import get_prompt_mtime

    with pytest.raises(ValueError):
        get_prompt_mtime(None)  # type: ignore[arg-type]


def test_reload_prompt_source_if_changed_empty_string_does_not_silently_succeed():
    """Passing an empty string for module_name should not silently succeed (return False)."""
    from bob.orchestrator import reload_prompt_source_if_changed

    # Empty string is not a valid dotted module name — must either raise or return False.
    # It must NOT return True (that would mean it silently "succeeded" a reload).
    try:
        result = reload_prompt_source_if_changed("")
        # If no exception, result must be False (module not found → no reload).
        assert result is False, "Empty module name must not cause a reload to succeed"
    except (ValueError, TypeError, AttributeError):
        # Raising is also acceptable — it signals invalid input.
        pass


def test_reload_prompt_sources_does_not_silently_succeed_on_import_error():
    """When the underlying reloader raises ImportError, reload_prompt_sources must not mask it."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.orchestrator import reload_prompt_sources
    from unittest.mock import patch

    # If maybe_reload_all propagates an unexpected ImportError, it should surface.
    with patch.object(_reloader, "maybe_reload_all", side_effect=ImportError("boom")):
        with pytest.raises(ImportError):
            reload_prompt_sources()
