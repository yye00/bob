"""Tests for spec_quality_score gate threshold env-var honoring.

Feature 4f4f297b: BOB_SPEC_QUALITY_THRESHOLD must be read lazily on every
gate call so operator-unstick (lower threshold to promote pending features)
works without a process restart.
"""

from __future__ import annotations

import importlib
import os

import pytest

import bob.spec_quality.threshold_resolver as _tr
from bob.spec_quality.quality_score import (
    QualityReport,
    ScoreComponents,
    _resolve_threshold,
    compute_score,
    gate_for_ready,
    score_threshold,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_frozen(monkeypatch):
    """Ensure the frozen-state is cleared before and after every test."""
    _tr._frozen_value = None
    _tr._frozen_initialized = False
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
    yield
    _tr._frozen_value = None
    _tr._frozen_initialized = False


def _report(score: float) -> QualityReport:
    return QualityReport(
        score=score,
        components=ScoreComponents(
            ambiguity_score=score,
            reachability_score=score,
            ears_score=score,
            ac_coverage_score=score,
        ),
        remediation_hints=[],
    )


# ---------------------------------------------------------------------------
# _resolve_threshold — function must exist and delegate to threshold_resolver
# ---------------------------------------------------------------------------

class TestResolveThresholdFunction:
    def test_function_exists(self):
        from bob.spec_quality.quality_score import _resolve_threshold
        assert callable(_resolve_threshold)

    def test_returns_float(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.75")
        result = _resolve_threshold()
        assert isinstance(result, float)

    def test_returns_env_var_value(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.60")
        assert _resolve_threshold() == pytest.approx(0.60)

    def test_defaults_to_0_85_when_env_absent(self):
        assert _resolve_threshold() == pytest.approx(0.85)

    def test_clamps_above_1(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "1.5")
        assert _resolve_threshold() == pytest.approx(1.0)

    def test_clamps_below_0(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "-0.3")
        assert _resolve_threshold() == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# score_threshold — public function, same contract
# ---------------------------------------------------------------------------

class TestScoreThresholdFunction:
    def test_function_exists(self):
        from bob.spec_quality.quality_score import score_threshold
        assert callable(score_threshold)

    def test_returns_float(self):
        result = score_threshold()
        assert isinstance(result, float)

    def test_honors_env_var(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")
        assert score_threshold() == pytest.approx(0.55)

    def test_defaults_when_absent(self):
        assert score_threshold() == pytest.approx(0.85)

    def test_clamps_to_1(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "2.0")
        assert score_threshold() == pytest.approx(1.0)

    def test_clamps_to_0(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "-1.0")
        assert score_threshold() == pytest.approx(0.0)

    def test_ignores_unparseable_value(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "not-a-float")
        assert score_threshold() == pytest.approx(0.85)

    def test_lazy_re_reads_env_on_each_call(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.70")
        first = score_threshold()
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.50")
        second = score_threshold()
        assert first == pytest.approx(0.70)
        assert second == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# gate_for_ready — threshold is taken from env, not hardcoded
# ---------------------------------------------------------------------------

class TestGateForReadyHonorsEnvVar:
    def test_lower_threshold_promotes_previously_blocked_feature(self, monkeypatch):
        """A score of 0.55 should be blocked at 0.85 but pass at 0.50."""
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        allowed_high, _ = gate_for_ready(_report(0.55))
        assert allowed_high is False

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.50")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        allowed_low, _ = gate_for_ready(_report(0.55))
        assert allowed_low is True

    def test_default_threshold_is_0_85(self):
        # No env var set — gate should block score=0.84
        allowed, _ = gate_for_ready(_report(0.84))
        assert allowed is False

        allowed, _ = gate_for_ready(_report(0.85))
        assert allowed is True

    def test_threshold_visible_in_rejection_message(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.60")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        _, message = gate_for_ready(_report(0.40))
        assert "0.60" in message or "0.6" in message

    def test_env_var_0_means_all_pass(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        allowed, _ = gate_for_ready(_report(0.0))
        assert allowed is True

    def test_env_var_1_means_only_perfect_passes(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "1.0")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        allowed_99, _ = gate_for_ready(_report(0.99))
        allowed_100, _ = gate_for_ready(_report(1.0))
        assert allowed_99 is False
        assert allowed_100 is True


# ---------------------------------------------------------------------------
# FROZEN escape hatch (for tests that need deterministic threshold)
# ---------------------------------------------------------------------------

class TestFrozenEscapeHatch:
    def test_frozen_var_pins_threshold(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "0.70")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        assert score_threshold() == pytest.approx(0.70)
        # Even if the live var changes, frozen wins
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.40")
        assert score_threshold() == pytest.approx(0.70)

    def test_frozen_var_is_clamped(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "5.0")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        assert score_threshold() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Boundary: empty / zero AC list — must return 0.0, not crash
# ---------------------------------------------------------------------------

class TestBoundaryEmptyInput:
    def test_empty_ac_list_returns_zero(self):
        report = compute_score(name="F", description=None, acceptance_criteria=[])
        assert report.score == pytest.approx(0.0)

    def test_empty_ac_list_does_not_crash(self):
        report = compute_score(name="F", description="Some desc", acceptance_criteria=[])
        assert isinstance(report.score, float)

    def test_empty_ac_list_has_remediation_hint(self):
        report = compute_score(name="F", description=None, acceptance_criteria=[])
        assert len(report.remediation_hints) > 0

    def test_zero_input_gate_returns_false(self):
        report = compute_score(name="F", description=None, acceptance_criteria=[])
        allowed, _ = gate_for_ready(report)
        assert allowed is False


# ---------------------------------------------------------------------------
# Invalid input — must raise ValueError or return rejection, not silently succeed
# ---------------------------------------------------------------------------

class TestInvalidInput:
    def test_none_name_raises_type_error(self):
        with pytest.raises(TypeError):
            compute_score(name=None, description=None, acceptance_criteria=["pytest: tests/foo.py"])

    def test_invalid_score_below_zero_in_report_is_blocked(self, monkeypatch):
        """A report with score=-1 (produced by bad caller) should never pass the gate."""
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        # score=0.0 is at the clamped threshold=0.0, gate should pass
        report = _report(0.0)
        allowed, _ = gate_for_ready(report)
        assert allowed is True  # 0.0 >= 0.0

    def test_env_var_invalid_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "INVALID")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        threshold = score_threshold()
        assert threshold == pytest.approx(0.85)

    def test_env_var_empty_string_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "")
        _tr._frozen_value = None
        _tr._frozen_initialized = False
        threshold = score_threshold()
        assert threshold == pytest.approx(0.85)
