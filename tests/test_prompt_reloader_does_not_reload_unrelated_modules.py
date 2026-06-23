"""Tests for AC-9: prompt_source_reloader does not reload modules outside the watchlist.

Feature: 5899f432-0bfd-47e1-a776-d144d6e13212
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import patch

import pytest

import bob3.orchestrator.prompt_source_reloader as reloader_mod
from bob3.orchestrator.prompt_source_reloader import (
    maybe_reload_all,
    reload_if_stale,
    _MTIME_CACHE,
    _PROMPT_SOURCE_MODULES,
)


@pytest.fixture(autouse=True)
def clear_mtime_cache():
    _MTIME_CACHE.clear()
    yield
    _MTIME_CACHE.clear()


class TestPromptReloaderDoesNotReloadUnrelatedModules:
    """maybe_reload_all only watches the declared _PROMPT_SOURCE_MODULES list."""

    def test_watchlist_contains_superpowers_and_models(self):
        """_PROMPT_SOURCE_MODULES includes both bob3.superpowers and bob3.models."""
        assert "bob3.superpowers" in _PROMPT_SOURCE_MODULES
        assert "bob3.models" in _PROMPT_SOURCE_MODULES

    def test_maybe_reload_all_does_not_touch_unrelated_module(self, tmp_path):
        """maybe_reload_all never calls reload on a module not in the watchlist."""
        unrelated_src = tmp_path / "unrelated.py"
        unrelated_src.write_text("X = 1\n")

        unrelated_mod = types.ModuleType("bob3._unrelated_test_module_xyz")
        unrelated_mod.__file__ = str(unrelated_src)

        reload_calls: list[str] = []

        def tracking_reload(m):
            reload_calls.append(m.__name__)
            return m

        with patch.dict(sys.modules, {"bob3._unrelated_test_module_xyz": unrelated_mod}):
            with patch.object(importlib, "reload", side_effect=tracking_reload):
                # Seed the mtime for the unrelated module manually
                _MTIME_CACHE["bob3._unrelated_test_module_xyz"] = 1.0

                # Change the file's mtime via rewrite
                import time
                time.sleep(0.01)
                unrelated_src.write_text("X = 2\n")

                # maybe_reload_all should not reload the unrelated module
                reloaded = maybe_reload_all()

        assert "bob3._unrelated_test_module_xyz" not in reloaded
        assert "bob3._unrelated_test_module_xyz" not in reload_calls

    def test_reload_if_stale_is_independent_per_module(self, tmp_path):
        """reload_if_stale for one module does not affect another module's cache."""
        src_a = tmp_path / "mod_a.py"
        src_b = tmp_path / "mod_b.py"
        src_a.write_text("A = 1\n")
        src_b.write_text("B = 1\n")

        mod_a = types.ModuleType("bob3._test_mod_a")
        mod_a.__file__ = str(src_a)
        mod_b = types.ModuleType("bob3._test_mod_b")
        mod_b.__file__ = str(src_b)

        with patch.dict(sys.modules, {
            "bob3._test_mod_a": mod_a,
            "bob3._test_mod_b": mod_b,
        }):
            with patch.object(importlib, "reload", return_value=mod_a):
                reload_if_stale("bob3._test_mod_a")
                # mod_b's cache should not be set by the above call
                assert "bob3._test_mod_b" not in _MTIME_CACHE

    def test_maybe_reload_all_only_covers_watchlist_modules(self, tmp_path):
        """maybe_reload_all only checks modules in _PROMPT_SOURCE_MODULES."""
        checked_modules: list[str] = []
        original_reload_if_stale = reloader_mod.reload_if_stale

        def tracking_reload_if_stale(module_name: str) -> bool:
            checked_modules.append(module_name)
            return False

        with patch.object(reloader_mod, "reload_if_stale", side_effect=tracking_reload_if_stale):
            maybe_reload_all()

        # Every checked module must be in the watchlist
        for mod_name in checked_modules:
            assert mod_name in _PROMPT_SOURCE_MODULES, (
                f"{mod_name!r} was checked but is not in _PROMPT_SOURCE_MODULES"
            )
        # Every watchlist module must have been checked
        for mod_name in _PROMPT_SOURCE_MODULES:
            assert mod_name in checked_modules, (
                f"{mod_name!r} is in _PROMPT_SOURCE_MODULES but was not checked"
            )
