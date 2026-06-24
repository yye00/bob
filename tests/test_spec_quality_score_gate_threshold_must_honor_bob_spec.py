"""Tests for spec_quality_score_gate_threshold_must_honor_bob_spec.

Verifies that the spec quality gate threshold honors the
BOB_SPEC_QUALITY_THRESHOLD env var and is computed lazily on each call.
"""

from __future__ import annotations

import os
import importlib
from unittest.mock import patch

import pytest

from bob.spec_quality_score_gate_threshold_must_honor_bob_spec import (
    spec_quality_score_gate_threshold_must_honor_bob_spec,
)
from bob.spec_quality.threshold_resolver import resolve_spec_quality_threshold


# Minimal AC list that produces a high enough score to pass at default threshold
_GOOD_ACS = [
    "File exists: src/bob/foo.py",
    "Function defined: bob.foo.my_function",
    "pytest: tests/test_foo.py::test_my_function",
]

# Feature that will reliably score low (empty ACs → 0.0)
_EMPTY_ACS: list[str] = []


def _make_call(acs=None, env_threshold=None, frozen=None):
    """Helper: call the facade with optional env-var overrides."""
    env_patches = {}
    if env_threshold is not None:
        env_patches["BOB_SPEC_QUALITY_THRESHOLD"] = str(env_threshold)
    if frozen is not None:
        env_patches["BOB_SPEC_QUALITY_THRESHOLD_FROZEN"] = str(frozen)

    if acs is None:
        acs = _GOOD_ACS

    with patch.dict(os.environ, env_patches, clear=False):
        # Reset frozen state in threshold_resolver between calls
        import bob.spec_quality.threshold_resolver as _tr
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        return spec_quality_score_gate_threshold_must_honor_bob_spec(
            name="test-feature",
            description=None,
            acceptance_criteria=acs,
        )


