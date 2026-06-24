"""pytest: tests/test_spec_quality_threshold.py

Tests for _resolve_threshold and score_threshold in quality_score.py.

Verifies that:
- _resolve_threshold reads BOB_SPEC_QUALITY_THRESHOLD from env on every call
- _resolve_threshold clamps to [0.0, 1.0]
- _resolve_threshold falls back to 0.85 when env var is absent or unparseable
- score_threshold() returns the live threshold (not hardcoded 0.85)
- gate_for_ready uses the env var threshold
- BOB_SPEC_QUALITY_THRESHOLD_FROZEN escape hatch works for test determinism
"""
from __future__ import annotations

import os
import importlib

import pytest

import bob.spec_quality.quality_score as qs
import bob.spec_quality.threshold_resolver as tr


class TestResolveThreshold:
    """_resolve_threshold delegates to threshold_resolver and is lazy (per-call)."""

    def test_default_is_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        assert qs._resolve_threshold() == pytest.approx(0.85)

    def test_reads_env_var(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")
        assert qs._resolve_threshold() == pytest.approx(0.55)

    def test_clamps_above_1_0(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "1.9")
        assert qs._resolve_threshold() == pytest.approx(1.0)

    def test_clamps_below_0_0(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "-0.3")
        assert qs._resolve_threshold() == pytest.approx(0.0)

    def test_unparseable_falls_back_to_default(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "not_a_float")
        assert qs._resolve_threshold() == pytest.approx(0.85)

    def test_lazy_reflects_env_change_between_calls(self, monkeypatch):
        """Two consecutive calls with different env values yield different thresholds."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.70")
        first = qs._resolve_threshold()

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.40")
        second = qs._resolve_threshold()

        assert first == pytest.approx(0.70)
        assert second == pytest.approx(0.40)

    def test_frozen_escape_hatch(self, monkeypatch):
        """BOB_SPEC_QUALITY_THRESHOLD_FROZEN pins threshold for deterministic tests."""
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "0.60")
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)

        first = qs._resolve_threshold()
        # Change the live env — frozen should ignore it
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.10")
        second = qs._resolve_threshold()

        assert first == pytest.approx(0.60)
        assert second == pytest.approx(0.60)


class TestScoreThreshold:
    """score_threshold() MUST return the live threshold, not hardcoded 0.85."""

    def test_default_is_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        assert qs.score_threshold() == pytest.approx(0.85)

    def test_honors_env_var(self, monkeypatch):
        """score_threshold() must return the env-controlled value, not hardcoded 0.85."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")
        assert qs.score_threshold() == pytest.approx(0.55)

    def test_honors_low_threshold(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.0")
        assert qs.score_threshold() == pytest.approx(0.0)

    def test_is_not_hardcoded_constant(self, monkeypatch):
        """score_threshold() must not return 0.85 when env overrides it."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.30")
        result = qs.score_threshold()
        assert result != 0.85, "score_threshold must not be hardcoded to 0.85"
        assert result == pytest.approx(0.30)


class TestGateForReadyUsesEnvThreshold:
    """gate_for_ready() must use the env-controlled threshold."""

    def _make_report(self, score: float) -> qs.QualityReport:
        return qs.QualityReport(
            score=score,
            components=qs.ScoreComponents(
                ambiguity_score=score,
                reachability_score=score,
                ears_score=score,
                ac_coverage_score=score,
            ),
        )

    def test_passes_when_score_above_env_threshold(self, monkeypatch):
        """Feature with score 0.60 passes gate when threshold=0.55."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")

        report = self._make_report(0.60)
        passed, msg = qs.gate_for_ready(report)
        assert passed is True
        assert msg is None

    def test_blocks_when_score_below_env_threshold(self, monkeypatch):
        """Feature with score 0.60 is blocked when threshold=0.70."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.70")

        report = self._make_report(0.60)
        passed, msg = qs.gate_for_ready(report)
        assert passed is False
        assert msg is not None
        assert "0.60" in msg or "0.6" in msg

    def test_operator_unstick_scenario(self, monkeypatch):
        """Operator lowering threshold to 0.55 unsticks features at score=0.39-0.84."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")

        # Features that were blocked at 0.85 should now pass at 0.55
        for score in [0.55, 0.60, 0.70, 0.80, 0.84]:
            report = self._make_report(round(score, 4))
            passed, _ = qs.gate_for_ready(report)
            assert passed is True, f"score={score} should pass gate at threshold=0.55"

        # Features genuinely below 0.55 stay blocked
        for score in [0.39, 0.40, 0.50, 0.54]:
            report = self._make_report(round(score, 4))
            passed, _ = qs.gate_for_ready(report)
            assert passed is False, f"score={score} should still be blocked at threshold=0.55"

    def test_remediation_message_shows_env_threshold(self, monkeypatch):
        """Remediation message must show the env-controlled threshold, not hardcoded 0.85."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.70")

        report = self._make_report(0.50)
        passed, msg = qs.gate_for_ready(report)
        assert passed is False
        assert "0.7" in msg, f"Expected threshold 0.70 in message, got: {msg}"
