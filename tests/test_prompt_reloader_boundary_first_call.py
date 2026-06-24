"""Tests for AC-8: prompt_source_reloader boundary — first call seeds cache, no reload.

Feature: 5899f432-0bfd-47e1-a776-d144d6e13212
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import patch

import pytest

from bob.orchestrator.prompt_source_reloader import (
    reload_if_stale,
    get_prompt_mtime,
    maybe_reload_all,
    _MTIME_CACHE,
)


@pytest.fixture(autouse=True)
def clear_mtime_cache():
    _MTIME_CACHE.clear()
    yield
    _MTIME_CACHE.clear()


class TestPromptReloaderBoundaryFirstCall:
    """First call to reload_if_stale seeds the cache without triggering a reload."""

    def test_first_call_does_not_reload(self, tmp_path):
        """reload_if_stale returns False on the very first call (cache seeding)."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("VERIFICATION_PROMPT_SECTION = 'initial'\n")

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        reload_calls = []

        def fake_reload(m):
            reload_calls.append(m.__name__)
            return m

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", side_effect=fake_reload):
                result = reload_if_stale("bob.superpowers")

        assert result is False
        assert len(reload_calls) == 0

    def test_first_call_populates_mtime_cache(self, tmp_path):
        """After the first call, _MTIME_CACHE contains the current mtime."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("X = 1\n")
        expected_mtime = src_file.stat().st_mtime

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", return_value=mod):
                reload_if_stale("bob.superpowers")

        cached = _MTIME_CACHE.get("bob.superpowers")
        assert cached is not None
        assert cached == expected_mtime

    def test_second_call_with_unchanged_file_no_reload(self, tmp_path):
        """Two consecutive calls with no file change → no reload either call."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("Y = 2\n")

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        reload_calls = []

        def fake_reload(m):
            reload_calls.append(m.__name__)
            return m

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", side_effect=fake_reload):
                result1 = reload_if_stale("bob.superpowers")  # seed
                result2 = reload_if_stale("bob.superpowers")  # no change

        assert result1 is False
        assert result2 is False
        assert len(reload_calls) == 0

    def test_maybe_reload_all_first_call_returns_empty(self, tmp_path):
        """maybe_reload_all on first call returns empty list (seeds all caches)."""
        import bob.orchestrator.prompt_source_reloader as reloader_mod

        # Patch get_prompt_mtime to return a fixed value for all modules
        original_get = reloader_mod.get_prompt_mtime

        def fake_mtime(module_name):
            return 1000.0

        with patch.object(reloader_mod, "get_prompt_mtime", side_effect=fake_mtime):
            with patch.object(importlib, "reload"):
                result = maybe_reload_all()

        assert result == []

    def test_empty_cache_means_no_module_in_cache_initially(self):
        """Before any reload_if_stale call, _MTIME_CACHE has no entry."""
        assert "bob.superpowers" not in _MTIME_CACHE
        assert "bob.models" not in _MTIME_CACHE