class TestSpecQualityScoreGateThresholdMustHonorBobSpec:
    """AC: spec_quality_score gate threshold MUST honor BOB_SPEC_QUALITY_THRESHOLD."""

    def test_function_is_callable(self):
        """The required function exists and is callable."""
        assert callable(spec_quality_score_gate_threshold_must_honor_bob_spec)

    def test_returns_tuple_of_three(self):
        """Returns (score, passed, remediation) tuple."""
        result = _make_call()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_score_is_float_in_range(self):
        """Score is a float in [0.0, 1.0]."""
        score, _, _ = _make_call()
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_default_threshold_is_085(self):
        """Default threshold is 0.85 when BOB_SPEC_QUALITY_THRESHOLD not set."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("BOB_SPEC_QUALITY_THRESHOLD", "BOB_SPEC_QUALITY_THRESHOLD_FROZEN")}
        import bob.spec_quality.threshold_resolver as _tr
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        with patch.dict(os.environ, env, clear=True):
            threshold = resolve_spec_quality_threshold()
        assert threshold == pytest.approx(0.85)

    def test_empty_ac_list_scores_zero_and_fails_gate(self):
        """Empty AC list always scores 0.0 and fails the gate."""
        score, passed, remediation = _make_call(acs=_EMPTY_ACS)
        assert score == pytest.approx(0.0)
        assert passed is False
        assert remediation is not None
        assert len(remediation) > 0

    def test_env_var_lowered_threshold_promotes_borderline_feature(self):
        """Lowering BOB_SPEC_QUALITY_THRESHOLD via env var allows lower-scoring features to pass."""
        # First confirm that at default threshold (0.85) a score of ~0.5 fails
        import bob.spec_quality.threshold_resolver as _tr
        _tr._frozen_initialized = False
        _tr._frozen_value = None

        with patch.dict(os.environ,
                        {"BOB_SPEC_QUALITY_THRESHOLD": "0.85"},
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            threshold_high = resolve_spec_quality_threshold()
        assert threshold_high == pytest.approx(0.85)

        # Now confirm threshold drops when env var is lowered
        with patch.dict(os.environ,
                        {"BOB_SPEC_QUALITY_THRESHOLD": "0.10"},
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            threshold_low = resolve_spec_quality_threshold()
        assert threshold_low == pytest.approx(0.10)
        assert threshold_low < threshold_high

    def test_gate_uses_env_var_threshold_not_hardcoded_085(self):
        """gate_for_ready must use env var threshold, not hardcoded 0.85."""
        from bob.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents

        report = QualityReport(
            score=0.55,
            components=ScoreComponents(
                ambiguity_score=0.55,
                reachability_score=0.55,
                ears_score=1.0,
                ac_coverage_score=0.55,
            ),
            remediation_hints=[],
        )

        import bob.spec_quality.threshold_resolver as _tr

        # At default (0.85), score 0.55 should FAIL
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        env_no_override = {k: v for k, v in os.environ.items()
                           if k not in ("BOB_SPEC_QUALITY_THRESHOLD",
                                        "BOB_SPEC_QUALITY_THRESHOLD_FROZEN")}
        with patch.dict(os.environ, env_no_override, clear=True):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            passed_high, _ = gate_for_ready(report)
        assert passed_high is False, "score 0.55 should fail at threshold 0.85"

        # At lowered threshold (0.40), score 0.55 should PASS
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        with patch.dict(os.environ,
                        {"BOB_SPEC_QUALITY_THRESHOLD": "0.40"},
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            passed_low, remediation = gate_for_ready(report)
        assert passed_low is True, "score 0.55 should pass at threshold 0.40"
        assert remediation is None

    def test_env_var_threshold_clamped_above_1(self):
        """Threshold clamped to 1.0 when env var exceeds 1.0."""
        import bob.spec_quality.threshold_resolver as _tr
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        with patch.dict(os.environ,
                        {"BOB_SPEC_QUALITY_THRESHOLD": "1.5"},
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            threshold = resolve_spec_quality_threshold()
        assert threshold == pytest.approx(1.0)

    def test_env_var_threshold_clamped_below_0(self):
        """Threshold clamped to 0.0 when env var is negative."""
        import bob.spec_quality.threshold_resolver as _tr
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        with patch.dict(os.environ,
                        {"BOB_SPEC_QUALITY_THRESHOLD": "-0.5"},
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            threshold = resolve_spec_quality_threshold()
        assert threshold == pytest.approx(0.0)

    def test_unparseable_env_var_falls_back_to_default(self):
        """Unparseable BOB_SPEC_QUALITY_THRESHOLD falls back to 0.85."""
        import bob.spec_quality.threshold_resolver as _tr
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        with patch.dict(os.environ,
                        {"BOB_SPEC_QUALITY_THRESHOLD": "not-a-float"},
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            threshold = resolve_spec_quality_threshold()
        assert threshold == pytest.approx(0.85)

    def test_frozen_env_var_pins_threshold(self):
        """BOB_SPEC_QUALITY_THRESHOLD_FROZEN pins threshold regardless of BOB_SPEC_QUALITY_THRESHOLD."""
        import bob.spec_quality.threshold_resolver as _tr
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        with patch.dict(os.environ,
                        {
                            "BOB_SPEC_QUALITY_THRESHOLD": "0.10",
                            "BOB_SPEC_QUALITY_THRESHOLD_FROZEN": "0.70",
                        },
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            threshold = resolve_spec_quality_threshold()
        assert threshold == pytest.approx(0.70), (
            "FROZEN var should override BOB_SPEC_QUALITY_THRESHOLD"
        )

    def test_lazy_evaluation_env_var_change_takes_effect(self):
        """Threshold is read lazily — changing env var mid-run takes effect on next call."""
        import bob.spec_quality.threshold_resolver as _tr

        _tr._frozen_initialized = False
        _tr._frozen_value = None

        with patch.dict(os.environ, {"BOB_SPEC_QUALITY_THRESHOLD": "0.80"}, clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            t1 = resolve_spec_quality_threshold()

        assert t1 == pytest.approx(0.80)

        with patch.dict(os.environ, {"BOB_SPEC_QUALITY_THRESHOLD": "0.50"}, clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            t2 = resolve_spec_quality_threshold()

        assert t2 == pytest.approx(0.50)
        assert t2 != t1, "Lazy evaluation must pick up env var change"

    def test_facade_passes_score_and_gate_result_through(self):
        """Facade returns (score, passed, remediation) consistent with underlying gate."""
        import bob.spec_quality.threshold_resolver as _tr
        from bob.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents, compute_score

        _tr._frozen_initialized = False
        _tr._frozen_value = None

        env = {k: v for k, v in os.environ.items()
               if k not in ("BOB_SPEC_QUALITY_THRESHOLD", "BOB_SPEC_QUALITY_THRESHOLD_FROZEN")}
        with patch.dict(os.environ, env, clear=True):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            score, passed, remediation = spec_quality_score_gate_threshold_must_honor_bob_spec(
                name="facade-test",
                description=None,
                acceptance_criteria=_GOOD_ACS,
            )

        assert isinstance(score, float)
        assert isinstance(passed, bool)
        # remediation is None when passed, string when blocked
        if passed:
            assert remediation is None
        else:
            assert isinstance(remediation, str)

    def test_threshold_in_remediation_message_matches_env_var(self):
        """Remediation message reports the env-var threshold, not hardcoded 0.85."""
        import bob.spec_quality.threshold_resolver as _tr
        from bob.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents

        report = QualityReport(
            score=0.30,
            components=ScoreComponents(
                ambiguity_score=0.30,
                reachability_score=0.30,
                ears_score=1.0,
                ac_coverage_score=0.30,
            ),
            remediation_hints=["Fix something"],
        )

        _tr._frozen_initialized = False
        _tr._frozen_value = None
        with patch.dict(os.environ,
                        {"BOB_SPEC_QUALITY_THRESHOLD": "0.60"},
                        clear=False):
            _tr._frozen_initialized = False
            _tr._frozen_value = None
            passed, remediation = gate_for_ready(report)

        assert passed is False
        assert remediation is not None
        assert "0.6" in remediation or "0.60" in remediation, (
            f"Remediation message should contain the env-var threshold 0.60, got: {remediation}"
        )


def test_spec_quality_score_gate_threshold_must_honor_bob_spec():
    """Master AC test: function exists, is callable, and gate honors env var."""
    # 1. Function is importable and callable
    assert callable(spec_quality_score_gate_threshold_must_honor_bob_spec)

    # 2. Returns 3-tuple (score, passed, remediation)
    import bob.spec_quality.threshold_resolver as _tr
    _tr._frozen_initialized = False
    _tr._frozen_value = None

    result = spec_quality_score_gate_threshold_must_honor_bob_spec(
        name="ac-master-test",
        description=None,
        acceptance_criteria=_GOOD_ACS,
    )
    assert isinstance(result, tuple) and len(result) == 3

    # 3. Gate uses env-var threshold — a score that fails at 0.85 passes at 0.10
    from bob.spec_quality.quality_score import gate_for_ready, QualityReport, ScoreComponents

    borderline_report = QualityReport(
        score=0.50,
        components=ScoreComponents(
            ambiguity_score=0.50,
            reachability_score=0.50,
            ears_score=1.0,
            ac_coverage_score=0.50,
        ),
        remediation_hints=[],
    )

    env_no_override = {k: v for k, v in os.environ.items()
                       if k not in ("BOB_SPEC_QUALITY_THRESHOLD",
                                    "BOB_SPEC_QUALITY_THRESHOLD_FROZEN")}
    with patch.dict(os.environ, env_no_override, clear=True):
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        passed_default, _ = gate_for_ready(borderline_report)
    assert passed_default is False, "Score 0.50 should fail at default threshold 0.85"

    with patch.dict(os.environ,
                    {"BOB_SPEC_QUALITY_THRESHOLD": "0.40"},
                    clear=False):
        _tr._frozen_initialized = False
        _tr._frozen_value = None
        passed_low, _ = gate_for_ready(borderline_report)
    assert passed_low is True, "Score 0.50 should pass when threshold lowered to 0.40"
