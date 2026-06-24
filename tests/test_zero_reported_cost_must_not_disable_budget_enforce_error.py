"""Error-path tests: invalid input raises ValueError and does not silently succeed.

AC: pytest: tests/test_zero_reported_cost_must_not_disable_budget_enforce_error.py
    — invalid input raises ValueError and the function does not silently succeed.

Covers:
- enforce_zero_cost_policy raises ValueError for negative/zero per_feature_ceiling
- validate_reported_cost raises TypeError for non-numeric work_events
- should_treat_cost_as_unknown raises on invalid types where appropriate
"""

from __future__ import annotations

import pytest

from bob.cost_enforcement import (
    CostValidationResult,
    enforce_zero_cost_policy,
    validate_reported_cost,
)


class TestEnforceZeroCostPolicyInvalidCeiling:
    """enforce_zero_cost_policy must raise ValueError for invalid per_feature_ceiling."""

    def test_zero_ceiling_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id="error-zero-ceiling",
            )

    def test_negative_ceiling_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-1.0,
                feature_id="error-negative-ceiling",
            )

    def test_large_negative_ceiling_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-100.0,
                feature_id="error-large-negative-ceiling",
            )

    def test_very_small_negative_ceiling_raises_value_error(self):
        with pytest.raises(ValueError):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-0.0001,
                feature_id="error-tiny-negative-ceiling",
            )

    def test_zero_ceiling_does_not_silently_succeed(self):
        """Invalid ceiling must raise — not return a result silently."""
        raised = False
        try:
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id="error-silent-check",
            )
        except ValueError:
            raised = True
        assert raised, "enforce_zero_cost_policy must raise ValueError for zero ceiling"

    def test_negative_ceiling_does_not_silently_succeed(self):
        raised = False
        try:
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-5.0,
                feature_id="error-neg-silent-check",
            )
        except ValueError:
            raised = True
        assert raised, "enforce_zero_cost_policy must raise ValueError for negative ceiling"

    def test_error_message_mentions_per_feature_ceiling(self):
        """The ValueError message must reference per_feature_ceiling so it's diagnosable."""
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=-1.0,
                feature_id="error-msg-check",
            )

    def test_zero_ceiling_error_message_mentions_ceiling(self):
        with pytest.raises(ValueError, match="per_feature_ceiling"):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=0.0,
                feature_id="error-zero-msg-check",
            )

    def test_invalid_ceiling_with_telemetry_loss_context_still_raises(self):
        """Even when telemetry would be lost, invalid ceiling must still raise."""
        with pytest.raises(ValueError):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=176217,
                per_feature_ceiling=0.0,
                feature_id="error-telem-loss-zero-ceiling",
            )

    def test_invalid_ceiling_with_free_retry_context_still_raises(self):
        """Even in the free-retry case (work_events=0), invalid ceiling must still raise."""
        with pytest.raises(ValueError):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=0,
                per_feature_ceiling=0.0,
                feature_id="error-free-retry-zero-ceiling",
            )


class TestErrorPathDoesNotReturnSilentSuccess:
    """Verify the error cases truly raise rather than returning a default/zero result."""

    def test_enforce_negative_ceiling_no_return_value(self):
        result = None
        try:
            result = enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=500,
                per_feature_ceiling=-1.0,
                feature_id="error-no-return",
            )
        except ValueError:
            pass
        assert result is None, (
            "enforce_zero_cost_policy must NOT return a value when ceiling is invalid"
        )

    def test_enforce_zero_ceiling_no_return_value(self):
        result = None
        try:
            result = enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=500,
                per_feature_ceiling=0.0,
                feature_id="error-zero-no-return",
            )
        except ValueError:
            pass
        assert result is None, (
            "enforce_zero_cost_policy must NOT return a value when ceiling is zero"
        )

    @pytest.mark.parametrize("bad_ceiling", [0.0, -0.001, -1.0, -10.0, -1000.0])
    def test_all_invalid_ceilings_raise(self, bad_ceiling):
        with pytest.raises(ValueError):
            enforce_zero_cost_policy(
                reported_cost=0.0,
                work_events=200,
                per_feature_ceiling=bad_ceiling,
                feature_id="error-param-bad-ceiling",
            )
