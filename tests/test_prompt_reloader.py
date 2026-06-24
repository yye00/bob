"""Tests for bob.prompt_reloader (feature 20f0c750).

Covers the public reload_if_modified API and its delegation to the
underlying prompt_source_reloader.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch


def test_module_is_importable():
    """bob.prompt_reloader is importable."""
    import bob.prompt_reloader  # noqa: F401


def test_reload_if_modified_is_callable():
    """reload_if_modified exists and is callable."""
    from bob.prompt_reloader import reload_if_modified

    assert callable(reload_if_modified)


def test_reload_if_modified_returns_bool_when_not_stale():
    """reload_if_modified returns False when module is up-to-date."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reloader import reload_if_modified

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        result = reload_if_modified("bob.superpowers")

    assert result is False
    mock_fn.assert_called_once_with("bob.superpowers")


def test_reload_if_modified_returns_true_when_stale():
    """reload_if_modified returns True when the module was reloaded."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reloader import reload_if_modified

    with patch.object(_reloader, "reload_if_stale", return_value=True) as mock_fn:
        result = reload_if_modified("bob.superpowers")

    assert result is True
    mock_fn.assert_called_once_with("bob.superpowers")


def test_reload_if_modified_default_module_is_superpowers():
    """reload_if_modified uses bob.superpowers as default module."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reloader import reload_if_modified

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        reload_if_modified()

    mock_fn.assert_called_once_with("bob.superpowers")


def test_reload_if_modified_raises_on_non_string():
    """reload_if_modified raises ValueError when module_name is not a string."""
    from bob.prompt_reloader import reload_if_modified

    with pytest.raises(ValueError):
        reload_if_modified(42)  # type: ignore[arg-type]


def test_reload_if_modified_raises_on_none():
    """reload_if_modified raises ValueError when module_name is None."""
    from bob.prompt_reloader import reload_if_modified

    with pytest.raises(ValueError):
        reload_if_modified(None)  # type: ignore[arg-type]


def test_reload_if_modified_accepts_other_module_names():
    """reload_if_modified can check arbitrary module names."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reloader import reload_if_modified

    with patch.object(_reloader, "reload_if_stale", return_value=False) as mock_fn:
        result = reload_if_modified("bob.models")

    assert result is False
    mock_fn.assert_called_once_with("bob.models")


def test_reload_if_modified_returns_false_for_unknown_module():
    """reload_if_modified returns False (not raises) for an unknown module."""
    from bob.prompt_reloader import reload_if_modified

    result = reload_if_modified("bob.__nonexistent_module_20f0c750__")
    assert result is False


def test_reload_if_modified_propagates_import_error():
    """reload_if_modified propagates ImportError from the underlying reloader."""
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.prompt_reloader import reload_if_modified

    with patch.object(_reloader, "reload_if_stale", side_effect=ImportError("boom")):
        with pytest.raises(ImportError):
            reload_if_modified("bob.superpowers")
