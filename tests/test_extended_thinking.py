"""Tests for BF-8 Part B — bob3.extended_thinking.classify_thinking_requirement."""

from __future__ import annotations

import pytest

from bob3.extended_thinking import (
    EXTENDED_THINKING_DEFAULT,
    classify_thinking_requirement,
    classifier,
    thinking_kwargs,
)


# ---------------------------------------------------------------------------
# classify_thinking_requirement — explicit overrides
# ---------------------------------------------------------------------------


def test_explicit_true_always_enables():
    result = classify_thinking_requirement(extended_thinking=True)
    assert result is True


def test_explicit_false_always_disables():
    result = classify_thinking_requirement(extended_thinking=False)
    assert result is False


def test_explicit_false_overrides_complex_feature():
    result = classify_thinking_requirement(
        feature_name="major refactor",
        num_files=10,
        spec_quality=0.50,
        retry_count=3,
        extended_thinking=False,
    )
    assert result is False


# ---------------------------------------------------------------------------
# classify_thinking_requirement — auto-classifier
# ---------------------------------------------------------------------------


def test_auto_off_for_trivial_rename_single_file():
    result = classify_thinking_requirement(
        feature_name="rename method",
        num_files=1,
        extended_thinking="auto",
    )
    assert result is False


def test_auto_on_for_many_files():
    result = classify_thinking_requirement(
        feature_name="update config",
        num_files=5,
        extended_thinking="auto",
    )
    assert result is True


def test_auto_on_for_low_spec_quality():
    result = classify_thinking_requirement(
        feature_name="implement feature",
        num_files=1,
        spec_quality=0.70,
        extended_thinking="auto",
    )
    assert result is True


def test_auto_on_for_retry():
    result = classify_thinking_requirement(
        feature_name="implement something",
        num_files=1,
        retry_count=1,
        extended_thinking="auto",
    )
    assert result is True


def test_auto_on_for_refactor_keyword():
    result = classify_thinking_requirement(
        feature_name="large refactor of auth system",
        num_files=2,
        spec_quality=0.90,
        retry_count=0,
        extended_thinking=None,
    )
    assert result is True


def test_auto_on_for_bugfix_keyword():
    result = classify_thinking_requirement(
        feature_name="bugfix in payment processor",
        num_files=1,
        spec_quality=0.95,
        retry_count=0,
        extended_thinking=None,
    )
    assert result is True


def test_defaults_to_extended_thinking_default():
    result = classify_thinking_requirement()
    assert result == EXTENDED_THINKING_DEFAULT


# ---------------------------------------------------------------------------
# thinking_kwargs — shape of output
# ---------------------------------------------------------------------------


def test_thinking_kwargs_enabled_returns_type_enabled():
    result = thinking_kwargs(True)
    assert result.get("type") == "enabled"
    assert "budget_tokens" in result


def test_thinking_kwargs_disabled_returns_empty_dict():
    result = thinking_kwargs(False)
    assert result == {}


# ---------------------------------------------------------------------------
# classifier — alias works the same way
# ---------------------------------------------------------------------------


def test_classifier_alias_matches_classify_thinking_requirement():
    kwargs = dict(
        feature_name="migration task",
        num_files=2,
        spec_quality=0.95,
        retry_count=0,
    )
    assert classifier(**kwargs) == classify_thinking_requirement(**kwargs)


def test_extended_thinking_default_is_true():
    assert EXTENDED_THINKING_DEFAULT is True
