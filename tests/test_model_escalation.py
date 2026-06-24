"""Tests for the model-escalation ladder (F-R7-633)."""

from __future__ import annotations

import types

import pytest

from bob3.model_escalation import parse_ladder, resolve_model_for_tier, try_escalate


def test_parse_ladder_default(monkeypatch):
    monkeypatch.delenv("BOB3_MODEL_ESCALATION_LADDER", raising=False)
    assert parse_ladder() == ["sonnet", "opus"]


def test_parse_ladder_explicit():
    assert parse_ladder("sonnet,opus,fable") == ["sonnet", "opus", "fable"]


def test_parse_ladder_drops_unknown_and_dedups():
    # unknown 'gpt5' dropped; duplicate 'sonnet' collapsed; whitespace trimmed
    assert parse_ladder(" sonnet , gpt5 ,opus, sonnet ") == ["sonnet", "opus"]


def test_parse_ladder_empty_falls_back_to_sonnet():
    assert parse_ladder("") == ["sonnet"]
    assert parse_ladder("   ") == ["sonnet"]
    assert parse_ladder(",,") == ["sonnet"]
    assert parse_ladder("totally-bogus") == ["sonnet"]


def test_resolve_model_for_tier_clamps():
    assert resolve_model_for_tier(0, "sonnet,opus") == "sonnet"
    assert resolve_model_for_tier(1, "sonnet,opus") == "opus"
    # beyond the end clamps to the last (strongest) entry
    assert resolve_model_for_tier(5, "sonnet,opus") == "opus"
    # negative / None clamp to 0
    assert resolve_model_for_tier(-3, "sonnet,opus") == "sonnet"
    assert resolve_model_for_tier(None, "sonnet,opus") == "sonnet"


def _fake_feature(tier):
    return types.SimpleNamespace(id="feat-1234abcd", model_tier=tier, refinement_attempts=9)


def test_try_escalate_bumps_tier_and_resets_attempts():
    calls = {}

    def fake_update(feature_id, **kwargs):
        calls["id"] = feature_id
        calls.update(kwargs)

    feat = _fake_feature(0)
    escalated = try_escalate(feat, fake_update, raw="sonnet,opus")
    assert escalated is True
    assert calls["id"] == "feat-1234abcd"
    assert calls["model_tier"] == 1           # bumped 0 -> 1
    assert calls["refinement_attempts"] == 0  # counter reset
    assert calls["status"] == "ready"         # returned to ready, not needs_human


def test_try_escalate_exhausted_at_last_tier_returns_false():
    calls = {}

    def fake_update(feature_id, **kwargs):
        calls["called"] = True

    feat = _fake_feature(1)  # already on opus (last tier of sonnet,opus)
    escalated = try_escalate(feat, fake_update, raw="sonnet,opus")
    assert escalated is False
    assert "called" not in calls  # no DB write — caller marks needs_human


def test_try_escalate_three_tier_ladder():
    seen = []

    def fake_update(feature_id, **kwargs):
        seen.append(kwargs["model_tier"])

    # tier 0 -> 1
    assert try_escalate(_fake_feature(0), fake_update, raw="sonnet,opus,fable") is True
    # tier 1 -> 2
    assert try_escalate(_fake_feature(1), fake_update, raw="sonnet,opus,fable") is True
    # tier 2 is last -> exhausted
    assert try_escalate(_fake_feature(2), fake_update, raw="sonnet,opus,fable") is False
    assert seen == [1, 2]
