"""Tests for BF-8 Part B — extended_thinking toggle (classify_feature_thinking)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from bob3.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    EXTENDED_THINKING_DEFAULT,
    classify_feature_thinking,
    get_extended_thinking_setting,
    thinking_kwargs,
)


# ---------------------------------------------------------------------------
# classify_feature_thinking — explicit overrides
# ---------------------------------------------------------------------------


def test_explicit_true_forces_on():
    result = classify_feature_thinking(
        feature_name="rename something",
        extended_thinking=True,
    )
    assert result is True


def test_explicit_false_forces_off():
    result = classify_feature_thinking(
        feature_name="complex multi-file refactor",
        extended_thinking=False,
    )
    assert result is False


# ---------------------------------------------------------------------------
# classify_feature_thinking — auto/None classifier (OFF branch)
# ---------------------------------------------------------------------------


def test_auto_off_for_rename_single_file():
    result = classify_feature_thinking(
        feature_name="rename the FooBar class",
        num_files=1,
        extended_thinking="auto",
    )
    assert result is False


def test_auto_off_for_doc_update():
    result = classify_feature_thinking(
        feature_name="update doc strings",
        num_files=1,
        extended_thinking=None,
    )
    assert result is False


def test_auto_off_for_typo_fix():
    result = classify_feature_thinking(
        feature_name="fix typo in README",
        num_files=1,
        extended_thinking=None,
    )
    assert result is False


def test_auto_off_for_format_change():
    result = classify_feature_thinking(
        feature_name="format all Python files",
        num_files=1,
        extended_thinking="auto",
    )
    assert result is False


# ---------------------------------------------------------------------------
# classify_feature_thinking — auto classifier (ON branch)
# ---------------------------------------------------------------------------


def test_auto_on_for_many_files():
    result = classify_feature_thinking(
        feature_name="some minor task",
        num_files=4,
        extended_thinking="auto",
    )
    assert result is True


def test_auto_on_for_low_spec_quality():
    result = classify_feature_thinking(
        feature_name="something simple",
        spec_quality=0.70,
        extended_thinking=None,
    )
    assert result is True


def test_auto_on_for_retry():
    result = classify_feature_thinking(
        feature_name="simple task",
        retry_count=1,
        extended_thinking=None,
    )
    assert result is True


def test_auto_on_for_refactor_keyword():
    result = classify_feature_thinking(
        feature_name="refactor the authentication module",
        num_files=2,
        extended_thinking="auto",
    )
    assert result is True


def test_auto_on_for_migration_keyword():
    result = classify_feature_thinking(
        feature_name="database migration to new schema",
        extended_thinking="auto",
    )
    assert result is True


def test_auto_on_for_bugfix_keyword():
    result = classify_feature_thinking(
        feature_name="bugfix in payment handler",
        extended_thinking=None,
    )
    assert result is True


def test_auto_on_for_integration_keyword():
    result = classify_feature_thinking(
        feature_name="integration with external API",
        extended_thinking="auto",
    )
    assert result is True


# ---------------------------------------------------------------------------
# classify_feature_thinking — default fallback
# ---------------------------------------------------------------------------


def test_defaults_to_extended_thinking_default_when_no_signals():
    result = classify_feature_thinking(
        feature_name="some neutral thing",
        num_files=2,
        spec_quality=0.90,
        retry_count=0,
        extended_thinking=None,
    )
    assert result == EXTENDED_THINKING_DEFAULT


# ---------------------------------------------------------------------------
# thinking_kwargs
# ---------------------------------------------------------------------------


def test_thinking_kwargs_enabled_returns_type_enabled():
    kwargs = thinking_kwargs(True)
    assert kwargs.get("type") == "enabled"
    assert "budget_tokens" in kwargs


def test_thinking_kwargs_disabled_returns_empty_dict():
    kwargs = thinking_kwargs(False)
    assert kwargs == {}


# ---------------------------------------------------------------------------
# get_extended_thinking_setting
# ---------------------------------------------------------------------------


def test_get_extended_thinking_setting_reads_settings_json(tmp_path, monkeypatch):
    settings = {"extended_thinking_default": False}
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(settings))
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result is False


def test_get_extended_thinking_setting_true_from_file(tmp_path, monkeypatch):
    settings = {"extended_thinking_default": True}
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(settings))
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result is True


def test_get_extended_thinking_setting_fallback_when_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result == EXTENDED_THINKING_DEFAULT


def test_get_extended_thinking_setting_fallback_on_invalid_json(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("not valid json")
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result == EXTENDED_THINKING_DEFAULT


def test_get_extended_thinking_setting_fallback_when_field_missing(tmp_path, monkeypatch):
    settings = {"other_setting": 42}
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(settings))
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result == EXTENDED_THINKING_DEFAULT


# ---------------------------------------------------------------------------
# EXTENDED_THINKING_DEFAULT constant
# ---------------------------------------------------------------------------


def test_extended_thinking_default_is_true():
    assert EXTENDED_THINKING_DEFAULT is True
