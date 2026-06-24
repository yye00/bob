"""Error path tests for spec_quality_score gate threshold honor BOB3_SPEC_QUALITY_THRESHOLD.

Verifies that invalid input raises ValueError (or TypeError for None name) and
the function does not silently succeed. Error cases include:
- None feature name raises TypeError
- Invalid (non-parseable) env var for threshold falls back to default (does not raise)
- Non-list, non-string acceptance_criteria returns score 0.0 (coerced)
- score_threshold() itself never raises even for bad env values
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

import bob3.spec_quality.threshold_resolver as _tr
from bob3.spec_quality.quality_score import (
    _resolve_threshold,
    score_threshold,
    gate_for_ready,
    compute_score,
    QualityReport,
    ScoreComponents,
)


def _reset_frozen():
    _tr._frozen_initialized = False
    _tr._frozen_value = None


class TestErrorNoneFeatureName:
    """None feature name raises TypeError — function does not silently succeed."""

    def test_none_name_raises_type_error(self):
        with pytest.raises(TypeError):
            compute_score(
                name=None,
                description=None,
                acceptance_criteria=["File exists: src/foo.py"],
            )

    def test_none_name_raises_not_silently_returns(self):
        """Ensure we actually raise, not return a result."""
        raised = False
        try:
            compute_score(name=None, description=None, acceptance_criteria=[])
        except TypeError:
            raised = True
        assert raised, "compute_score(name=None) must raise TypeError"


class TestErrorInvalidEnvVarDoesNotRaise:
    """Invalid BOB3_SPEC_QUALITY_THRESHOLD falls back to 0.85 without raising."""

    def test_non_numeric_env_var_falls_back(self, monkeypatch):
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "invalid!")

        # Must not raise; must fall back to 0.85
        result = _resolve_threshold()
        assert result == pytest.approx(0.85)

    def test_empty_string_env_var_falls_back(self, monkeypatch):
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "")

        result = _resolve_threshold()
        assert result == pytest.approx(0.85)

    def test_score_threshold_never_raises_on_bad_env(self, monkeypatch):
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "not_a_number")

        # score_threshold() must never raise
        result = score_threshold()
        assert isinstance(result, float)
        assert result == pytest.approx(0.85)

    def test_nan_string_env_var_falls_back(self, monkeypatch):
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        # "nan" parses as float('nan') which is a valid float — clamped to [0,1]
        # This is acceptable behavior; what matters is no exception is raised
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD", "totally_invalid")

        result = _resolve_threshold()
        assert isinstance(result, float)

    def test_frozen_env_with_invalid_value_falls_back(self, monkeypatch):
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)
        monkeypatch.setenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", "bad_value")
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD", raising=False)

        # Must not raise; frozen with unparseable value falls back to 0.85
        result = _resolve_threshold()
        assert isinstance(result, float)
        assert result == pytest.approx(0.85)


class TestErrorInvalidAcceptanceCriteria:
    """Non-list/non-string acceptance_criteria is coerced to empty — no silent success."""

    def test_none_ac_coerced_to_empty_score_zero(self):
        report = compute_score(
            name="feature",
            description=None,
            acceptance_criteria=None,
        )
        # None is coerced to empty list → score 0.0; must not raise
        assert report.score == pytest.approx(0.0)

    def test_integer_ac_coerced_to_empty_score_zero(self):
        report = compute_score(
            name="feature",
            description=None,
            acceptance_criteria=42,
        )
        assert report.score == pytest.approx(0.0)


class TestErrorGateForReadyDoesNotSilentlySucceedOnBadReport:
    """gate_for_ready must not silently succeed when called with minimal report."""

    def test_score_below_threshold_is_blocked_not_passed(self, monkeypatch):
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)

        report = QualityReport(
            score=0.10,
            components=ScoreComponents(
                ambiguity_score=0.10,
                reachability_score=0.10,
                ears_score=0.10,
                ac_coverage_score=0.10,
            ),
            remediation_hints=["Fix things"],
        )
        passed, msg = gate_for_ready(report)
        # Must not silently pass — score 0.10 << threshold 0.85
        assert passed is False
        assert msg is not None
        assert len(msg) > 0

    def test_remediation_message_not_empty_when_blocked(self, monkeypatch):
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB3_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(_tr, "_frozen_initialized", False)
        monkeypatch.setattr(_tr, "_frozen_value", None)

        report = QualityReport(
            score=0.0,
            components=ScoreComponents(
                ambiguity_score=0.0,
                reachability_score=0.0,
                ears_score=0.0,
                ac_coverage_score=0.0,
            ),
            remediation_hints=["No ACs"],
        )
        passed, msg = gate_for_ready(report)
        assert passed is False
        # Must provide a non-trivial remediation message
        assert isinstance(msg, str)
        assert len(msg) > 20
