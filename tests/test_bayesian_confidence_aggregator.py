"""Tests for src/bob/bayesian_confidence_aggregator.py (F-R4-130)."""

from __future__ import annotations

import math

import pytest

from bob.bayesian_confidence_aggregator import (
    AggregationResult,
    BayesianConfidenceAggregator,
    _DEFAULT_TASK_CLASS_PRIORS,
    _clamp_prob,
    _from_log_odds,
    _to_log_odds,
    aggregate_confidence,
)


# ---------------------------------------------------------------------------
# Math helper tests
# ---------------------------------------------------------------------------


class TestMathHelpers:
    def test_to_log_odds_midpoint(self):
        assert _to_log_odds(0.5) == pytest.approx(0.0, abs=1e-6)

    def test_to_log_odds_high_probability(self):
        lo = _to_log_odds(0.9)
        assert lo > 0

    def test_to_log_odds_low_probability(self):
        lo = _to_log_odds(0.1)
        assert lo < 0

    def test_to_log_odds_clamps_input(self):
        # Should not raise even for degenerate inputs
        assert _to_log_odds(0.0) < -10
        assert _to_log_odds(1.0) > 10

    def test_from_log_odds_zero(self):
        assert _from_log_odds(0.0) == pytest.approx(0.5, abs=1e-6)

    def test_round_trip(self):
        for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            assert _from_log_odds(_to_log_odds(p)) == pytest.approx(p, abs=1e-6)

    def test_clamp_prob_within_bounds(self):
        assert _clamp_prob(0.5) == pytest.approx(0.5)
        assert _clamp_prob(0.0) == pytest.approx(0.02)
        assert _clamp_prob(1.0) == pytest.approx(0.98)
        assert _clamp_prob(-1.0) == pytest.approx(0.02)
        assert _clamp_prob(2.0) == pytest.approx(0.98)


# ---------------------------------------------------------------------------
# aggregate_confidence() tests
# ---------------------------------------------------------------------------


