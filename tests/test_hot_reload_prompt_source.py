"""Tests for bob.hot_reload_prompt_source (feature e8dbe235).

Verifies the per-dispatch hot-reload facade: reload_if_changed picks up
on-disk patches to prompt-source modules without an orchestrator restart,
and get_prompt_sections returns the current prompt-section text.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_module_importable():
    import bob.hot_reload_prompt_source as m

    assert hasattr(m, "reload_if_changed")
    assert hasattr(m, "get_prompt_sections")


def test_reload_if_changed_returns_bool_default():
    from bob.hot_reload_prompt_source import reload_if_changed

    result = reload_if_changed()
    assert isinstance(result, bool)


def test_reload_if_changed_named_module():
    from bob.hot_reload_prompt_source import reload_if_changed

    result = reload_if_changed("bob.superpowers")
    assert isinstance(result, bool)


def test_reload_if_changed_delegates_to_reloader():
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.hot_reload_prompt_source import reload_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=True) as spy:
        assert reload_if_changed("bob.superpowers") is True
    spy.assert_called_once_with("bob.superpowers")


def test_reload_if_changed_false_when_unchanged():
    import bob.orchestrator.prompt_source_reloader as _reloader
    from bob.hot_reload_prompt_source import reload_if_changed

    with patch.object(_reloader, "reload_if_stale", return_value=False):
        assert reload_if_changed("bob.superpowers") is False


def test_reload_if_changed_raises_on_non_string():
    from bob.hot_reload_prompt_source import reload_if_changed

    with pytest.raises(ValueError):
        reload_if_changed(123)  # type: ignore[arg-type]


def test_reload_if_changed_raises_on_none():
    from bob.hot_reload_prompt_source import reload_if_changed

    with pytest.raises(ValueError):
        reload_if_changed(None)  # type: ignore[arg-type]


def test_reload_if_changed_false_for_unknown_module():
    from bob.hot_reload_prompt_source import reload_if_changed

    assert reload_if_changed("bob.__no_such_module_xyz__") is False


def test_get_prompt_sections_returns_dict():
    from bob.hot_reload_prompt_source import get_prompt_sections

    sections = get_prompt_sections()
    assert isinstance(sections, dict)
    assert len(sections) > 0


def test_get_prompt_sections_contains_verification():
    from bob.hot_reload_prompt_source import get_prompt_sections

    sections = get_prompt_sections()
    assert "VERIFICATION_PROMPT_SECTION" in sections
    assert isinstance(sections["VERIFICATION_PROMPT_SECTION"], str)
    assert sections["VERIFICATION_PROMPT_SECTION"].strip()


def test_get_prompt_sections_all_values_are_strings():
    from bob.hot_reload_prompt_source import get_prompt_sections

    for name, text in get_prompt_sections().items():
        assert isinstance(name, str)
        assert isinstance(text, str)


def test_get_prompt_sections_reflects_reload():
    """get_prompt_sections reads live from the module so a reload is visible."""
    from bob.hot_reload_prompt_source import get_prompt_sections

    before = get_prompt_sections()
    after = get_prompt_sections()
    # Idempotent when nothing changed on disk.
    assert before.keys() == after.keys()


def test_get_prompt_sections_triggers_reload_check():
    """get_prompt_sections calls reload_if_changed before reading sections."""
    import bob.hot_reload_prompt_source as m

    with patch.object(m, "reload_if_changed", return_value=False) as spy:
        m.get_prompt_sections()
    assert spy.called
