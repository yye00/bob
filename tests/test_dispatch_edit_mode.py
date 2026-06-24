"""Tests for adaptive edit mode (EDIT_MODE) in bob3.dispatch (F-R7-609).

Covers select_edit_mode, compute_edit_mode, compute_edit_metrics, and
emit_edit_mode_event. SWE-Edit NeurIPS 2025: string-replace default;
whole-file rewrite when sites > 3 or span > 40.
"""

from __future__ import annotations

import json

import pytest

from bob3.dispatch import (
    EditModeDecision,
    compute_edit_metrics,
    compute_edit_mode,
    emit_edit_mode_event,
    select_edit_mode,
)


class TestSelectEditMode:
    def test_zero_inputs_returns_replace(self):
        d = select_edit_mode(0, 0)
        assert d.mode == "replace"

    def test_sites_below_threshold_returns_replace(self):
        d = select_edit_mode(2, 0)
        assert d.mode == "replace"

    def test_span_below_threshold_returns_replace(self):
        d = select_edit_mode(0, 20)
        assert d.mode == "replace"

    def test_exactly_at_threshold_returns_replace(self):
        # > 3 triggers rewrite; == 3 is still replace
        d = select_edit_mode(3, 40)
        assert d.mode == "replace"

    def test_sites_exceeds_threshold_returns_rewrite(self):
        d = select_edit_mode(4, 0)
        assert d.mode == "rewrite"

    def test_span_exceeds_threshold_returns_rewrite(self):
        d = select_edit_mode(0, 41)
        assert d.mode == "rewrite"

    def test_both_exceed_thresholds_returns_rewrite(self):
        d = select_edit_mode(10, 100)
        assert d.mode == "rewrite"

    def test_returns_edit_mode_decision_instance(self):
        d = select_edit_mode(1, 5)
        assert isinstance(d, EditModeDecision)

    def test_sites_recorded_on_decision(self):
        d = select_edit_mode(7, 0)
        assert d.sites == 7

    def test_span_recorded_on_decision(self):
        d = select_edit_mode(0, 55)
        assert d.span == 55

    def test_custom_thresholds_respected(self):
        # With site_threshold=1, even 2 sites → rewrite
        d = select_edit_mode(2, 0, site_threshold=1)
        assert d.mode == "rewrite"

    def test_custom_span_threshold_respected(self):
        d = select_edit_mode(0, 10, span_threshold=5)
        assert d.mode == "rewrite"


class TestComputeEditMode:
    def test_zero_inputs_returns_replace(self):
        d = compute_edit_mode(0, 0)
        assert d.mode == "replace"

    def test_four_sites_returns_rewrite(self):
        d = compute_edit_mode(4, 0)
        assert d.mode == "rewrite"

    def test_41_span_returns_rewrite(self):
        d = compute_edit_mode(0, 41)
        assert d.mode == "rewrite"

    def test_returns_edit_mode_decision(self):
        d = compute_edit_mode(1, 1)
        assert isinstance(d, EditModeDecision)

    def test_matches_select_edit_mode(self):
        for sites in [0, 1, 3, 4, 10]:
            for span in [0, 10, 40, 41, 100]:
                assert compute_edit_mode(sites, span).mode == select_edit_mode(sites, span).mode


class TestComputeEditMetrics:
    def test_valid_inputs_return_decision(self):
        d = compute_edit_metrics(2, 10)
        assert isinstance(d, EditModeDecision)

    def test_zero_inputs_valid(self):
        d = compute_edit_metrics(0, 0)
        assert d.mode == "replace"

    def test_negative_sites_raises(self):
        with pytest.raises(ValueError, match="edit_site_count"):
            compute_edit_metrics(-1, 10)

    def test_negative_span_raises(self):
        with pytest.raises(ValueError, match="edit_span"):
            compute_edit_metrics(2, -1)

    def test_float_sites_raises(self):
        with pytest.raises(ValueError, match="integer"):
            compute_edit_metrics(1.5, 10)  # type: ignore[arg-type]

    def test_float_span_raises(self):
        with pytest.raises(ValueError, match="integer"):
            compute_edit_metrics(2, 10.5)  # type: ignore[arg-type]

    def test_string_sites_raises(self):
        with pytest.raises(ValueError):
            compute_edit_metrics("3", 10)  # type: ignore[arg-type]

    def test_above_threshold_sites_returns_rewrite(self):
        d = compute_edit_metrics(4, 0)
        assert d.mode == "rewrite"

    def test_above_threshold_span_returns_rewrite(self):
        d = compute_edit_metrics(0, 41)
        assert d.mode == "rewrite"


class TestEmitEditModeEvent:
    def test_returns_dict(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert isinstance(event, dict)

    def test_event_key_is_edit_mode(self):
        d = EditModeDecision(mode="rewrite", sites=5, span=50)
        event = emit_edit_mode_event(d)
        assert event["event"] == "EDIT_MODE"

    def test_mode_in_event(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert event["mode"] == "replace"

    def test_sites_in_event(self):
        d = EditModeDecision(mode="rewrite", sites=7, span=50)
        event = emit_edit_mode_event(d)
        assert event["sites"] == 7

    def test_span_in_event(self):
        d = EditModeDecision(mode="rewrite", sites=7, span=50)
        event = emit_edit_mode_event(d)
        assert event["span"] == 50

    def test_feature_id_included_when_provided(self):
        d = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(d, feature_id="feat-123")
        assert event["feature_id"] == "feat-123"

    def test_feature_id_absent_when_not_provided(self):
        d = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(d)
        assert "feature_id" not in event

    def test_event_is_json_serializable(self):
        d = EditModeDecision(mode="rewrite", sites=5, span=50)
        event = emit_edit_mode_event(d, feature_id="feat-999")
        json.dumps(event)  # must not raise