class TestAggregateConfidence:
    def test_returns_float_in_range(self):
        result = aggregate_confidence(
            conf_spec=0.8,
            conf_impl=0.8,
            conf_test=0.8,
        )
        assert isinstance(result, float)
        assert 0.02 <= result <= 0.98

    def test_high_confidence_yields_high_output(self):
        high = aggregate_confidence(
            conf_spec=0.95,
            conf_impl=0.95,
            conf_test=0.95,
        )
        low = aggregate_confidence(
            conf_spec=0.1,
            conf_impl=0.1,
            conf_test=0.1,
        )
        assert high > 0.6
        assert low < 0.5
        assert high > low

    def test_stub_errors_penalise_output(self):
        base = aggregate_confidence(
            conf_spec=0.8,
            conf_impl=0.8,
            conf_test=0.8,
            has_stub_errors=False,
        )
        penalised = aggregate_confidence(
            conf_spec=0.8,
            conf_impl=0.8,
            conf_test=0.8,
            has_stub_errors=True,
        )
        assert penalised < base

    def test_mock_errors_penalise_output(self):
        base = aggregate_confidence(
            conf_spec=0.8,
            conf_impl=0.8,
            conf_test=0.8,
            has_mock_errors=False,
        )
        penalised = aggregate_confidence(
            conf_spec=0.8,
            conf_impl=0.8,
            conf_test=0.8,
            has_mock_errors=True,
        )
        assert penalised < base

    def test_both_penalties_compound(self):
        no_penalty = aggregate_confidence(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8
        )
        stub_only = aggregate_confidence(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8, has_stub_errors=True
        )
        both = aggregate_confidence(
            conf_spec=0.8,
            conf_impl=0.8,
            conf_test=0.8,
            has_stub_errors=True,
            has_mock_errors=True,
        )
        assert both < stub_only < no_penalty

    def test_registry_high_success_rate_boosts_output(self):
        no_reg = aggregate_confidence(
            conf_spec=0.5, conf_impl=0.5, conf_test=0.5
        )
        with_reg = aggregate_confidence(
            conf_spec=0.5,
            conf_impl=0.5,
            conf_test=0.5,
            registry_success_rate=0.95,
            registry_n=20,
        )
        assert with_reg > no_reg

    def test_registry_low_success_rate_reduces_output(self):
        no_reg = aggregate_confidence(
            conf_spec=0.5, conf_impl=0.5, conf_test=0.5
        )
        with_reg = aggregate_confidence(
            conf_spec=0.5,
            conf_impl=0.5,
            conf_test=0.5,
            registry_success_rate=0.05,
            registry_n=20,
        )
        assert with_reg < no_reg

    def test_registry_small_n_has_less_effect(self):
        large_n = aggregate_confidence(
            conf_spec=0.5,
            conf_impl=0.5,
            conf_test=0.5,
            registry_success_rate=0.95,
            registry_n=100,
        )
        small_n = aggregate_confidence(
            conf_spec=0.5,
            conf_impl=0.5,
            conf_test=0.5,
            registry_success_rate=0.95,
            registry_n=1,
        )
        no_reg = aggregate_confidence(conf_spec=0.5, conf_impl=0.5, conf_test=0.5)
        # small_n boost is between no_reg and large_n boost
        assert no_reg < small_n <= large_n

    def test_registry_n_zero_ignored(self):
        # registry_n=0 should not apply registry signal
        result_no_reg = aggregate_confidence(conf_spec=0.5, conf_impl=0.5, conf_test=0.5)
        result_n_zero = aggregate_confidence(
            conf_spec=0.5,
            conf_impl=0.5,
            conf_test=0.5,
            registry_success_rate=0.99,
            registry_n=0,
        )
        assert result_no_reg == pytest.approx(result_n_zero, abs=1e-6)

    def test_task_class_prior_influences_result(self):
        high_prior = aggregate_confidence(
            conf_spec=0.5, conf_impl=0.5, conf_test=0.5, task_class_prior=0.9
        )
        low_prior = aggregate_confidence(
            conf_spec=0.5, conf_impl=0.5, conf_test=0.5, task_class_prior=0.1
        )
        assert high_prior > low_prior

    def test_task_class_prior_explicit_overrides_lookup(self):
        # Provide explicit prior that differs from default table
        explicit = aggregate_confidence(
            conf_spec=0.5,
            conf_impl=0.5,
            conf_test=0.5,
            task_class="algorithm_implementation",
            task_class_prior=0.95,
        )
        default = aggregate_confidence(
            conf_spec=0.5,
            conf_impl=0.5,
            conf_test=0.5,
            task_class="algorithm_implementation",
        )
        # Explicit prior of 0.95 > default (0.65), so explicit should be higher
        assert explicit > default

    def test_known_task_classes_have_defaults(self):
        for tc in _DEFAULT_TASK_CLASS_PRIORS:
            result = aggregate_confidence(
                conf_spec=0.5, conf_impl=0.5, conf_test=0.5, task_class=tc
            )
            assert 0.02 <= result <= 0.98

    def test_unknown_task_class_uses_fallback(self):
        result = aggregate_confidence(
            conf_spec=0.5, conf_impl=0.5, conf_test=0.5, task_class="unknown_xyz"
        )
        assert 0.02 <= result <= 0.98

    def test_output_clamped_to_valid_range(self):
        # Extreme inputs should still stay within [0.02, 0.98]
        very_high = aggregate_confidence(
            conf_spec=1.0, conf_impl=1.0, conf_test=1.0,
            registry_success_rate=1.0, registry_n=100,
            task_class_prior=1.0,
        )
        very_low = aggregate_confidence(
            conf_spec=0.0, conf_impl=0.0, conf_test=0.0,
            has_stub_errors=True, has_mock_errors=True,
            registry_success_rate=0.0, registry_n=100,
            task_class_prior=0.0,
        )
        assert very_high <= 0.98
        assert very_low >= 0.02

    def test_all_default_args(self):
        # Must not raise with minimal arguments
        result = aggregate_confidence(conf_spec=0.7, conf_impl=0.7, conf_test=0.7)
        assert 0.02 <= result <= 0.98


# ---------------------------------------------------------------------------
# BayesianConfidenceAggregator (wrapper) tests
# ---------------------------------------------------------------------------


