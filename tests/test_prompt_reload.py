"""Tests for bob.prompt_reload.reload_if_modified (feature 2ce973a8).

Verifies the hot-reload behaviour: mtime tracking, reload triggering,
error validation, and idempotency.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


def test_module_importable():
    """bob.prompt_reload is importable."""
    import bob.prompt_reload  # noqa: F401 — import test


def test_reload_if_modified_importable():
    """bob.prompt_reload.reload_if_modified is importable and callable."""
    from bob.prompt_reload import reload_if_modified

    assert callable(reload_if_modified)


# ---------------------------------------------------------------------------
# Normal / boundary behaviour
# ---------------------------------------------------------------------------


def test_reload_if_modified_returns_bool_for_real_module():
    """reload_if_modified returns a bool when called on a known module."""
    from bob.prompt_reload import reload_if_modified

    result = reload_if_modified("bob.prompt_reload")
    assert isinstance(result, bool)


def test_reload_if_modified_returns_false_first_call():
    """First call on a module returns False (records mtime, does not reload)."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reload import reload_if_modified

    # Reset state for this module name so the first-call branch runs.
    mod_name = "bob.__test_first_call_prompt_reload__"
    _reloader._MTIME_CACHE.pop(mod_name, None)

    # An unknown/unimportable module → mtime is None → returns False.
    result = reload_if_modified(mod_name)
    assert result is False


def test_reload_if_modified_returns_false_when_unchanged(tmp_path):
    """reload_if_modified returns False on the second call when mtime is unchanged."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reload import reload_if_modified

    # Use a dummy module backed by a real file.
    src = tmp_path / "dummy_mod_unchanged.py"
    src.write_text("VALUE = 1\n")

    mod_name = "bob.__dummy_unchanged__"
    spec = importlib.util.spec_from_file_location(mod_name, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)

    try:
        # First call: seeds the cache.
        _reloader._MTIME_CACHE.pop(mod_name, None)
        r1 = reload_if_modified(mod_name)
        assert r1 is False  # seed call, no reload

        # Second call: mtime unchanged → False.
        r2 = reload_if_modified(mod_name)
        assert r2 is False
    finally:
        sys.modules.pop(mod_name, None)
        _reloader._MTIME_CACHE.pop(mod_name, None)


def test_reload_if_modified_triggers_reload_on_mtime_change(tmp_path):
    """reload_if_modified calls importlib.reload when the source mtime increases."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reload import reload_if_modified
    import time

    src = tmp_path / "dummy_mod_changed.py"
    src.write_text("VALUE = 1\n")

    mod_name = "bob.__dummy_changed__"
    spec = importlib.util.spec_from_file_location(mod_name, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)

    try:
        _reloader._MTIME_CACHE.pop(mod_name, None)
        # Seed: first call records mtime, does not reload.
        reload_if_modified(mod_name)

        # Advance mtime.
        time.sleep(0.01)
        src.write_text("VALUE = 2\n")

        # Mock importlib.reload so the call succeeds (avoids spec-not-found error
        # for dynamically created modules).
        with patch("importlib.reload", return_value=None):
            result = reload_if_modified(mod_name)

        assert result is True
    finally:
        sys.modules.pop(mod_name, None)
        _reloader._MTIME_CACHE.pop(mod_name, None)


def test_reload_if_modified_missing_module_returns_false():
    """reload_if_modified returns False (not raises) for an unimportable module."""
    from bob.prompt_reload import reload_if_modified

    result = reload_if_modified("bob.__totally_nonexistent_xyz_abc__")
    assert result is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_reload_if_modified_raises_value_error_on_int():
    """reload_if_modified raises ValueError when module_name is an int."""
    from bob.prompt_reload import reload_if_modified

    with pytest.raises(ValueError):
        reload_if_modified(42)  # type: ignore[arg-type]


def test_reload_if_modified_raises_value_error_on_none():
    """reload_if_modified raises ValueError when module_name is None."""
    from bob.prompt_reload import reload_if_modified

    with pytest.raises(ValueError):
        reload_if_modified(None)  # type: ignore[arg-type]


def test_reload_if_modified_raises_value_error_on_list():
    """reload_if_modified raises ValueError when module_name is a list."""
    from bob.prompt_reload import reload_if_modified

    with pytest.raises(ValueError):
        reload_if_modified(["bob.superpowers"])  # type: ignore[arg-type]


def test_reload_if_modified_empty_string_does_not_reload():
    """Empty string module_name does not cause a spurious True return."""
    from bob.prompt_reload import reload_if_modified

    try:
        result = reload_if_modified("")
        assert result is False
    except (ValueError, TypeError):
        pass  # Raising is also acceptable.


# ---------------------------------------------------------------------------
# Integration: delegates to prompt_source_reloader.reload_if_stale
# ---------------------------------------------------------------------------


def test_reload_if_modified_delegates_to_reloader():
    """reload_if_modified delegates to prompt_source_reloader.reload_if_stale."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reload import reload_if_modified

    with patch.object(_reloader, "reload_if_stale", return_value=True) as mock_fn:
        result = reload_if_modified("bob.superpowers")

    mock_fn.assert_called_once_with("bob.superpowers")
    assert result is True


def test_reload_if_modified_default_module_is_superpowers():
    """Default module_name argument is 'bob.superpowers'."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reload import reload_if_modified

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_if_modified()

    mock_fn.assert_called_once_with("bob.superpowers")
