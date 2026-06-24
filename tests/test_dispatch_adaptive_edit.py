"""Tests for adaptive edit mode in bob.dispatch (F-R7-609 component C).

Covers select_edit_mode, compute_edit_mode, compute_edit_site_count,
compute_edit_site_metrics, compute_edit_metrics, and emit_edit_mode_event.

SWE-Edit (NeurIPS 2025): string-replace default; switch to whole-file rewrite
when edit_site_count > 3 OR edit_span > 40 lines. +2.1% accuracy, -17.9% cost.
"""

from __future__ import annotations

import json

import pytest

from bob.dispatch import (
    EditModeDecision,
    compute_edit_metrics,
    compute_edit_mode,
    compute_edit_site_count,
    compute_edit_site_metrics,
    emit_edit_mode_event,
    select_edit_mode,
)


# ── select_edit_mode ───────────────────────────────────────────────────────────


class TestSelectEditMode:
    def test_returns_edit_mode_decision(self):
        d = select_edit_mode(0, 0)
        assert isinstance(d, EditModeDecision)

    def test_replace_when_below_both_thresholds(self):
        d = select_edit_mode(1, 10)
        assert d.mode == "replace"

    def test_rewrite_when_sites_exceeds_threshold(self):
        d = select_edit_mode(4, 0)
        assert d.mode == "rewrite"

    def test_rewrite_when_span_exceeds_threshold(self):
        d = select_edit_mode(0, 41)
        assert d.mode == "rewrite"

    def test_rewrite_when_both_exceed_thresholds(self):
        d = select_edit_mode(5, 50)
        assert d.mode == "rewrite"

    def test_replace_when_sites_exactly_at_threshold(self):
        # > 3 triggers rewrite; == 3 stays replace
        d = select_edit_mode(3, 0)
        assert d.mode == "replace"

    def test_replace_when_span_exactly_at_threshold(self):
        # > 40 triggers rewrite; == 40 stays replace
        d = select_edit_mode(0, 40)
        assert d.mode == "replace"

    def test_sites_stored_on_decision(self):
        d = select_edit_mode(2, 15)
        assert d.sites == 2

    def test_span_stored_on_decision(self):
        d = select_edit_mode(2, 15)
        assert d.span == 15

    def test_custom_site_threshold(self):
        d = select_edit_mode(2, 0, site_threshold=1)
        assert d.mode == "rewrite"

    def test_custom_span_threshold(self):
        d = select_edit_mode(0, 5, span_threshold=4)
        assert d.mode == "rewrite"


# ── compute_edit_mode ──────────────────────────────────────────────────────────


class TestComputeEditMode:
    def test_returns_edit_mode_decision(self):
        d = compute_edit_mode(0, 0)
        assert isinstance(d, EditModeDecision)

    def test_delegates_to_select_edit_mode_replace(self):
        d = compute_edit_mode(1, 5)
        assert d.mode == "replace"

    def test_delegates_to_select_edit_mode_rewrite(self):
        d = compute_edit_mode(4, 0)
        assert d.mode == "rewrite"

    def test_sites_and_span_preserved(self):
        d = compute_edit_mode(2, 30)
        assert d.sites == 2
        assert d.span == 30


# ── compute_edit_site_count ────────────────────────────────────────────────────


class TestComputeEditSiteCount:
    def test_returns_edit_mode_decision(self):
        d = compute_edit_site_count(0, 0)
        assert isinstance(d, EditModeDecision)

    def test_replace_below_thresholds(self):
        d = compute_edit_site_count(1, 10)
        assert d.mode == "replace"

    def test_rewrite_above_site_threshold(self):
        d = compute_edit_site_count(4, 0)
        assert d.mode == "rewrite"

    def test_rewrite_above_span_threshold(self):
        d = compute_edit_site_count(0, 41)
        assert d.mode == "rewrite"

    def test_sites_and_span_recorded(self):
        d = compute_edit_site_count(3, 20)
        assert d.sites == 3
        assert d.span == 20

    def test_negative_site_count_raises_value_error(self):
        with pytest.raises(ValueError, match="edit_site_count"):
            compute_edit_site_count(-1, 10)

    def test_negative_span_raises_value_error(self):
        with pytest.raises(ValueError, match="edit_span"):
            compute_edit_site_count(2, -1)

    def test_float_site_count_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_site_count(1.5, 10)  # type: ignore[arg-type]

    def test_float_span_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_site_count(2, 10.5)  # type: ignore[arg-type]

    def test_zero_zero_returns_replace(self):
        d = compute_edit_site_count(0, 0)
        assert d.mode == "replace"

    def test_at_site_threshold_returns_replace(self):
        d = compute_edit_site_count(3, 0)
        assert d.mode == "replace"

    def test_at_span_threshold_returns_replace(self):
        d = compute_edit_site_count(0, 40)
        assert d.mode == "replace"


# ── compute_edit_site_metrics ──────────────────────────────────────────────────


class TestComputeEditSiteMetrics:
    def test_returns_edit_mode_decision(self):
        d = compute_edit_site_metrics(0, 0)
        assert isinstance(d, EditModeDecision)

    def test_same_output_as_compute_edit_site_count(self):
        for sites, span in [(0, 0), (3, 40), (4, 0), (0, 41), (5, 50)]:
            assert compute_edit_site_metrics(sites, span) == compute_edit_site_count(sites, span)

    def test_validates_negative_inputs(self):
        with pytest.raises(ValueError):
            compute_edit_site_metrics(-1, 0)

    def test_validates_float_inputs(self):
        with pytest.raises(ValueError):
            compute_edit_site_metrics(1.0, 0)  # type: ignore[arg-type]


# ── compute_edit_metrics ───────────────────────────────────────────────────────


class TestComputeEditMetrics:
    def test_returns_replace_for_small_inputs(self):
        d = compute_edit_metrics(1, 5)
        assert d.mode == "replace"

    def test_returns_rewrite_for_large_sites(self):
        d = compute_edit_metrics(4, 0)
        assert d.mode == "rewrite"

    def test_returns_rewrite_for_large_span(self):
        d = compute_edit_metrics(0, 41)
        assert d.mode == "rewrite"

    def test_negative_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(-1, 10)


# ── emit_edit_mode_event ───────────────────────────────────────────────────────


class TestEmitEditModeEvent:
    def test_returns_dict(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert isinstance(event, dict)

    def test_event_key_is_edit_mode(self):
        d = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(d)
        assert event["event"] == "EDIT_MODE"

    def test_mode_in_event(self):
        d = EditModeDecision(mode="rewrite", sites=4, span=0)
        event = emit_edit_mode_event(d)
        assert event["mode"] == "rewrite"

    def test_sites_in_event(self):
        d = EditModeDecision(mode="replace", sites=2, span=0)
        event = emit_edit_mode_event(d)
        assert event["sites"] == 2

    def test_span_in_event(self):
        d = EditModeDecision(mode="replace", sites=0, span=15)
        event = emit_edit_mode_event(d)
        assert event["span"] == 15

    def test_feature_id_included_when_provided(self):
        d = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(d, feature_id="feat-123")
        assert event["feature_id"] == "feat-123"

    def test_feature_id_absent_when_none(self):
        d = EditModeDecision(mode="replace", sites=0, span=0)
        event = emit_edit_mode_event(d)
        assert "feature_id" not in event

    def test_event_is_json_serializable(self):
        d = EditModeDecision(mode="rewrite", sites=5, span=50)
        event = emit_edit_mode_event(d, feature_id="feat-abc")
        json.dumps(event)  # must not raise
