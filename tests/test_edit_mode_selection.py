"""Tests for adaptive edit mode selection (F-R7-609 component C).

AC: Function defined: bob.dispatch.select_edit_mode
    pytest: tests/test_edit_mode_selection.py

SWE-Edit (NeurIPS 2025): string-replace by default; switch to whole-file
rewrite when edit_site_count > 3 OR edit_span > 40.
"""

from __future__ import annotations

import pytest

from bob.dispatch import (
    EditModeDecision,
    compute_edit_mode,
    compute_edit_metrics,
    emit_edit_mode_event,
    select_edit_mode,
)


class TestSelectEditModeExists:
    def test_select_edit_mode_callable(self):
        assert callable(select_edit_mode)

    def test_returns_edit_mode_decision(self):
        d = select_edit_mode(0, 0)
        assert isinstance(d, EditModeDecision)

    def test_edit_mode_decision_has_mode_field(self):
        d = select_edit_mode(1, 5)
        assert hasattr(d, "mode")
        assert d.mode in ("replace", "rewrite")

    def test_edit_mode_decision_has_sites_field(self):
        d = select_edit_mode(2, 10)
        assert hasattr(d, "sites")
        assert d.sites == 2

    def test_edit_mode_decision_has_span_field(self):
        d = select_edit_mode(1, 15)
        assert hasattr(d, "span")
        assert d.span == 15


class TestSelectEditModeLogic:
    def test_zero_sites_zero_span_is_replace(self):
        assert select_edit_mode(0, 0).mode == "replace"

    def test_one_site_small_span_is_replace(self):
        assert select_edit_mode(1, 5).mode == "replace"

    def test_three_sites_forty_span_is_replace(self):
        # At threshold, not over — still replace
        assert select_edit_mode(3, 40).mode == "replace"

    def test_four_sites_small_span_is_rewrite(self):
        assert select_edit_mode(4, 0).mode == "rewrite"

    def test_one_site_forty_one_span_is_rewrite(self):
        assert select_edit_mode(1, 41).mode == "rewrite"

    def test_many_sites_is_rewrite(self):
        assert select_edit_mode(10, 0).mode == "rewrite"

    def test_large_span_is_rewrite(self):
        assert select_edit_mode(0, 100).mode == "rewrite"

    def test_both_over_threshold_is_rewrite(self):
        assert select_edit_mode(5, 50).mode == "rewrite"

    def test_sites_preserved_in_decision(self):
        d = select_edit_mode(7, 20)
        assert d.sites == 7

    def test_span_preserved_in_decision(self):
        d = select_edit_mode(1, 55)
        assert d.span == 55


class TestComputeEditMode:
    def test_compute_edit_mode_callable(self):
        assert callable(compute_edit_mode)

    def test_compute_same_as_select_below_threshold(self):
        d1 = select_edit_mode(2, 20)
        d2 = compute_edit_mode(2, 20)
        assert d1.mode == d2.mode

    def test_compute_same_as_select_above_threshold(self):
        d1 = select_edit_mode(5, 50)
        d2 = compute_edit_mode(5, 50)
        assert d1.mode == d2.mode


class TestComputeEditMetrics:
    def test_validates_negative_sites(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(-1, 10)

    def test_validates_negative_span(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(2, -1)

    def test_validates_float_sites(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(1.5, 10)  # type: ignore[arg-type]

    def test_validates_float_span(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(2, 10.5)  # type: ignore[arg-type]

    def test_zero_inputs_returns_replace(self):
        d = compute_edit_metrics(0, 0)
        assert d.mode == "replace"

    def test_over_threshold_returns_rewrite(self):
        d = compute_edit_metrics(4, 0)
        assert d.mode == "rewrite"


class TestEmitEditModeEvent:
    def test_returns_dict(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert isinstance(event, dict)

    def test_event_has_event_key(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert "event" in event
        assert event["event"] == "EDIT_MODE"

    def test_event_has_mode(self):
        d = EditModeDecision(mode="rewrite", sites=5, span=50)
        event = emit_edit_mode_event(d)
        assert event["mode"] == "rewrite"

    def test_event_has_sites(self):
        d = EditModeDecision(mode="replace", sites=2, span=10)
        event = emit_edit_mode_event(d)
        assert event["sites"] == 2

    def test_event_has_span(self):
        d = EditModeDecision(mode="replace", sites=1, span=15)
        event = emit_edit_mode_event(d)
        assert event["span"] == 15

    def test_event_with_feature_id(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d, feature_id="feat-xyz")
        assert event.get("feature_id") == "feat-xyz"

    def test_event_without_feature_id_has_no_feature_id_key(self):
        d = EditModeDecision(mode="replace", sites=1, span=5)
        event = emit_edit_mode_event(d)
        assert "feature_id" not in event
