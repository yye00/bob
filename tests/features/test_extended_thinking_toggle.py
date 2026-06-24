"""Tests for BF-8 Part B — extended_thinking toggle.

Covers the classify_feature_thinking classifier, thinking_kwargs helper,
and the get_extended_thinking_setting bootstrap reader.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from bob.bf_8_context_budget_pretooluse_hook_extended_thinking_toggle import (
    EXTENDED_THINKING_DEFAULT,
    classify_feature_thinking,
    get_extended_thinking_setting,
    thinking_kwargs,
)


# ---------------------------------------------------------------------------
# thinking_kwargs
# ---------------------------------------------------------------------------


def test_thinking_kwargs_enabled_returns_type_enabled():
    result = thinking_kwargs(True)
    assert result.get("type") == "enabled"


def test_thinking_kwargs_enabled_has_budget_tokens():
    result = thinking_kwargs(True)
    assert "budget_tokens" in result
    assert isinstance(result["budget_tokens"], int)
    assert result["budget_tokens"] > 0


def test_thinking_kwargs_disabled_returns_empty_dict():
    result = thinking_kwargs(False)
    assert result == {}


# ---------------------------------------------------------------------------
# classify_feature_thinking — explicit overrides
# ---------------------------------------------------------------------------


def test_classify_explicit_true_returns_true():
    result = classify_feature_thinking(feature_name="whatever", extended_thinking=True)
    assert result is True


def test_classify_explicit_false_returns_false():
    result = classify_feature_thinking(feature_name="whatever", extended_thinking=False)
    assert result is False


# ---------------------------------------------------------------------------
# classify_feature_thinking — OFF heuristics (auto mode)
# ---------------------------------------------------------------------------


def test_classify_rename_single_file_returns_false():
    result = classify_feature_thinking(
        feature_name="rename variable x to y",
        num_files=1,
        extended_thinking="auto",
    )
    assert result is False


def test_classify_doc_single_file_returns_false():
    result = classify_feature_thinking(
        feature_name="update doc comment",
        num_files=1,
        extended_thinking="auto",
    )
    assert result is False


def test_classify_format_single_file_returns_false():
    result = classify_feature_thinking(
        feature_name="format source file",
        num_files=1,
        extended_thinking="auto",
    )
    assert result is False


def test_classify_typo_single_file_returns_false():
    result = classify_feature_thinking(
        feature_name="fix typo in README",
        num_files=1,
        extended_thinking="auto",
    )
    assert result is False


# ---------------------------------------------------------------------------
# classify_feature_thinking — ON heuristics (auto mode)
# ---------------------------------------------------------------------------


def test_classify_four_or_more_files_returns_true():
    result = classify_feature_thinking(
        feature_name="neutral task name",
        num_files=4,
        spec_quality=0.95,
        retry_count=0,
        extended_thinking="auto",
    )
    assert result is True


def test_classify_low_spec_quality_returns_true():
    result = classify_feature_thinking(
        feature_name="neutral task",
        num_files=1,
        spec_quality=0.50,
        extended_thinking="auto",
    )
    assert result is True


def test_classify_spec_quality_just_below_threshold_returns_true():
    result = classify_feature_thinking(
        feature_name="neutral",
        num_files=1,
        spec_quality=0.799,
        extended_thinking="auto",
    )
    assert result is True


def test_classify_retry_count_one_returns_true():
    result = classify_feature_thinking(
        feature_name="neutral task",
        num_files=1,
        spec_quality=0.90,
        retry_count=1,
        extended_thinking="auto",
    )
    assert result is True


def test_classify_refactor_keyword_returns_true():
    result = classify_feature_thinking(
        feature_name="refactor auth module",
        extended_thinking="auto",
    )
    assert result is True


def test_classify_migration_keyword_returns_true():
    result = classify_feature_thinking(
        feature_name="migration from old schema",
        extended_thinking="auto",
    )
    assert result is True


def test_classify_bugfix_keyword_returns_true():
    result = classify_feature_thinking(
        feature_name="bugfix null pointer in parser",
        extended_thinking="auto",
    )
    assert result is True


def test_classify_integration_keyword_returns_true():
    result = classify_feature_thinking(
        feature_name="integration between services",
        extended_thinking="auto",
    )
    assert result is True


# ---------------------------------------------------------------------------
# classify_feature_thinking — None extended_thinking (same as "auto")
# ---------------------------------------------------------------------------


def test_classify_none_extended_thinking_runs_classifier():
    # With all signals neutral, should return the default.
    result = classify_feature_thinking(
        feature_name="some feature",
        num_files=2,
        spec_quality=0.90,
        retry_count=0,
        extended_thinking=None,
    )
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# classify_feature_thinking — invalid extended_thinking string raises
# ---------------------------------------------------------------------------


def test_classify_invalid_string_raises_value_error():
    with pytest.raises((ValueError, TypeError)):
        classify_feature_thinking(feature_name="x", extended_thinking="maybe")


# ---------------------------------------------------------------------------
# get_extended_thinking_setting
# ---------------------------------------------------------------------------


def test_get_extended_thinking_setting_returns_bool():
    result = get_extended_thinking_setting()
    assert isinstance(result, bool)


def test_get_extended_thinking_setting_reads_settings_json(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text(json.dumps({"extended_thinking_default": False}))
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result is False


def test_get_extended_thinking_setting_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result is EXTENDED_THINKING_DEFAULT


def test_get_extended_thinking_setting_defaults_on_bad_json(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text("not valid json")
    monkeypatch.chdir(tmp_path)
    result = get_extended_thinking_setting()
    assert result is EXTENDED_THINKING_DEFAULT


# ---------------------------------------------------------------------------
# EXTENDED_THINKING_DEFAULT constant
# ---------------------------------------------------------------------------


def test_extended_thinking_default_is_true():
    assert EXTENDED_THINKING_DEFAULT is True
