"""Boundary-case tests for model-escalation ladder (F-R7-633).

These tests verify that empty, zero, or minimum inputs return well-defined
results rather than raising — the parser and resolver must never crash the run.
"""

from __future__ import annotations

import types

import pytest

from bob3.model_escalation import parse_ladder, resolve_model_for_tier, try_escalate


# ---------------------------------------------------------------------------
# parse_ladder — boundary inputs


def test_parse_ladder_none_returns_default():
    """None raw string (unset env) uses the default ladder without raising."""
    result = parse_ladder(None)
    assert isinstance(result, list)
    assert len(result) >= 1


def test_parse_ladder_empty_string_returns_fallback():
    """Empty string is a boundary input; must return ["sonnet"] not raise."""
    result = parse_ladder("")
    assert result == ["sonnet"]


def test_parse_ladder_single_valid_entry():
    """A single-entry ladder (minimum non-empty) is valid."""
    result = parse_ladder("sonnet")
    assert result == ["sonnet"]


def test_parse_ladder_all_whitespace_returns_fallback():
    """All-whitespace string is treated as empty; safe fallback, no raise."""
    result = parse_ladder("   ")
    assert result == ["sonnet"]


def test_parse_ladder_zero_valid_entries_drops_unknowns_returns_fallback():
    """All entries unknown → fallback, not raise."""
    result = parse_ladder("bogus1,bogus2")
    assert result == ["sonnet"]


def test_parse_ladder_empty_tokens_via_commas_returns_fallback():
    """Commas with no tokens → no entries → fallback, not raise."""
    result = parse_ladder(",,,")
    assert result == ["sonnet"]


def test_parse_ladder_preserves_order():
    """Order of valid entries is preserved (boundary: first entry is least capable)."""
    result = parse_ladder("sonnet,opus")
    assert result[0] == "sonnet"
    assert result[1] == "opus"


# ---------------------------------------------------------------------------
# resolve_model_for_tier — boundary inputs


def test_resolve_model_for_tier_zero():
    """Tier 0 (minimum) returns the first ladder entry without raising."""
    result = resolve_model_for_tier(0, "sonnet,opus")
    assert result == "sonnet"


def test_resolve_model_for_tier_none_clamps_to_zero():
    """None tier is a boundary input; must clamp to 0, not raise."""
    result = resolve_model_for_tier(None, "sonnet,opus")
    assert result == "sonnet"


def test_resolve_model_for_tier_negative_clamps_to_zero():
    """Negative tier is a boundary; must clamp to 0, not raise."""
    result = resolve_model_for_tier(-1, "sonnet,opus")
    assert result == "sonnet"


def test_resolve_model_for_tier_beyond_end_clamps_to_last():
    """Tier beyond ladder length clamps to last entry, not raise."""
    result = resolve_model_for_tier(999, "sonnet,opus")
    assert result == "opus"


def test_resolve_model_for_tier_single_entry_ladder():
    """Single-entry ladder (minimum ladder size) works for any tier."""
    assert resolve_model_for_tier(0, "sonnet") == "sonnet"
    assert resolve_model_for_tier(5, "sonnet") == "sonnet"
    assert resolve_model_for_tier(None, "sonnet") == "sonnet"


# ---------------------------------------------------------------------------
# try_escalate — boundary inputs


def test_try_escalate_feature_at_tier_zero_escalates():
    """Tier 0 (minimum starting tier) escalates to tier 1 without raising."""
    calls = {}

    def fake_update(feature_id, **kwargs):
        calls.update(kwargs)

    feat = types.SimpleNamespace(id="feat-boundary-0", model_tier=0, refinement_attempts=5)
    result = try_escalate(feat, fake_update, raw="sonnet,opus")
    assert result is True
    assert calls["model_tier"] == 1
    assert calls["refinement_attempts"] == 0
    assert calls["status"] == "ready"


def test_try_escalate_feature_at_last_tier_returns_false():
    """Feature at the last (maximum) tier returns False, not raise."""
    calls = {}

    def fake_update(feature_id, **kwargs):
        calls["called"] = True

    feat = types.SimpleNamespace(id="feat-boundary-last", model_tier=1, refinement_attempts=5)
    result = try_escalate(feat, fake_update, raw="sonnet,opus")
    assert result is False
    assert "called" not in calls


def test_try_escalate_model_tier_none_treated_as_zero():
    """None model_tier (boundary: unset column) is treated as 0, not raise."""
    calls = {}

    def fake_update(feature_id, **kwargs):
        calls.update(kwargs)

    feat = types.SimpleNamespace(id="feat-boundary-none-tier", model_tier=None, refinement_attempts=3)
    result = try_escalate(feat, fake_update, raw="sonnet,opus")
    assert result is True
    assert calls["model_tier"] == 1


def test_try_escalate_zero_refinement_attempts_resets_to_zero():
    """Feature with zero refinement_attempts (already reset) still escalates cleanly."""
    calls = {}

    def fake_update(feature_id, **kwargs):
        calls.update(kwargs)

    feat = types.SimpleNamespace(id="feat-boundary-zero-attempts", model_tier=0, refinement_attempts=0)
    result = try_escalate(feat, fake_update, raw="sonnet,opus")
    assert result is True
    assert calls["refinement_attempts"] == 0
