"""Tests for AC-7: prompt_source_reloader handles missing/unimportable files gracefully.

Feature: 5899f432-0bfd-47e1-a776-d144d6e13212
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from bob.orchestrator.prompt_source_reloader import (
    get_prompt_mtime,
    reload_if_stale,
    _MTIME_CACHE,
)


@pytest.fixture(autouse=True)
def clear_mtime_cache():
    _MTIME_CACHE.clear()
    yield
    _MTIME_CACHE.clear()


class TestPromptReloaderHandlesMissingFile:
    """reload_if_stale and get_prompt_mtime survive missing/unimportable modules."""

    def test_get_prompt_mtime_returns_none_for_nonexistent_module(self):
        """get_prompt_mtime returns None when module cannot be imported."""
        result = get_prompt_mtime("bob.this_module_does_not_exist_xyz_987")
        assert result is None

    def test_reload_if_stale_returns_false_for_missing_module(self):
        """reload_if_stale returns False (not raises) when module is not importable."""
        result = reload_if_stale("bob.totally_nonexistent_module_abc_123")
        assert result is False

    def test_reload_if_stale_returns_false_when_file_deleted_after_seed(self, tmp_path):
        """If a file disappears after the cache is seeded, reload_if_stale returns False."""
        import types

        src_file = tmp_path / "vanishing.py"
        src_file.write_text("X = 1\n")

        mod = types.ModuleType("bob._vanishing_test_mod")
        mod.__file__ = str(src_file)

        with patch.dict(sys.modules, {"bob._vanishing_test_mod": mod}):
            # Seed the cache with the file present
            result1 = reload_if_stale("bob._vanishing_test_mod")
            assert result1 is False

            # Delete the file — stat will now raise OSError
            src_file.unlink()

            # Should return False, not raise
            result2 = reload_if_stale("bob._vanishing_test_mod")
            assert result2 is False

    def test_get_prompt_mtime_returns_none_when_module_has_no_file_attr(self):
        """get_prompt_mtime returns None for a built-in module with no __file__."""
        import types

        mod = types.ModuleType("_fake_built_in_xyz")
        # No __file__ set → get_prompt_mtime should return None
        with patch.dict(sys.modules, {"_fake_built_in_xyz": mod}):
            result = get_prompt_mtime("_fake_built_in_xyz")
            assert result is None

    def test_reload_if_stale_does_not_raise_on_import_error(self):
        """reload_if_stale returns False when importlib.import_module raises."""
        import importlib
        from unittest.mock import patch as _patch

        def bad_import(name):
            raise ImportError(f"fake import error for {name}")

        with _patch.dict(sys.modules, {}):
            with _patch.object(importlib, "import_module", side_effect=bad_import):
                result = reload_if_stale("bob._import_error_test")
                assert result is False