class TestBayesianConfidenceAggregator:
    @pytest.fixture()
    def agg(self) -> BayesianConfidenceAggregator:
        return BayesianConfidenceAggregator()

    def test_returns_aggregation_result(self, agg):
        result = agg.aggregate(conf_spec=0.8, conf_impl=0.8, conf_test=0.8)
        assert isinstance(result, AggregationResult)

    def test_calibrated_confidence_in_range(self, agg):
        result = agg.aggregate(conf_spec=0.8, conf_impl=0.8, conf_test=0.8)
        assert 0.02 <= result.calibrated_confidence <= 0.98

    def test_self_reported_avg_computed_correctly(self, agg):
        result = agg.aggregate(conf_spec=0.6, conf_impl=0.8, conf_test=1.0)
        assert result.self_reported_avg == pytest.approx(0.8, abs=1e-6)

    def test_task_class_recorded(self, agg):
        result = agg.aggregate(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8, task_class="refactor"
        )
        assert result.task_class == "refactor"

    def test_signals_includes_self_report_and_prior(self, agg):
        result = agg.aggregate(conf_spec=0.8, conf_impl=0.8, conf_test=0.8)
        assert "self_report" in result.signals_applied
        assert "task_class_prior" in result.signals_applied

    def test_signals_includes_registry_when_provided(self, agg):
        result = agg.aggregate(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8,
            registry_success_rate=0.7, registry_n=5,
        )
        assert "registry" in result.signals_applied

    def test_signals_excludes_registry_when_n_zero(self, agg):
        result = agg.aggregate(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8,
            registry_success_rate=0.7, registry_n=0,
        )
        assert "registry" not in result.signals_applied

    def test_signals_includes_stub_penalty(self, agg):
        result = agg.aggregate(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8, has_stub_errors=True
        )
        assert "ast_stub_penalty" in result.signals_applied
        assert "ast_clean_bonus" not in result.signals_applied

    def test_signals_includes_mock_penalty(self, agg):
        result = agg.aggregate(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8, has_mock_errors=True
        )
        assert "ast_mock_penalty" in result.signals_applied

    def test_signals_includes_clean_bonus_when_no_issues(self, agg):
        result = agg.aggregate(conf_spec=0.8, conf_impl=0.8, conf_test=0.8)
        assert "ast_clean_bonus" in result.signals_applied
        assert "ast_stub_penalty" not in result.signals_applied
        assert "ast_mock_penalty" not in result.signals_applied

    def test_calibrated_matches_aggregate_confidence(self, agg):
        kwargs = dict(
            conf_spec=0.7,
            conf_impl=0.6,
            conf_test=0.8,
            task_class="integration",
            registry_success_rate=0.65,
            registry_n=12,
            has_stub_errors=False,
            has_mock_errors=True,
        )
        result = agg.aggregate(**kwargs)
        direct = aggregate_confidence(**kwargs)
        assert result.calibrated_confidence == pytest.approx(direct, abs=1e-6)

    def test_stub_errors_lower_calibrated_confidence(self, agg):
        clean = agg.aggregate(conf_spec=0.8, conf_impl=0.8, conf_test=0.8)
        stubbed = agg.aggregate(
            conf_spec=0.8, conf_impl=0.8, conf_test=0.8, has_stub_errors=True
        )
        assert stubbed.calibrated_confidence < clean.calibrated_confidence


# ---------------------------------------------------------------------------
# Monotonicity / ordering tests
# ---------------------------------------------------------------------------


class TestMonotonicity:
    """Aggregate output should vary monotonically with clear signal changes."""

    @pytest.mark.parametrize("conf", [0.1, 0.3, 0.5, 0.7, 0.9])
    def test_uniform_self_report_monotone(self, conf):
        result = aggregate_confidence(
            conf_spec=conf, conf_impl=conf, conf_test=conf
        )
        assert 0.02 <= result <= 0.98

    def test_increasing_conf_increases_output(self):
        results = [
            aggregate_confidence(conf_spec=c, conf_impl=c, conf_test=c)
            for c in [0.1, 0.3, 0.5, 0.7, 0.9]
        ]
        for r0, r1 in zip(results, results[1:]):
            assert r1 > r0

    def test_increasing_registry_n_amplifies_effect(self):
        """More registry observations should pull output closer to registry rate."""
        outputs = []
        for n in [1, 5, 10, 50]:
            out = aggregate_confidence(
                conf_spec=0.3, conf_impl=0.3, conf_test=0.3,
                registry_success_rate=0.9,  # high registry → should pull up
                registry_n=n,
            )
            outputs.append(out)
        for o0, o1 in zip(outputs, outputs[1:]):
            assert o1 >= o0  # non-decreasing as more observations confirm high rate
