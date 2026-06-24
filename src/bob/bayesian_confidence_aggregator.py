"""Bayesian confidence aggregator for Bob (F-R4-130).

Combines four independent signals into a single calibrated probability
estimate of implementation success:

1. Self-reported confidence — the three feature-level conf_* fields
   (conf_spec_understanding, conf_impl_correctness, conf_test_adequacy)
   averaged into a raw prior.
2. Registry hit count — features whose task class has many historical
   successes get a mild positive prior boost; features with only failures
   get a negative boost.
3. AST heuristics — presence of stub functions or mock imports in source
   files penalises the estimate; absence gives a small positive nudge.
4. Task-class priors — empirical base-rates drawn from the calibration_data
   table.  Unknown task classes default to 0.5.

The aggregation uses a log-odds Bayesian update:

    log_odds = log(p / (1 - p))

Starting from the self-reported prior, each signal contributes an additive
delta to the log-odds.  The result is converted back to a probability with
the logistic function and clamped to [0.02, 0.98] to avoid degenerate
outputs.

Public API
----------
aggregate_confidence(
    conf_spec, conf_impl, conf_test,
    task_class,
    registry_success_rate, registry_n,
    has_stub_errors, has_mock_errors,
    task_class_prior,
) -> float

BayesianConfidenceAggregator  — stateless callable wrapper (for easy injection)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Default task-class prior pass-rates (empirical placeholders).
# Overridden at runtime by data from calibration_data when available.
# ---------------------------------------------------------------------------

_DEFAULT_TASK_CLASS_PRIORS: dict[str, float] = {
    "file_manipulation": 0.72,
    "algorithm_implementation": 0.65,
    "integration": 0.58,
    "refactor": 0.70,
    "research_synthesis": 0.60,
}

_FALLBACK_PRIOR = 0.60

# Weight parameters — how strongly each signal influences log-odds.
_REGISTRY_WEIGHT = 0.5   # max ±0.5 nats of adjustment from registry
_AST_STUB_PENALTY = -1.2  # log-odds penalty when error-severity stubs found
_AST_MOCK_PENALTY = -0.8  # log-odds penalty when mock usage found in src/
_AST_CLEAN_BONUS = 0.2    # small bonus when source is stub-and-mock-free
_TASK_CLASS_WEIGHT = 0.4  # weight of task-class prior vs self-report


# ---------------------------------------------------------------------------
# Core math helpers
# ---------------------------------------------------------------------------


def _to_log_odds(p: float) -> float:
    """Convert probability to log-odds; clamps input to (1e-6, 1-1e-6)."""
    p = max(1e-6, min(1.0 - 1e-6, p))
    return math.log(p / (1.0 - p))


def _from_log_odds(lo: float) -> float:
    """Convert log-odds back to probability via logistic function."""
    return 1.0 / (1.0 + math.exp(-lo))


def _clamp_prob(p: float) -> float:
    """Clamp probability to [0.02, 0.98] to keep outputs interpretable."""
    return max(0.02, min(0.98, p))


# ---------------------------------------------------------------------------
# Main aggregation function
# ---------------------------------------------------------------------------


def aggregate_confidence(
    *,
    conf_spec: float,
    conf_impl: float,
    conf_test: float,
    task_class: str = "algorithm_implementation",
    registry_success_rate: float | None = None,
    registry_n: int = 0,
    has_stub_errors: bool = False,
    has_mock_errors: bool = False,
    task_class_prior: float | None = None,
) -> float:
    """Compute a calibrated confidence estimate from four independent signals.

    Parameters
    ----------
    conf_spec:
        Self-reported confidence in spec understanding (0–1).
    conf_impl:
        Self-reported confidence in implementation correctness (0–1).
    conf_test:
        Self-reported confidence in test adequacy (0–1).
    task_class:
        One of the five canonical task class labels.  Used for prior lookup
        if ``task_class_prior`` is not supplied.
    registry_success_rate:
        Empirical pass-rate for this task class drawn from calibration_data
        (float in 0–1), or None when no history is available.
    registry_n:
        Number of historical observations backing ``registry_success_rate``.
        Observations with n < 3 are weighted less to avoid overfit.
    has_stub_errors:
        True when the AST checker found error-severity stubs in src/.
    has_mock_errors:
        True when the AST checker found mock imports in src/.
    task_class_prior:
        Explicit task-class base-rate override.  When None, looked up from
        ``_DEFAULT_TASK_CLASS_PRIORS`` (or 0.6 for unknown classes).

    Returns
    -------
    float
        Calibrated probability in [0.02, 0.98].
    """
    # --- Signal 1: self-reported prior (equal-weight average) ---
    raw_self = (float(conf_spec) + float(conf_impl) + float(conf_test)) / 3.0
    raw_self = max(0.0, min(1.0, raw_self))

    # --- Signal 4: task-class prior ---
    if task_class_prior is None:
        task_class_prior = _DEFAULT_TASK_CLASS_PRIORS.get(task_class, _FALLBACK_PRIOR)
    task_class_prior = max(0.0, min(1.0, float(task_class_prior)))

    # Blend self-report with task-class prior using fixed weights.
    blended_p = (1.0 - _TASK_CLASS_WEIGHT) * raw_self + _TASK_CLASS_WEIGHT * task_class_prior
    log_odds = _to_log_odds(blended_p)

    # --- Signal 2: registry hit count ---
    if registry_success_rate is not None and registry_n >= 1:
        reg_rate = max(0.0, min(1.0, float(registry_success_rate)))
        # Scale weight by sqrt(n) / sqrt(10) so n=10 gives full weight.
        effective_weight = _REGISTRY_WEIGHT * min(1.0, math.sqrt(registry_n) / math.sqrt(10))
        reg_log_odds = _to_log_odds(reg_rate)
        # Blend registry log-odds into current estimate.
        log_odds += effective_weight * (reg_log_odds - log_odds)

    # --- Signal 3: AST heuristics ---
    if has_stub_errors:
        log_odds += _AST_STUB_PENALTY
    if has_mock_errors:
        log_odds += _AST_MOCK_PENALTY
    if not has_stub_errors and not has_mock_errors:
        log_odds += _AST_CLEAN_BONUS

    return _clamp_prob(_from_log_odds(log_odds))


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


@dataclass
class AggregationResult:
    """Output of BayesianConfidenceAggregator.aggregate()."""

    calibrated_confidence: float
    self_reported_avg: float
    task_class: str
    signals_applied: list[str]


class BayesianConfidenceAggregator:
    """Stateless aggregator that wraps ``aggregate_confidence``.

    Designed for dependency injection — pass an instance to wherever
    calibrated confidence needs to be computed.
    """

    def aggregate(
        self,
        *,
        conf_spec: float,
        conf_impl: float,
        conf_test: float,
        task_class: str = "algorithm_implementation",
        registry_success_rate: float | None = None,
        registry_n: int = 0,
        has_stub_errors: bool = False,
        has_mock_errors: bool = False,
        task_class_prior: float | None = None,
    ) -> AggregationResult:
        """Run aggregation and return a structured result.

        Parameters mirror those of :func:`aggregate_confidence`.
        """
        signals: list[str] = ["self_report", "task_class_prior"]
        if registry_success_rate is not None and registry_n >= 1:
            signals.append("registry")
        if has_stub_errors:
            signals.append("ast_stub_penalty")
        if has_mock_errors:
            signals.append("ast_mock_penalty")
        if not has_stub_errors and not has_mock_errors:
            signals.append("ast_clean_bonus")

        calibrated = aggregate_confidence(
            conf_spec=conf_spec,
            conf_impl=conf_impl,
            conf_test=conf_test,
            task_class=task_class,
            registry_success_rate=registry_success_rate,
            registry_n=registry_n,
            has_stub_errors=has_stub_errors,
            has_mock_errors=has_mock_errors,
            task_class_prior=task_class_prior,
        )
        self_avg = (float(conf_spec) + float(conf_impl) + float(conf_test)) / 3.0

        return AggregationResult(
            calibrated_confidence=calibrated,
            self_reported_avg=self_avg,
            task_class=task_class,
            signals_applied=signals,
        )
