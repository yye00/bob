"""Tests for AC-6: prompt_source_reloader skips reload when mtime is unchanged.

Feature: 5899f432-0bfd-47e1-a776-d144d6e13212
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import patch

import pytest

from bob.orchestrator.prompt_source_reloader import reload_if_stale, _MTIME_CACHE


@pytest.fixture(autouse=True)
def clear_mtime_cache():
    _MTIME_CACHE.clear()
    yield
    _MTIME_CACHE.clear()


class TestPromptReloaderSkipsWhenUnchanged:
    """reload_if_stale does NOT call reload when mtime is stable."""

    def test_no_reload_when_mtime_unchanged(self, tmp_path):
        """Multiple calls with same mtime → no reload triggered."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("X = 1\n")

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        reload_calls = []

        def fake_reload(m):
            reload_calls.append(m.__name__)
            return m

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", side_effect=fake_reload):
                # Seed the cache
                reload_if_stale("bob.superpowers")
                # Many calls with no file change
                for _ in range(5):
                    result = reload_if_stale("bob.superpowers")
                    assert result is False

                assert len(reload_calls) == 0

    def test_return_false_when_no_change(self, tmp_path):
        """reload_if_stale returns False when mtime is stable."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("Y = 2\n")

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", return_value=mod):
                reload_if_stale("bob.superpowers")  # seed
                result = reload_if_stale("bob.superpowers")
                assert result is False

    def test_mtime_cache_stable_when_no_change(self, tmp_path):
        """_MTIME_CACHE value is identical across repeated no-change calls."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("Z = 3\n")

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", return_value=mod):
                reload_if_stale("bob.superpowers")
                mtime_after_seed = _MTIME_CACHE.get("bob.superpowers")

                reload_if_stale("bob.superpowers")
                reload_if_stale("bob.superpowers")
                mtime_after_repeats = _MTIME_CACHE.get("bob.superpowers")

                assert mtime_after_seed == mtime_after_repeats
