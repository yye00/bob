"""pytest: tests/test_spec_quality.py

Tests for feature 0e9cce0e: spec_quality_score gate threshold MUST honor
BOB_SPEC_QUALITY_THRESHOLD env var.

Acceptance criteria verified:
  - File exists: src/bob/spec_quality/quality_score.py
  - Function defined: bob.spec_quality.quality_score._resolve_threshold
  - Function defined: bob.spec_quality.quality_score.score_threshold
  - integration: bob.spec_quality
"""
from __future__ import annotations

import importlib
import os

import pytest

import bob.spec_quality.quality_score as qs
import bob.spec_quality.threshold_resolver as tr


# ---------------------------------------------------------------------------
# AC: File exists: src/bob/spec_quality/quality_score.py
# ---------------------------------------------------------------------------

class TestFileExists:
    def test_quality_score_module_importable(self):
        """quality_score.py must exist and be importable."""
        module = importlib.import_module("bob.spec_quality.quality_score")
        assert module is not None

    def test_quality_score_file_on_disk(self):
        from pathlib import Path
        p = Path(__file__).parent.parent / "src" / "bob" / "spec_quality" / "quality_score.py"
        assert p.exists(), f"Expected file at {p}"


# ---------------------------------------------------------------------------
# AC: Function defined: bob.spec_quality.quality_score._resolve_threshold
# ---------------------------------------------------------------------------

class TestResolveThresholdDefined:
    def test_function_exists(self):
        assert callable(qs._resolve_threshold)

    def test_returns_float(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        result = qs._resolve_threshold()
        assert isinstance(result, float)

    def test_default_is_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        assert qs._resolve_threshold() == pytest.approx(0.85)

    def test_reads_env_var_on_every_call(self, monkeypatch):
        """Lazy evaluation: env var change between calls takes effect immediately."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.70")
        first = qs._resolve_threshold()

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.40")
        second = qs._resolve_threshold()

        assert first == pytest.approx(0.70)
        assert second == pytest.approx(0.40)

    def test_clamps_above_1_0(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "2.5")
        assert qs._resolve_threshold() == pytest.approx(1.0)

    def test_clamps_below_0_0(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "-1.0")
        assert qs._resolve_threshold() == pytest.approx(0.0)

    def test_unparseable_falls_back_to_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "banana")
        assert qs._resolve_threshold() == pytest.approx(0.85)

    def test_frozen_escape_hatch_pins_value(self, monkeypatch):
        """BOB_SPEC_QUALITY_THRESHOLD_FROZEN pins threshold for deterministic tests."""
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", "0.60")
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)

        first = qs._resolve_threshold()
        # Even if live env changes, frozen value stays
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.10")
        second = qs._resolve_threshold()

        assert first == pytest.approx(0.60)
        assert second == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# AC: Function defined: bob.spec_quality.quality_score.score_threshold
# ---------------------------------------------------------------------------

class TestScoreThresholdDefined:
    def test_function_exists(self):
        assert callable(qs.score_threshold)

    def test_returns_float(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        result = qs.score_threshold()
        assert isinstance(result, float)

    def test_default_is_0_85(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD", raising=False)
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        assert qs.score_threshold() == pytest.approx(0.85)

    def test_honors_env_var(self, monkeypatch):
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")
        assert qs.score_threshold() == pytest.approx(0.55)

    def test_is_not_hardcoded(self, monkeypatch):
        """score_threshold() must NOT return 0.85 when env overrides it."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.30")
        result = qs.score_threshold()
        assert result != 0.85, "score_threshold must not be hardcoded to 0.85"
        assert result == pytest.approx(0.30)

    def test_delegates_to_resolve_threshold(self, monkeypatch):
        """score_threshold() must produce identical result to _resolve_threshold()."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.72")
        assert qs.score_threshold() == qs._resolve_threshold()


# ---------------------------------------------------------------------------
# AC: integration: bob.spec_quality
# ---------------------------------------------------------------------------

class TestIntegrationBobSpecQuality:
    """Verify the bob.spec_quality package is reachable and the gate is wired correctly."""

    def test_package_importable(self):
        pkg = importlib.import_module("bob.spec_quality")
        assert pkg is not None

    def test_quality_score_module_importable(self):
        mod = importlib.import_module("bob.spec_quality.quality_score")
        assert mod is not None

    def test_threshold_resolver_importable(self):
        mod = importlib.import_module("bob.spec_quality.threshold_resolver")
        assert mod is not None

    def test_gate_for_ready_uses_env_threshold(self, monkeypatch):
        """gate_for_ready must use env-controlled threshold, not hardcoded 0.85."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")

        # score=0.60 would be blocked at 0.85 but passes at 0.55
        report = qs.QualityReport(
            score=0.60,
            components=qs.ScoreComponents(
                ambiguity_score=0.60,
                reachability_score=0.60,
                ears_score=0.60,
                ac_coverage_score=0.60,
            ),
        )
        passed, msg = qs.gate_for_ready(report)
        assert passed is True, "score=0.60 should pass gate at threshold=0.55"
        assert msg is None

    def test_operator_unstick_scenario(self, monkeypatch):
        """Operator lowers threshold to 0.55 to unstick features at score=0.39-0.84."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.55")

        def _report(score: float) -> qs.QualityReport:
            return qs.QualityReport(
                score=score,
                components=qs.ScoreComponents(
                    ambiguity_score=score,
                    reachability_score=score,
                    ears_score=score,
                    ac_coverage_score=score,
                ),
            )

        # Features above new threshold should now pass
        for score in [0.55, 0.60, 0.70, 0.80, 0.84]:
            passed, _ = qs.gate_for_ready(_report(score))
            assert passed is True, f"score={score} should pass at threshold=0.55"

        # Features genuinely below 0.55 remain blocked
        for score in [0.39, 0.40, 0.50, 0.54]:
            passed, _ = qs.gate_for_ready(_report(score))
            assert passed is False, f"score={score} should still be blocked at threshold=0.55"

    def test_remediation_message_shows_env_threshold(self, monkeypatch):
        """Remediation message must display the env threshold, not hardcoded 0.85."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)
        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.70")

        report = qs.QualityReport(
            score=0.50,
            components=qs.ScoreComponents(
                ambiguity_score=0.50,
                reachability_score=0.50,
                ears_score=0.50,
                ac_coverage_score=0.50,
            ),
        )
        passed, msg = qs.gate_for_ready(report)
        assert passed is False
        assert msg is not None
        assert "0.7" in msg, f"Expected threshold 0.70 in message, got: {msg}"

    def test_env_change_mid_run_takes_effect(self, monkeypatch):
        """Threshold is re-read on every gate call — mid-run env changes are honoured."""
        monkeypatch.delenv("BOB_SPEC_QUALITY_THRESHOLD_FROZEN", raising=False)
        monkeypatch.setattr(tr, "_frozen_initialized", False)
        monkeypatch.setattr(tr, "_frozen_value", None)

        report = qs.QualityReport(
            score=0.60,
            components=qs.ScoreComponents(
                ambiguity_score=0.60,
                reachability_score=0.60,
                ears_score=0.60,
                ac_coverage_score=0.60,
            ),
        )

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.70")
        passed_high, _ = qs.gate_for_ready(report)
        assert passed_high is False, "score=0.60 should be blocked at threshold=0.70"

        monkeypatch.setenv("BOB_SPEC_QUALITY_THRESHOLD", "0.50")
        passed_low, _ = qs.gate_for_ready(report)
        assert passed_low is True, "score=0.60 should pass at threshold=0.50"
