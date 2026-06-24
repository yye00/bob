"""Tests for AC-5: prompt_source_reloader detects mtime changes and reloads.

Feature: 5899f432-0bfd-47e1-a776-d144d6e13212
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import patch

import pytest

import bob.orchestrator.prompt_source_reloader as reloader_mod
from bob.orchestrator.prompt_source_reloader import reload_if_stale, _MTIME_CACHE


@pytest.fixture(autouse=True)
def clear_mtime_cache():
    """Reset the global mtime cache between tests."""
    _MTIME_CACHE.clear()
    yield
    _MTIME_CACHE.clear()


def _make_fake_module(name: str, mtime: float) -> types.ModuleType:
    """Create a fake module with a fake __file__ that has a known mtime."""
    mod = types.ModuleType(name)
    mod.__file__ = f"/fake/path/{name.replace('.', '/')}.py"
    return mod


class TestPromptReloaderPicksUpMtimeChange:
    """reload_if_stale triggers importlib.reload when mtime changes."""

    def test_reload_triggered_on_mtime_change(self, tmp_path):
        """reload_if_stale returns True and calls reload when mtime changes."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("VERIFICATION_PROMPT_SECTION = 'v1'\n")
        first_mtime = src_file.stat().st_mtime

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        reload_calls = []

        def fake_reload(m):
            reload_calls.append(m.__name__)
            return m

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", side_effect=fake_reload):
                # First call: seeds the cache, no reload.
                result1 = reload_if_stale("bob.superpowers")
                assert result1 is False
                assert len(reload_calls) == 0

                # Simulate file change by advancing mtime.
                import time
                time.sleep(0.01)
                src_file.write_text("VERIFICATION_PROMPT_SECTION = 'v2'\n")

                # Second call: detects mtime change, triggers reload.
                result2 = reload_if_stale("bob.superpowers")
                assert result2 is True
                assert "bob.superpowers" in reload_calls

    def test_cache_updated_after_reload(self, tmp_path):
        """After a reload, _MTIME_CACHE is updated to the new mtime."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("X = 1\n")

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", return_value=mod):
                reload_if_stale("bob.superpowers")
                old_mtime = _MTIME_CACHE.get("bob.superpowers")

                import time
                time.sleep(0.01)
                src_file.write_text("X = 2\n")

                reload_if_stale("bob.superpowers")
                new_mtime = _MTIME_CACHE.get("bob.superpowers")

                assert new_mtime is not None
                assert old_mtime is not None
                assert new_mtime > old_mtime

    def test_reload_count_matches_change_count(self, tmp_path):
        """Exactly one reload per mtime change, not per call."""
        src_file = tmp_path / "superpowers.py"
        src_file.write_text("X = 1\n")

        mod = types.ModuleType("bob.superpowers")
        mod.__file__ = str(src_file)

        reload_count = [0]

        def counting_reload(m):
            reload_count[0] += 1
            return m

        with patch.dict(sys.modules, {"bob.superpowers": mod}):
            with patch.object(importlib, "reload", side_effect=counting_reload):
                reload_if_stale("bob.superpowers")  # seeds cache

                # Two calls with no file change → no reloads
                reload_if_stale("bob.superpowers")
                reload_if_stale("bob.superpowers")
                assert reload_count[0] == 0

                import time
                time.sleep(0.01)
                src_file.write_text("X = 2\n")

                # One file change → one reload
                reload_if_stale("bob.superpowers")
                assert reload_count[0] == 1

                # Subsequent calls with same mtime → no additional reloads
                reload_if_stale("bob.superpowers")
                assert reload_count[0] == 1
