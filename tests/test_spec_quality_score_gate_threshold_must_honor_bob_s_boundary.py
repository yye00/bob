"""Boundary tests for the env-honoring spec-quality gate threshold.

Empty, zero, and minimum inputs must return a well-defined result rather than
raising.
"""
from __future__ import annotations

import importlib

import pytest

from bob.spec_quality import quality_score
from bob.spec_quality.quality_score import (
    QualityReport,
    ScoreComponents,
    _resolve_threshold,
    gate_for_ready,
    score_threshold,
)


def _report(score: float) -> QualityReport:
    return QualityReport(
        score=score,
        components=ScoreComponents(
            ambiguity_score=score,
            reachability_score=score,
            ears_score=score,
            ac_coverage_score=score,
        ),
    )


class TestBoundary:
    def test_empty_env_var_uses_default(self, monkeypatch):
        """An empty-string env var is treated as unset -> default 0.85."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "")
        assert _resolve_threshold() == pytest.approx(0.85)

    def test_threshold_zero(self, monkeypatch):
        """Threshold of exactly 0.0 admits every feature, including score 0.0."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        assert score_threshold() == pytest.approx(0.0)
        passed, msg = gate_for_ready(_report(0.0))
        assert passed is True
        assert msg is None

    def test_threshold_exactly_one(self, monkeypatch):
        """Threshold of exactly 1.0 admits only a perfect-scoring feature."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "1.0")
        assert score_threshold() == pytest.approx(1.0)
        assert gate_for_ready(_report(1.0))[0] is True
        assert gate_for_ready(_report(0.999999))[0] is False

    def test_score_equal_to_threshold_passes(self, monkeypatch):
        """A score exactly equal to the threshold passes the gate (>=)."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")
        passed, msg = gate_for_ready(_report(0.55))
        assert passed is True
        assert msg is None

    def test_frozen_empty_falls_back_to_default(self, monkeypatch):
        """An empty FROZEN value pins the default rather than raising."""
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "")
        importlib.reload(quality_score)
        # Empty string is a set-but-unparseable frozen value -> default.
        assert quality_score._resolve_threshold() == pytest.approx(0.85)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        importlib.reload(quality_score)
