"""Error path tests for the env-honoring spec-quality gate threshold.

Invalid input raises ValueError (TypeError for a None feature name) and the
function does not silently succeed. Unparseable env thresholds must fall back
to the default without raising, so a typo in an operator's env var can never
crash the gate.
"""
from __future__ import annotations

import pytest

import bob.spec_quality.threshold_resolver as _tr
from bob.spec_quality import quality_score as _qs
from bob.spec_quality.quality_score import (
    QualityReport,
    ScoreComponents,
    _resolve_threshold,
    compute_score,
    gate_for_ready,
    score_threshold,
)


def _reset_frozen(monkeypatch):
    monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
    monkeypatch.setattr(_tr, "_frozen_initialized", False)
    monkeypatch.setattr(_tr, "_frozen_value", None)


def _report(score: float) -> QualityReport:
    return QualityReport(
        score=score,
        components=ScoreComponents(
            ambiguity_score=score,
            reachability_score=score,
            ears_score=score,
            ac_coverage_score=score,
        ),
        remediation_hints=["fix it"],
    )


class TestNoneNameRaisesTypeError:
    def test_none_name_raises(self):
        with pytest.raises(TypeError):
            compute_score(name=None, description=None, acceptance_criteria=["x"])

    def test_none_name_does_not_silently_return(self):
        raised = False
        try:
            compute_score(name=None, description=None, acceptance_criteria=[])
        except TypeError:
            raised = True
        assert raised


class TestBelowThresholdRaises:
    def test_raises_below_threshold_raises(self, monkeypatch):
        _reset_frozen(monkeypatch)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
        with pytest.raises(_qs.BelowQualityScoreError):
            _qs.raises_below_threshold(_report(0.10))

    def test_raises_below_threshold_silent_when_passing(self, monkeypatch):
        _reset_frozen(monkeypatch)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.05")
        # Score above the lowered threshold — must NOT raise.
        _qs.raises_below_threshold(_report(0.10))


class TestInvalidEnvFallsBackNeverRaises:
    def test_unparseable_threshold_falls_back(self, monkeypatch):
        _reset_frozen(monkeypatch)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "not-a-float")
        assert _resolve_threshold() == pytest.approx(0.85)

    def test_score_threshold_never_raises_on_bad_env(self, monkeypatch):
        _reset_frozen(monkeypatch)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "%%%")
        assert isinstance(score_threshold(), float)

    def test_frozen_unparseable_falls_back(self, monkeypatch):
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "garbage")
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        assert _resolve_threshold() == pytest.approx(0.85)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)


class TestGateDoesNotSilentlySucceed:
    def test_below_threshold_blocked(self, monkeypatch):
        _reset_frozen(monkeypatch)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
        passed, msg = gate_for_ready(_report(0.10))
        assert passed is False
        assert msg and len(msg) > 20
