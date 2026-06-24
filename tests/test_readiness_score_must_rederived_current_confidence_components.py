"""Tests for readiness_score_must_rederived_current_confidence_components (961667e0).

Acceptance criteria:
- File exists: src/bob/readiness_score_must_rederived_current_confidence_components.py
- Function defined: bob.readiness_score_must_rederived_current_confidence_components
  .readiness_score_must_rederived_current_confidence_components
- pytest: tests/test_readiness_score_must_rederived_current_confidence_components.py
  ::test_readiness_score_must_rederived_current_confidence_components

The central invariant being tested:
    readiness_score = mean(conf_impl_correctness, conf_spec_understanding, conf_test_quality)

Readiness MUST be derived from live component values — never from a stored,
decaying readiness_score column.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import bob.readiness_score_must_rederived_current_confidence_components as mod
from bob.readiness_score_must_rederived_current_confidence_components import (
    readiness_score_must_rederived_current_confidence_components,
)


# ---------------------------------------------------------------------------
# AC test — named exactly as the acceptance criterion requires
# ---------------------------------------------------------------------------


def test_readiness_score_must_rederived_current_confidence_components():
    """AC test: function is importable and derives readiness from live confidence components."""
    # Function is callable
    assert callable(readiness_score_must_rederived_current_confidence_components)

    # Module docstring describes the rederivation fix
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "readiness" in doc
    assert "confidence" in doc

    # Equal components → their mean
    result = readiness_score_must_rederived_current_confidence_components(
        conf_impl_correctness=0.9,
        conf_spec_understanding=0.9,
        conf_test_quality=0.9,
    )
    assert abs(result - 0.9) < 1e-9

    # Mixed components → arithmetic mean
    result = readiness_score_must_rederived_current_confidence_components(
        conf_impl_correctness=0.6,
        conf_spec_understanding=0.9,
        conf_test_quality=0.9,
    )
    expected = (0.6 + 0.9 + 0.9) / 3.0
    assert abs(result - expected) < 1e-9

    # Zero components → zero readiness (never claims a stale decayed value)
    result = readiness_score_must_rederived_current_confidence_components(
        conf_impl_correctness=0.0,
        conf_spec_understanding=0.0,
        conf_test_quality=0.0,
    )
    assert result == 0.0

    # Perfect components → 1.0
    result = readiness_score_must_rederived_current_confidence_components(
        conf_impl_correctness=1.0,
        conf_spec_understanding=1.0,
        conf_test_quality=1.0,
    )
    assert abs(result - 1.0) < 1e-9

    # Source file exists at the expected path
    src = Path(__file__).parents[1] / "src" / "bob" / \
        "readiness_score_must_rederived_current_confidence_components.py"
    assert src.exists(), f"Source file missing: {src}"


# ---------------------------------------------------------------------------
# Derivation invariant tests
# ---------------------------------------------------------------------------


class TestReadinessDerivationInvariant:
    """Readiness = mean(impl, spec, test) — always derived, never decayed state."""

    def test_ratchet_scenario_does_not_apply(self):
        """After two failures decaying impl to 0.55, derive still reflects live values."""
        # Simulate: original 0.85 readiness, then 2 x 0.15 decay applied to impl only
        decayed_impl = 0.85 - 0.30  # = 0.55
        result = readiness_score_must_rederived_current_confidence_components(
            conf_impl_correctness=decayed_impl,
            conf_spec_understanding=0.85,
            conf_test_quality=0.85,
        )
        # Derived from CURRENT components — not stored decayed readiness
        expected = (0.55 + 0.85 + 0.85) / 3.0
        assert abs(result - expected) < 1e-9
        # Crucially, result > 0.55 (which was the ratcheted stored value)
        assert result > 0.55

    def test_recovery_after_improvement(self):
        """If components improve (e.g., after infra error cleared), readiness follows."""
        # First: poor components
        low = readiness_score_must_rederived_current_confidence_components(
            conf_impl_correctness=0.4,
            conf_spec_understanding=0.5,
            conf_test_quality=0.5,
        )
        # After recovery
        high = readiness_score_must_rederived_current_confidence_components(
            conf_impl_correctness=0.85,
            conf_spec_understanding=0.90,
            conf_test_quality=0.88,
        )
        assert high > low

    def test_asymmetric_components(self):
        """Each component contributes equally to the mean."""
        # Only impl changes; spec and test fixed
        r1 = readiness_score_must_rederived_current_confidence_components(
            conf_impl_correctness=0.3,
            conf_spec_understanding=0.9,
            conf_test_quality=0.9,
        )
        r2 = readiness_score_must_rederived_current_confidence_components(
            conf_impl_correctness=0.9,
            conf_spec_understanding=0.9,
            conf_test_quality=0.9,
        )
        delta = r2 - r1
        expected_delta = (0.9 - 0.3) / 3.0
        assert abs(delta - expected_delta) < 1e-9

    def test_result_is_bounded_0_1_for_valid_inputs(self):
        """Result stays in [0, 1] for valid component range inputs."""
        for v in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = readiness_score_must_rederived_current_confidence_components(
                conf_impl_correctness=v,
                conf_spec_understanding=v,
                conf_test_quality=v,
            )
            assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# Re-exports tests
# ---------------------------------------------------------------------------


class TestModuleReExports:
    """The module re-exports primitives needed by callers."""

    def test_derive_readiness_score_re_exported(self):
        from bob.readiness_score_must_rederived_current_confidence_components import (
            derive_readiness_score,
        )
        assert callable(derive_readiness_score)

    def test_calculate_readiness_live_re_exported(self):
        from bob.readiness_score_must_rederived_current_confidence_components import (
            calculate_readiness_live,
        )
        assert callable(calculate_readiness_live)

    def test_seed_readiness_at_iteration_start_re_exported(self):
        from bob.readiness_score_must_rederived_current_confidence_components import (
            seed_readiness_at_iteration_start,
        )
        assert callable(seed_readiness_at_iteration_start)

    def test_all_exports_listed(self):
        assert "readiness_score_must_rederived_current_confidence_components" in mod.__all__
        assert "derive_readiness_score" in mod.__all__
        assert "calculate_readiness_live" in mod.__all__
        assert "seed_readiness_at_iteration_start" in mod.__all__


# ---------------------------------------------------------------------------
# Delegation tests
# ---------------------------------------------------------------------------


class TestDelegation:
    """The facade delegates to bob.readiness.derive_readiness_score."""

    def test_delegates_to_derive_readiness_score(self):
        with patch(
            "bob.readiness_score_must_rederived_current_confidence_components.derive_readiness_score"
        ) as mock_derive:
            mock_derive.return_value = 0.77

            result = readiness_score_must_rederived_current_confidence_components(
                conf_impl_correctness=0.7,
                conf_spec_understanding=0.8,
                conf_test_quality=0.8,
            )

        assert result == 0.77
        mock_derive.assert_called_once_with(
            conf_impl_correctness=0.7,
            conf_spec_understanding=0.8,
            conf_test_quality=0.8,
        )
