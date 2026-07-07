"""Tests for the env-honoring spec-quality gate threshold.

Verifies that ``bob.spec_quality.quality_score._resolve_threshold`` and
``score_threshold`` read ``BOB_SPEC_QUALITY_THRESHOLD`` lazily on every call,
clamp to [0.0, 1.0], fall back to 0.85, and support the
``BOB_SPEC_QUALITY_THRESHOLD_FROZEN`` escape hatch.

Regression: a prior generation hardcoded ``_THRESHOLD = 0.85`` at import time,
so relaunching with ``BOB_SPEC_QUALITY_THRESHOLD=0.55`` was a silent no-op and
the chain exited ALL_BLOCKED. The threshold MUST be computed per-call.
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


class TestResolveThreshold:
    def test_default_is_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        assert _resolve_threshold() == pytest.approx(0.85)

    def test_reads_env(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")
        assert _resolve_threshold() == pytest.approx(0.55)

    def test_lazy_reevaluation_between_calls(self, monkeypatch):
        """The env var change must take effect on the very next call (no restart)."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
        assert _resolve_threshold() == pytest.approx(0.85)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.40")
        assert _resolve_threshold() == pytest.approx(0.40)

    def test_clamps_high(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "5.0")
        assert _resolve_threshold() == pytest.approx(1.0)

    def test_clamps_low(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "-2.0")
        assert _resolve_threshold() == pytest.approx(0.0)

    def test_unparseable_falls_back(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "banana")
        assert _resolve_threshold() == pytest.approx(0.85)


class TestScoreThreshold:
    def test_matches_resolver(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.60")
        assert score_threshold() == pytest.approx(0.60)

    def test_not_frozen_at_import(self, monkeypatch):
        """score_threshold must not be a module-level constant frozen at import."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.30")
        importlib.reload(quality_score)
        assert quality_score.score_threshold() == pytest.approx(0.30)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.75")
        assert quality_score.score_threshold() == pytest.approx(0.75)


class TestGateHonorsThreshold:
    def test_lowering_threshold_unsticks_feature(self, monkeypatch):
        """A 0.55-scoring feature is blocked at 0.85 but promoted at 0.50."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        rpt = _report(0.55)

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.85")
        passed, msg = gate_for_ready(rpt)
        assert passed is False
        assert msg is not None

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.50")
        passed, msg = gate_for_ready(rpt)
        assert passed is True
        assert msg is None


class TestFrozenEscapeHatch:
    def test_frozen_pins_value(self, monkeypatch):
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "0.42")
        # Reload so frozen state is initialised fresh from this env.
        importlib.reload(quality_score)
        assert quality_score._resolve_threshold() == pytest.approx(0.42)
        # Even if the non-frozen var changes, the frozen value holds.
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.90")
        assert quality_score._resolve_threshold() == pytest.approx(0.42)
        # Clean up frozen module state for other tests.
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        importlib.reload(quality_score)
