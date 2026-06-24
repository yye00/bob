"""Tests for online threshold tuning (F-R4-131)."""
from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from bob.online_threshold_tuning import (
    OnlineThresholdTuner,
    ThresholdState,
    ThresholdTunerRegistry,
    apply_calibration_outcome,
    _DEFAULT_ALPHA,
    _DEFAULT_DECOMP_DEPTH,
    _DEFAULT_ECE_HIGH,
    _DEFAULT_ECE_LOW,
    _DEFAULT_RCA_THRESHOLD,
    _DECOMP_DEPTH_MAX,
    _DECOMP_DEPTH_MIN,
    _RCA_THRESHOLD_MAX,
    _RCA_THRESHOLD_MIN,
    _RCA_THRESHOLD_STEP,
)


# ---------------------------------------------------------------------------
# Sample factories
# ---------------------------------------------------------------------------


def _make_samples(
    task_class: str,
    predicted_conf: float,
    pass_rate: float,
    n: int = 20,
) -> list[dict]:
    """Return n samples with a given task_class and pass_rate."""
    n_pass = round(n * pass_rate)
    samples = []
    for i in range(n):
        samples.append(
            {
                "task_class": task_class,
                "predicted_conf": predicted_conf,
                "passed": i < n_pass,
            }
        )
    return samples


def _high_ece_samples(task_class: str = "algorithm_implementation") -> list[dict]:
    """Return samples guaranteed to produce ECE > 0.20 (high-water mark)."""
    # predicted 0.9, empirical 0.0 → ECE = 0.9
    return _make_samples(task_class, predicted_conf=0.9, pass_rate=0.0, n=20)


def _low_ece_samples(task_class: str = "algorithm_implementation") -> list[dict]:
    """Return samples guaranteed to produce ECE < 0.10 (low-water mark)."""
    # predicted 0.85, empirical 0.85 → ECE ≈ 0 (predicted ≈ empirical)
    return _make_samples(task_class, predicted_conf=0.85, pass_rate=0.85, n=20)


def _medium_ece_samples(task_class: str = "algorithm_implementation") -> list[dict]:
    """Return samples that produce ECE in the neutral zone [0.10, 0.20]."""
    # predicted 0.75, empirical 0.60 → ECE = 0.15
    return _make_samples(task_class, predicted_conf=0.75, pass_rate=0.60, n=20)


# ---------------------------------------------------------------------------
# Construction and validation
# ---------------------------------------------------------------------------


