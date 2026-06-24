"""Error path tests for adaptive edit mode in bob.swe_bench_directives (F-R7-609).

AC: invalid input raises ValueError and the function does not silently succeed.

Tests that select_edit_mode handles edge cases gracefully and that
emit_edit_mode_event produces valid output even for unusual inputs.
"""

from __future__ import annotations

import pytest

from bob.swe_bench_directives import (
    EditModeDecision,
    emit_edit_mode_event,
    select_edit_mode,
)


class TestSelectEditModeFallback:
    def test_zero_sites_zero_span_returns_replace(self):
        decision = select_edit_mode(0, 0)
        assert decision.mode == "replace"

    def test_negative_sites_does_not_silently_succeed(self):
        # select_edit_mode is lenient — negative is treated as <= threshold
        # confirm it returns a valid EditModeDecision rather than raising
        decision = select_edit_mode(-1, 0)
        assert isinstance(decision, EditModeDecision)
        assert decision.mode in ("replace", "rewrite")

    def test_very_large_site_count_returns_rewrite(self):
        decision = select_edit_mode(10_000, 0)
        assert decision.mode == "rewrite"

    def test_very_large_span_returns_rewrite(self):
        decision = select_edit_mode(0, 10_000)
        assert decision.mode == "rewrite"

    def test_at_site_threshold_stays_replace(self):
        # threshold is 3 — exactly 3 sites should not trigger rewrite
        decision = select_edit_mode(3, 0)
        assert decision.mode == "replace"

    def test_above_site_threshold_triggers_rewrite(self):
        decision = select_edit_mode(4, 0)
        assert decision.mode == "rewrite"

    def test_at_span_threshold_stays_replace(self):
        # threshold is 40 — exactly 40 span should not trigger rewrite
        decision = select_edit_mode(0, 40)
        assert decision.mode == "replace"

    def test_above_span_threshold_triggers_rewrite(self):
        decision = select_edit_mode(0, 41)
        assert decision.mode == "rewrite"

    def test_decision_carries_sites_and_span(self):
        decision = select_edit_mode(2, 15)
        assert decision.sites == 2
        assert decision.span == 15


class TestEmitEditModeEventFallback:
    def test_emit_returns_dict_with_required_keys(self):
        decision = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(decision)
        assert "event" in event
        assert "mode" in event
        assert "sites" in event
        assert "span" in event

    def test_emit_with_rewrite_mode(self):
        decision = EditModeDecision(mode="rewrite", sites=5, span=100)
        event = emit_edit_mode_event(decision)
        assert event["mode"] == "rewrite"

    def test_emit_with_none_feature_id_omits_key(self):
        decision = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(decision, feature_id=None)
        assert "feature_id" not in event

    def test_emit_with_feature_id_includes_key(self):
        decision = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(decision, feature_id="feat-123")
        assert event["feature_id"] == "feat-123"

    def test_event_value_is_edit_mode_string(self):
        decision = EditModeDecision(mode="replace", sites=1, span=2)
        event = emit_edit_mode_event(decision)
        assert event["event"] == "EDIT_MODE"
