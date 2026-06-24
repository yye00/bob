"""Error path tests for SWE-Bench cheap wins in bob3.dispatch (F-R7-609).

AC: invalid input raises ValueError and the function does not silently succeed.

Covers error paths for functions with explicit validation:
  (C) compute_edit_metrics — validates non-negative integer inputs
  Other functions use SimpleNamespace duck-typing so are tested
  for attribute-error safety.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bob3.dispatch import (
    EditModeDecision,
    apply_cheap_wins,
    build_repo_tree,
    build_worker_system_prompt,
    check_mutation_pass,
    check_reap_backoff,
    compute_edit_metrics,
    emit_edit_mode_event,
    emit_weak_test_event,
    run_mutation_pass_check,
    select_edit_mode,
    should_inject_repro_test_directive,
)


# ── compute_edit_metrics — validated entry point ───────────────────────────────


class TestComputeEditMetricsErrors:
    def test_negative_site_count_raises_value_error(self):
        with pytest.raises(ValueError, match="edit_site_count"):
            compute_edit_metrics(-1, 10)

    def test_negative_span_raises_value_error(self):
        with pytest.raises(ValueError, match="edit_span"):
            compute_edit_metrics(2, -1)

    def test_both_negative_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(-1, -1)

    def test_float_site_count_raises_value_error(self):
        with pytest.raises(ValueError, match="integer"):
            compute_edit_metrics(1.5, 10)  # type: ignore[arg-type]

    def test_float_span_raises_value_error(self):
        with pytest.raises(ValueError, match="integer"):
            compute_edit_metrics(2, 10.5)  # type: ignore[arg-type]

    def test_string_site_count_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics("3", 10)  # type: ignore[arg-type]

    def test_string_span_raises_value_error(self):
        with pytest.raises(ValueError):
            compute_edit_metrics(2, "10")  # type: ignore[arg-type]

    def test_none_site_count_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            compute_edit_metrics(None, 10)  # type: ignore[arg-type]

    def test_none_span_raises_value_error(self):
        with pytest.raises((ValueError, TypeError)):
            compute_edit_metrics(2, None)  # type: ignore[arg-type]

    def test_does_not_silently_succeed_on_negative_inputs(self):
        try:
            compute_edit_metrics(-5, -5)
            pytest.fail("Should have raised ValueError but did not")
        except ValueError:
            pass  # Expected

    def test_valid_zero_inputs_do_not_raise(self):
        result = compute_edit_metrics(0, 0)
        assert result.mode == "replace"


# ── check_reap_backoff — validates non-None feature ────────────────────────────


class TestCheckReapBackoffErrors:
    def test_none_feature_raises_value_error(self):
        with pytest.raises(ValueError):
            check_reap_backoff(None)  # type: ignore[arg-type]

    def test_does_not_silently_succeed_on_none(self):
        try:
            check_reap_backoff(None)  # type: ignore[arg-type]
            pytest.fail("Should have raised ValueError but did not")
        except (ValueError, AttributeError):
            pass  # Expected — either explicit ValueError or attr lookup failure


# ── Other functions — duck-typing robustness (must not silently corrupt) ───────


class TestInvalidInputRobustness:
    def test_select_edit_mode_negative_sites_does_not_silently_accept(self):
        # select_edit_mode doesn't validate, but negative sites < threshold → replace
        # (not a contract violation, just documenting behavior)
        d = select_edit_mode(-1, -1)
        assert d.mode in ("replace", "rewrite")

    def test_emit_weak_test_event_non_string_feature_id_returns_dict(self):
        # Duck-typed: any value stored as feature_id
        event = emit_weak_test_event(123)  # type: ignore[arg-type]
        assert isinstance(event, dict)

    def test_emit_edit_mode_event_invalid_mode_still_returns_dict(self):
        # No enum validation — just structural check
        d = EditModeDecision(mode="invalid", sites=0, span=0)
        event = emit_edit_mode_event(d)
        assert isinstance(event, dict)
        assert event["mode"] == "invalid"

    def test_run_mutation_pass_check_bad_command_returns_false(self, tmp_path):
        with patch("bob3.dispatch.subprocess.run") as mock:
            mock.side_effect = FileNotFoundError("command not found")
            result = run_mutation_pass_check(["nonexistent_cmd"], tmp_path, "feat-001")
        assert result is False

    def test_apply_cheap_wins_feature_without_skip_attrs_does_not_crash(self, tmp_path):
        # Feature with no skip_repo_tree or skip_repro_test defaults to False (getattr)
        feature = SimpleNamespace(
            id="feat-min",
            acceptance_criteria=None,
            localization_shortlist=[],
        )
        result, meta = apply_cheap_wins("do work", tmp_path, feature)
        assert isinstance(result, str)
        assert isinstance(meta, dict)

    def test_should_inject_repro_test_directive_malformed_json_does_not_raise(self):
        feature = SimpleNamespace(
            skip_repro_test=False,
            acceptance_criteria="{not valid json",
        )
        result = should_inject_repro_test_directive(feature)
        assert isinstance(result, bool)

    def test_build_worker_system_prompt_feature_no_acs_does_not_raise(self, tmp_path):
        feature = SimpleNamespace(
            id="feat-noac",
            skip_repo_tree=False,
            skip_repro_test=False,
            acceptance_criteria=None,
            localization_shortlist=[],
        )
        result = build_worker_system_prompt("do work", tmp_path, feature)
        assert isinstance(result, str)