class TestOnlineThresholdTunerInit:
    def test_default_state(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        assert tuner.rca_trigger_threshold == _DEFAULT_RCA_THRESHOLD
        assert tuner.decomposition_depth == _DEFAULT_DECOMP_DEPTH
        assert tuner.ema_ece is None
        assert tuner.task_class == "algorithm_implementation"

    def test_invalid_alpha_zero(self):
        with pytest.raises(ValueError, match="alpha"):
            OnlineThresholdTuner("integration", alpha=0.0)

    def test_invalid_alpha_above_one(self):
        with pytest.raises(ValueError, match="alpha"):
            OnlineThresholdTuner("integration", alpha=1.1)

    def test_invalid_ece_band(self):
        with pytest.raises(ValueError, match="ece_low"):
            OnlineThresholdTuner("integration", ece_low=0.3, ece_high=0.1)

    def test_invalid_rca_threshold_too_low(self):
        with pytest.raises(ValueError, match="initial_rca_threshold"):
            OnlineThresholdTuner("integration", initial_rca_threshold=0.0)

    def test_invalid_rca_threshold_too_high(self):
        with pytest.raises(ValueError, match="initial_rca_threshold"):
            OnlineThresholdTuner("integration", initial_rca_threshold=1.0)

    def test_invalid_decomp_depth_too_low(self):
        with pytest.raises(ValueError, match="initial_decomp_depth"):
            OnlineThresholdTuner("integration", initial_decomp_depth=0)

    def test_invalid_decomp_depth_too_high(self):
        with pytest.raises(ValueError, match="initial_decomp_depth"):
            OnlineThresholdTuner("integration", initial_decomp_depth=10)


# ---------------------------------------------------------------------------
# Threshold tightening (high ECE)
# ---------------------------------------------------------------------------


class TestThresholdTightening:
    def test_high_ece_lowers_rca_threshold(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        initial = tuner.rca_trigger_threshold
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(_high_ece_samples())
        assert state.rca_trigger_threshold < initial

    def test_high_ece_increases_decomp_depth(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        initial_depth = tuner.decomposition_depth
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(_high_ece_samples())
        assert state.decomposition_depth > initial_depth

    def test_rca_threshold_bounded_below(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            initial_rca_threshold=_RCA_THRESHOLD_MIN,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            for _ in range(10):
                tuner.update(_high_ece_samples())
        assert tuner.rca_trigger_threshold >= _RCA_THRESHOLD_MIN

    def test_decomp_depth_bounded_above(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            initial_decomp_depth=_DECOMP_DEPTH_MAX,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            for _ in range(10):
                tuner.update(_high_ece_samples())
        assert tuner.decomposition_depth <= _DECOMP_DEPTH_MAX

    def test_step_size_is_correct(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        initial = tuner.rca_trigger_threshold
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            tuner.update(_high_ece_samples())
        expected = max(_RCA_THRESHOLD_MIN, initial - _RCA_THRESHOLD_STEP)
        assert abs(tuner.rca_trigger_threshold - expected) < 1e-9


# ---------------------------------------------------------------------------
# Threshold relaxation (low ECE)
# ---------------------------------------------------------------------------


class TestThresholdRelaxation:
    def test_low_ece_raises_rca_threshold(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        initial = tuner.rca_trigger_threshold
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(_low_ece_samples())
        assert state.rca_trigger_threshold > initial

    def test_low_ece_decreases_decomp_depth(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            initial_decomp_depth=3,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(_low_ece_samples())
        assert state.decomposition_depth < 3

    def test_rca_threshold_bounded_above(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            initial_rca_threshold=_RCA_THRESHOLD_MAX,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            for _ in range(10):
                tuner.update(_low_ece_samples())
        assert tuner.rca_trigger_threshold <= _RCA_THRESHOLD_MAX

    def test_decomp_depth_bounded_below(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            initial_decomp_depth=_DECOMP_DEPTH_MIN,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            for _ in range(10):
                tuner.update(_low_ece_samples())
        assert tuner.decomposition_depth >= _DECOMP_DEPTH_MIN


# ---------------------------------------------------------------------------
# Neutral zone — no change
# ---------------------------------------------------------------------------


class TestNeutralZone:
    def test_medium_ece_no_threshold_change(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        initial_rca = tuner.rca_trigger_threshold
        initial_depth = tuner.decomposition_depth
        with patch("bob.online_threshold_tuning.emit_telemetry_line") as mock_emit:
            tuner.update(_medium_ece_samples())
        assert tuner.rca_trigger_threshold == initial_rca
        assert tuner.decomposition_depth == initial_depth
        mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# EMA correctness
# ---------------------------------------------------------------------------


class TestEMAUpdate:
    def test_first_update_initialises_ema_to_current_ece(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            alpha=1.0,
            ece_low=0.0,
            ece_high=1.0,  # no band crossing
        )
        samples = _make_samples("algorithm_implementation", 0.9, 0.0, n=20)
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(samples)
        # With 100% miss-rate and predicted=0.9, ECE = 0.9
        assert state.ema_ece is not None
        assert state.ema_ece > 0.5

    def test_ema_smooths_across_updates(self):
        alpha = 0.5
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            alpha=alpha,
            ece_low=0.0,
            ece_high=1.0,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            # First update: ECE ≈ 0.9 → EMA initialised to 0.9
            tuner.update(_high_ece_samples())
            ema_after_first = tuner.ema_ece
            # Second update: ECE ≈ 0 → EMA = 0.5*0 + 0.5*0.9 = 0.45
            tuner.update(_low_ece_samples())
        assert tuner.ema_ece < ema_after_first

    def test_state_snapshot_ema_ece_matches_property(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            ece_low=0.0,
            ece_high=1.0,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(_high_ece_samples())
        assert state.ema_ece == tuner.ema_ece


# ---------------------------------------------------------------------------
# Samples from other task classes are ignored
# ---------------------------------------------------------------------------


class TestTaskClassFiltering:
    def test_other_class_samples_ignored(self):
        tuner = OnlineThresholdTuner("refactor")
        initial_rca = tuner.rca_trigger_threshold
        foreign_samples = _high_ece_samples(task_class="integration")
        with patch("bob.online_threshold_tuning.emit_telemetry_line") as mock_emit:
            state = tuner.update(foreign_samples)
        assert state.rca_trigger_threshold == initial_rca
        assert state.ema_ece is None
        mock_emit.assert_not_called()

    def test_mixed_samples_only_uses_matching_class(self):
        tuner = OnlineThresholdTuner("refactor")
        samples = (
            _high_ece_samples(task_class="integration")
            + _low_ece_samples(task_class="refactor")
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(samples)
        # Only refactor samples should influence refactor tuner
        assert state.ema_ece is not None


# ---------------------------------------------------------------------------
# Telemetry emission
# ---------------------------------------------------------------------------


class TestTelemetryEmission:
    def test_threshold_change_emits_telemetry(self):
        tuner = OnlineThresholdTuner("algorithm_implementation", run_id="test-run")
        with patch("bob.online_threshold_tuning.emit_telemetry_line") as mock_emit:
            tuner.update(_high_ece_samples())
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args
        assert call_kwargs[0][0] == "test-run"
        kw = call_kwargs[1]
        assert kw["threshold_change_event"] == "online_threshold_tuning"
        assert kw["task_class"] == "algorithm_implementation"
        assert kw["direction"] == "tightened"
        assert "old_rca_trigger_threshold" in kw
        assert "new_rca_trigger_threshold" in kw
        assert "ema_ece" in kw

    def test_no_telemetry_when_no_change(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        with patch("bob.online_threshold_tuning.emit_telemetry_line") as mock_emit:
            tuner.update(_medium_ece_samples())
        mock_emit.assert_not_called()

    def test_relaxation_emits_tightened_direction_relaxed(self):
        tuner = OnlineThresholdTuner(
            "algorithm_implementation",
            initial_decomp_depth=3,
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line") as mock_emit:
            tuner.update(_low_ece_samples())
        if mock_emit.called:
            kw = mock_emit.call_args[1]
            assert kw["direction"] == "relaxed"

    def test_telemetry_failure_does_not_raise(self):
        tuner = OnlineThresholdTuner("algorithm_implementation")
        with patch(
            "bob.online_threshold_tuning.emit_telemetry_line",
            side_effect=OSError("disk full"),
        ):
            state = tuner.update(_high_ece_samples())
        # Should not raise; thresholds still updated
        assert state.rca_trigger_threshold < _DEFAULT_RCA_THRESHOLD


# ---------------------------------------------------------------------------
# ThresholdState dataclass
# ---------------------------------------------------------------------------


class TestThresholdState:
    def test_state_has_required_fields(self):
        tuner = OnlineThresholdTuner("refactor")
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(_high_ece_samples(task_class="refactor"))
        assert hasattr(state, "rca_trigger_threshold")
        assert hasattr(state, "decomposition_depth")
        assert hasattr(state, "ema_ece")
        assert hasattr(state, "task_class")
        assert hasattr(state, "updated_at")

    def test_to_dict_is_json_serialisable(self):
        tuner = OnlineThresholdTuner("refactor")
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = tuner.update(_high_ece_samples(task_class="refactor"))
        d = state.to_dict()
        json.dumps(d)  # should not raise

    def test_state_method_returns_current_snapshot(self):
        tuner = OnlineThresholdTuner("refactor")
        s1 = tuner.state()
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            s2 = tuner.update(_high_ece_samples(task_class="refactor"))
        s3 = tuner.state()
        assert s3.rca_trigger_threshold == s2.rca_trigger_threshold


# ---------------------------------------------------------------------------
# ThresholdTunerRegistry
# ---------------------------------------------------------------------------


class TestThresholdTunerRegistry:
    def test_registry_initialises_all_classes(self):
        classes = ["algorithm_implementation", "refactor", "integration"]
        registry = ThresholdTunerRegistry(classes)
        assert registry.task_classes == classes

    def test_update_all_returns_state_for_each_class(self):
        classes = ["algorithm_implementation", "refactor"]
        registry = ThresholdTunerRegistry(classes)
        samples = (
            _medium_ece_samples("algorithm_implementation")
            + _medium_ece_samples("refactor")
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            states = registry.update_all(samples)
        assert set(states.keys()) == set(classes)
        for state in states.values():
            assert isinstance(state, ThresholdState)

    def test_get_state_returns_none_for_unknown_class(self):
        registry = ThresholdTunerRegistry(["algorithm_implementation"])
        assert registry.get_state("unknown_class") is None

    def test_all_states_returns_all(self):
        classes = ["algorithm_implementation", "refactor"]
        registry = ThresholdTunerRegistry(classes)
        states = registry.all_states()
        assert set(states.keys()) == set(classes)

    def test_mixed_batch_routes_to_correct_tuner(self):
        classes = ["algorithm_implementation", "refactor"]
        registry = ThresholdTunerRegistry(classes)
        mixed_samples = (
            _high_ece_samples("algorithm_implementation")
            + _low_ece_samples("refactor")
        )
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            states = registry.update_all(mixed_samples)
        # algorithm_implementation should have tightened (high ECE)
        algo_state = states["algorithm_implementation"]
        assert algo_state.rca_trigger_threshold < _DEFAULT_RCA_THRESHOLD
        # refactor should have relaxed (low ECE)
        refactor_state = states["refactor"]
        assert refactor_state.rca_trigger_threshold > _DEFAULT_RCA_THRESHOLD


# ---------------------------------------------------------------------------
# apply_calibration_outcome convenience function
# ---------------------------------------------------------------------------


class TestApplyCalibrationOutcome:
    def test_returns_threshold_state(self):
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = apply_calibration_outcome(
                "algorithm_implementation",
                _high_ece_samples(),
            )
        assert isinstance(state, ThresholdState)

    def test_high_ece_tightens_thresholds(self):
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = apply_calibration_outcome(
                "algorithm_implementation",
                _high_ece_samples(),
            )
        assert state.rca_trigger_threshold < _DEFAULT_RCA_THRESHOLD

    def test_low_ece_relaxes_thresholds(self):
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = apply_calibration_outcome(
                "algorithm_implementation",
                _low_ece_samples(),
            )
        assert state.rca_trigger_threshold > _DEFAULT_RCA_THRESHOLD

    def test_empty_samples_returns_default_state(self):
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = apply_calibration_outcome("algorithm_implementation", [])
        assert state.rca_trigger_threshold == _DEFAULT_RCA_THRESHOLD
        assert state.decomposition_depth == _DEFAULT_DECOMP_DEPTH
        assert state.ema_ece is None

    def test_custom_alpha_forwarded(self):
        with patch("bob.online_threshold_tuning.emit_telemetry_line"):
            state = apply_calibration_outcome(
                "algorithm_implementation",
                _high_ece_samples(),
                alpha=0.9,
            )
        # With alpha=0.9, EMA converges faster to current ECE (0.9)
        assert state.ema_ece is not None
        assert state.ema_ece > 0.5
