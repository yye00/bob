"""Tests for bob.prompt_hot_reload (feature 9b346569)."""

import importlib
import os
import time

import pytest

from bob import prompt_hot_reload
from bob import superpowers


@pytest.fixture(autouse=True)
def _clear_cache():
    prompt_hot_reload.reset_cache()
    yield
    prompt_hot_reload.reset_cache()


def test_first_call_records_but_does_not_reload():
    # First observation just records the mtime; nothing "changed" yet.
    assert prompt_hot_reload.reload_if_changed(superpowers) is False


def test_reloads_when_source_mtime_advances(tmp_path):
    # Build a real throwaway module on disk so we can bump its mtime.
    mod_path = tmp_path / "hot_reload_probe.py"
    mod_path.write_text("VALUE = 1\n")

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module("hot_reload_probe")
        assert mod.VALUE == 1

        # First call records baseline, no reload.
        assert prompt_hot_reload.reload_if_changed(mod) is False

        # Patch source + advance mtime into the future.
        mod_path.write_text("VALUE = 2\n")
        future = time.time() + 10
        os.utime(mod_path, (future, future))

        assert prompt_hot_reload.reload_if_changed(mod) is True
        assert mod.VALUE == 2

        # Unchanged since last reload -> no second reload.
        assert prompt_hot_reload.reload_if_changed(mod) is False
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("hot_reload_probe", None)


def test_accepts_module_name_string():
    assert prompt_hot_reload.reload_if_changed("bob.superpowers") is False


def test_get_verification_prompt_section_returns_current_text():
    section = superpowers.get_verification_prompt_section()
    assert isinstance(section, str)
    assert section == superpowers.VERIFICATION_PROMPT_SECTION
    assert "Verification Before Completion" in section


def test_get_verification_prompt_section_stable_across_calls():
    a = superpowers.get_verification_prompt_section()
    b = superpowers.get_verification_prompt_section()
    assert a == b
